"""Shared gRPC client for container-to-container calls.

Internal services (portals, webhook, worker) should prefer gRPC via
``grpc.aio.insecure_channel("api:50051")`` over HTTP to ``http://api:8008``.
Public traffic (browsers, Xendit callbacks via Caddy) stays on HTTP
``handle /api/* -> api:8008`` and never dials gRPC.

Auth is via ``x-internal-api-key`` gRPC metadata, same value as the
HTTP ``X-Internal-API-Key`` header (``INTERNAL_API_KEY`` env).
"""

from __future__ import annotations

import os

import grpc

try:
    from shared.proto_gen import billing_pb2, billing_pb2_grpc
except ImportError:  # when PYTHONPATH=/app/shared, proto_gen is top-level
    from proto_gen import billing_pb2, billing_pb2_grpc  # type: ignore


def _grpc_addr() -> str:
    return os.environ.get("API_GRPC_ADDR", "api:50051")


def _grpc_metadata() -> tuple[tuple[str, str], ...]:
    key = os.environ.get("INTERNAL_API_KEY", "")
    if key:
        return (("x-internal-api-key", key),)
    return ()


async def get_customer_via_grpc(customer_number: int) -> dict | None:
    """Call api:50051 BillingService.GetCustomer via gRPC."""
    async with grpc.aio.insecure_channel(_grpc_addr()) as channel:
        stub = billing_pb2_grpc.BillingServiceStub(channel)
        try:
            resp = await stub.GetCustomer(
                billing_pb2.GetCustomerRequest(customer_number=customer_number),
                metadata=_grpc_metadata(),
                timeout=5,
            )
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                raise PermissionError(e.details()) from e
            raise
        return {
            "customer_number": resp.customer_number,
            "name": resp.name,
            "contact_number": resp.contact_number,
            "address": resp.address,
            "email": resp.email,
            "is_active": resp.is_active,
            "total_due": resp.total_due,
            "cumulative_balance": resp.cumulative_balance,
            "meter_serial_number": resp.meter_serial_number,
        }


async def list_customers_via_grpc(
    q: str = "",
    page: int = 1,
    size: int = 50,
    sort_by: str = "customer_number",
    sort_dir: str = "asc",
) -> dict | None:
    """Call BillingService.ListCustomers via gRPC."""
    async with grpc.aio.insecure_channel(_grpc_addr()) as channel:
        stub = billing_pb2_grpc.BillingServiceStub(channel)
        try:
            resp = await stub.ListCustomers(
                billing_pb2.ListCustomersRequest(
                    q=q or "", page=page, size=size, sort_by=sort_by, sort_dir=sort_dir
                ),
                metadata=_grpc_metadata(),
                timeout=5,
            )
        except grpc.aio.AioRpcError:
            return None
        return {
            "customers": [
                {
                    "customer_number": c.customer_number,
                    "name": c.name,
                    "contact_number": c.contact_number,
                    "address": c.address,
                    "email": c.email,
                    "is_active": c.is_active,
                    "total_due": c.total_due,
                    "cumulative_balance": c.cumulative_balance,
                    "meter_serial_number": c.meter_serial_number,
                }
                for c in resp.customers
            ],
            "total": resp.total,
            "page": resp.page,
            "pages": resp.pages,
            "per_page": resp.page_size,
        }


async def get_billing_history_via_grpc(
    customer_number: int, page: int = 1, size: int = 12
) -> dict | None:
    async with grpc.aio.insecure_channel(_grpc_addr()) as channel:
        stub = billing_pb2_grpc.BillingServiceStub(channel)
        try:
            resp = await stub.GetBillingHistory(
                billing_pb2.GetBillingHistoryRequest(
                    customer_number=customer_number, page=page, size=size
                ),
                metadata=_grpc_metadata(),
                timeout=5,
            )
        except grpc.aio.AioRpcError:
            return None
        return {
            "records": [
                {
                    "id": r.id,
                    "customer_number": r.customer_number,
                    "month": r.month,
                    "consumption": r.consumption,
                    "billed_amount": r.billed_amount,
                    "penalty": r.penalty,
                    "is_paid": r.is_paid,
                    "paid_amount": r.paid_amount,
                    "payment_timestamp": r.payment_timestamp,
                }
                for r in resp.records
            ],
            "total": resp.total,
            "page": resp.page,
            "pages": resp.pages,
        }


async def get_readings_via_grpc(customer_number: int, page: int = 1, size: int = 12) -> dict | None:
    async with grpc.aio.insecure_channel(_grpc_addr()) as channel:
        stub = billing_pb2_grpc.BillingServiceStub(channel)
        try:
            resp = await stub.GetReadings(
                billing_pb2.GetReadingsRequest(
                    customer_number=customer_number, page=page, size=size
                ),
                metadata=_grpc_metadata(),
                timeout=5,
            )
        except grpc.aio.AioRpcError:
            return None
        return {
            "readings": [
                {
                    "id": r.id,
                    "customer_number": r.customer_number,
                    "reading_value": r.reading_value,
                    "timestamp": r.timestamp,
                    "reader_name": r.reader_name,
                }
                for r in resp.readings
            ],
            "total": resp.total,
            "page": resp.page,
            "pages": resp.pages,
        }


async def health_check_via_grpc() -> dict | None:
    async with grpc.aio.insecure_channel(_grpc_addr()) as channel:
        stub = billing_pb2_grpc.BillingServiceStub(channel)
        try:
            resp = await stub.HealthCheck(
                billing_pb2.HealthCheckRequest(),
                metadata=_grpc_metadata(),
                timeout=3,
            )
        except grpc.aio.AioRpcError:
            return None
        return {"status": resp.status, "db": resp.db}
