"""gRPC server for internal container-to-container traffic.

Runs alongside the FastAPI HTTP app on ``api:50051`` (internal-only,
``expose: -50051`` in compose, never ``ports:``-published). Public traffic
goes via Caddy ``handle /api/* -> api:8008`` (HTTP); internal callers
(``customer-portal``, ``staff-portal``, ``developer-portal``, ``webhook``,
``worker``) should dial ``grpc.aio.insecure_channel("api:50051")`` and
pass ``x-internal-api-key`` metadata.

Servicers delegate to the same ``*_service.py`` modules that HTTP routes
use — no duplicated business logic.
"""

from __future__ import annotations

import logging
import os
import secrets

import grpc
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import desc, func, select, text

try:
    from shared.proto_gen import billing_pb2, billing_pb2_grpc
except ImportError:
    from proto_gen import billing_pb2, billing_pb2_grpc  # type: ignore

logger = logging.getLogger("grpc")

# ── Auth helper ──────────────────────────────────────────────────────────


async def _check_internal_auth(context: grpc.aio.ServicerContext) -> bool:
    """Validate ``x-internal-api-key`` metadata.

    Returns True on success, False after setting PERMISSION_DENIED on
    the context (caller should return an empty response).
    """
    md = dict(context.invocation_metadata())
    api_key = md.get("x-internal-api-key", "")
    expected = os.environ.get("INTERNAL_API_KEY", "")
    # Use constant-time compare; empty expected means misconfigured
    if not expected or not api_key or not secrets.compare_digest(api_key, expected):
        context.set_code(grpc.StatusCode.PERMISSION_DENIED)
        context.set_details("Invalid internal key")
        return False
    return True


# ── Helpers for DB ───────────────────────────────────────────────────────


def _db_sync_session():
    from db_async import sync_session

    return sync_session()


# ── BillingService ───────────────────────────────────────────────────────


class BillingServicer(billing_pb2_grpc.BillingServiceServicer):
    """gRPC servicer — delegates to the same service layer as HTTP routes."""

    async def GetCustomer(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.GetCustomerResponse()
        try:
            from db_async import session_factory
            from models import Customer

            async with session_factory()() as s:
                result = await s.execute(
                    select(Customer).where(Customer.customer_number == request.customer_number)
                )
                customer = result.scalar_one_or_none()
                if customer is None:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Customer not found")
                    return billing_pb2.GetCustomerResponse()
                return billing_pb2.GetCustomerResponse(
                    customer_number=customer.customer_number,
                    name=customer.name or "",
                    contact_number=customer.contact_number or "",
                    address=customer.address or "",
                    email=customer.email or "",
                    is_active=bool(customer.is_active),
                    total_due=float(customer.total_due or 0),
                    cumulative_balance=float(customer.cumulative_balance or 0),
                    meter_serial_number=customer.meter_serial_number or "",
                )
        except Exception as e:
            logger.exception("GetCustomer failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return billing_pb2.GetCustomerResponse()

    async def ListCustomers(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.ListCustomersResponse()
        try:
            # Reuse the sync list_customers via threadpool for consistency
            from customer_service import list_customers

            q = request.q or None
            page = request.page or 1
            size = request.size or 50
            sort_by = request.sort_by or "customer_number"
            sort_dir = request.sort_dir or "asc"

            def _list():
                s = _db_sync_session()
                try:
                    items, total = list_customers(
                        page=page, per_page=size, q=q, sort_by=sort_by, sort_dir=sort_dir, session=s
                    )
                    # Detach needed fields before closing
                    data = [
                        (
                            c.customer_number,
                            c.name,
                            c.contact_number,
                            c.address,
                            c.email,
                            c.is_active,
                            float(c.total_due or 0),
                            float(c.cumulative_balance or 0),
                            c.meter_serial_number,
                        )
                        for c in items
                    ]
                    return data, total
                finally:
                    s.close()

            data, total = await run_in_threadpool(_list)
            customers = [
                billing_pb2.GetCustomerResponse(
                    customer_number=cn,
                    name=n or "",
                    contact_number=ct or "",
                    address=a or "",
                    email=e or "",
                    is_active=bool(ia),
                    total_due=td,
                    cumulative_balance=cb,
                    meter_serial_number=ms or "",
                )
                for cn, n, ct, a, e, ia, td, cb, ms in data
            ]
            pages = max(1, (total + size - 1) // size) if size else 1
            return billing_pb2.ListCustomersResponse(
                customers=customers, total=total, page=page, pages=pages, page_size=size
            )
        except Exception as e:
            logger.exception("ListCustomers failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return billing_pb2.ListCustomersResponse()

    async def CreateCustomer(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.CreateCustomerResponse()
        try:
            from customer_service import create_customer

            def _create():
                s = _db_sync_session()
                try:
                    from models import Customer as C

                    max_val = s.query(func.max(C.customer_number)).scalar() or 100000
                    next_cn = int(max_val) + 1
                    data = {
                        "customer_number": next_cn,
                        "name": request.name,
                        "address": request.address,
                        "contact_number": request.contact_number,
                        "email": request.email,
                    }
                    cust, err = create_customer(data, session=s)
                    if err:
                        return None, err
                    return cust.customer_number if cust else None, None
                finally:
                    s.close()

            cn, err = await run_in_threadpool(_create)
            if err:
                context.set_code(
                    grpc.StatusCode.ALREADY_EXISTS
                    if "already exists" in err
                    else grpc.StatusCode.INVALID_ARGUMENT
                )
                context.set_details(err)
                return billing_pb2.CreateCustomerResponse()
            return billing_pb2.CreateCustomerResponse(customer_number=cn or 0, name=request.name)
        except Exception as e:
            logger.exception("CreateCustomer failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return billing_pb2.CreateCustomerResponse()

    async def GetBillingHistory(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.GetBillingHistoryResponse()
        try:
            from db_async import session_factory
            from models import Billing

            page = request.page or 1
            size = request.size or 12
            offset = (page - 1) * size
            async with session_factory()() as s:
                total_res = await s.execute(
                    select(func.count())
                    .select_from(Billing)
                    .where(Billing.customer_number == request.customer_number)
                )
                total = total_res.scalar() or 0
                result = await s.execute(
                    select(Billing)
                    .where(Billing.customer_number == request.customer_number)
                    .order_by(desc(Billing.date_created))
                    .offset(offset)
                    .limit(size)
                )
                rows = result.scalars().all()
                records = []
                for b in rows:
                    month_str = ""
                    if b.reading and b.reading.timestamp:
                        month_str = b.reading.timestamp.strftime("%B %Y")
                    elif b.date_created:
                        month_str = b.date_created.strftime("%B %Y")
                    records.append(
                        billing_pb2.BillingRecord(
                            id=b.id,
                            customer_number=b.customer_number,
                            month=month_str,
                            consumption=float(b.consumption or 0),
                            billed_amount=float(b.billed_amount or 0),
                            penalty=float(b.penalty or 0),
                            is_paid=bool(b.is_paid),
                            paid_amount=float(b.paid_amount or 0),
                            payment_timestamp=int(b.payment_timestamp.timestamp())
                            if b.payment_timestamp
                            else 0,
                        )
                    )
                pages = max(1, (total + size - 1) // size) if size else 1
                return billing_pb2.GetBillingHistoryResponse(
                    records=records, total=total, page=page, pages=pages
                )
        except Exception as e:
            logger.exception("GetBillingHistory failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return billing_pb2.GetBillingHistoryResponse()

    async def SubmitPayment(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.SubmitPaymentResponse(success=False, message="Invalid internal key")
        try:
            from shared.services.payment_service import submit_payment

            def _pay():
                s = _db_sync_session()
                try:
                    # Use cashier 1 as internal caller when not specified
                    result, err, code = submit_payment(
                        request.customer_number, float(request.amount), cashier_id=1, session=s
                    )
                    if err:
                        return False, err, 0
                    bid = result.get("billing_id") if isinstance(result, dict) else 0
                    return True, "Payment submitted", bid or 0
                finally:
                    s.close()

            success, msg, bid = await run_in_threadpool(_pay)
            if not success:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(msg)
                return billing_pb2.SubmitPaymentResponse(success=False, message=msg)
            return billing_pb2.SubmitPaymentResponse(success=True, message=msg, billing_id=bid)
        except Exception as e:
            logger.exception("SubmitPayment failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return billing_pb2.SubmitPaymentResponse(success=False, message=str(e))

    async def GetReadings(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.GetReadingsResponse()
        try:
            from db_async import session_factory
            from models import MeterReading

            page = request.page or 1
            size = request.size or 12
            offset = (page - 1) * size
            async with session_factory()() as s:
                total_res = await s.execute(
                    select(func.count())
                    .select_from(MeterReading)
                    .where(MeterReading.customer_number == request.customer_number)
                )
                total = total_res.scalar() or 0
                result = await s.execute(
                    select(MeterReading)
                    .where(MeterReading.customer_number == request.customer_number)
                    .order_by(desc(MeterReading.timestamp))
                    .offset(offset)
                    .limit(size)
                )
                rows = result.scalars().all()
                readings = []
                for r in rows:
                    readings.append(
                        billing_pb2.ReadingRecord(
                            id=r.id,
                            customer_number=r.customer_number,
                            reading_value=float(r.reading_value or 0),
                            timestamp=int(r.timestamp.timestamp()) if r.timestamp else 0,
                            reader_name="",
                        )
                    )
                pages = max(1, (total + size - 1) // size) if size else 1
                return billing_pb2.GetReadingsResponse(
                    readings=readings, total=total, page=page, pages=pages
                )
        except Exception as e:
            logger.exception("GetReadings failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return billing_pb2.GetReadingsResponse()

    async def HealthCheck(self, request, context):  # type: ignore[no-untyped-def]
        if not await _check_internal_auth(context):
            return billing_pb2.HealthCheckResponse(status="permission_denied", db="unauthorized")
        try:
            from db_async import session_factory

            async with session_factory()() as s:
                await s.execute(text("SELECT 1"))
                return billing_pb2.HealthCheckResponse(status="ok", db="connected")
        except Exception as e:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details(str(e))
            return billing_pb2.HealthCheckResponse(status="degraded", db=str(e))


class CustomerServicer(billing_pb2_grpc.CustomerServiceServicer):
    """Thin alias — same logic as BillingServicer for CustomerService."""

    async def GetCustomer(self, request, context):  # type: ignore[no-untyped-def]
        return await BillingServicer().GetCustomer(request, context)

    async def CreateCustomer(self, request, context):  # type: ignore[no-untyped-def]
        return await BillingServicer().CreateCustomer(request, context)


# ── Server bootstrap ─────────────────────────────────────────────────────

_grpc_server: grpc.aio.Server | None = None


async def start_grpc_server() -> grpc.aio.Server:
    """Create, start and return the gRPC server on ``0.0.0.0:50051``."""
    global _grpc_server
    server = grpc.aio.server()
    billing_pb2_grpc.add_BillingServiceServicer_to_server(BillingServicer(), server)
    billing_pb2_grpc.add_CustomerServiceServicer_to_server(CustomerServicer(), server)
    server.add_insecure_port("0.0.0.0:50051")
    await server.start()
    logger.info("gRPC server started on 0.0.0.0:50051")
    _grpc_server = server
    return server


async def stop_grpc_server(grace: int = 5) -> None:
    global _grpc_server
    if _grpc_server is not None:
        await _grpc_server.stop(grace=grace)
        _grpc_server = None
