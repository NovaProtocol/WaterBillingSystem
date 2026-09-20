from __future__ import annotations

from datetime import datetime, timedelta, timezone

from billing_service import ensure_penalty
from customer_service import (
    create_customer,
    list_customers,
    recalc_total_due,
    toggle_active,
    update_customer,
)
from db_async import session
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from models import ApiKey, Billing, Customer, MeterReading, NfcTag
from pricing import PRICING_TIERS
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import joinedload, selectinload
from utils import require_customer_self, require_staff

from routes.customer.common import _run_sync

router = APIRouter()


class CustomerCreatePayload(BaseModel):
    customer_number: int | None = None
    name: str = ""
    address: str = ""
    contact_number: str = ""
    email: str = ""
    phase: str | None = None
    block: str | None = None
    street: str | None = None
    x_coordinate: float | None = None
    y_coordinate: float | None = None
    max_meter_value: float | None = None


class CustomerUpdatePayload(BaseModel):
    name: str | None = None
    address: str | None = None
    contact_number: str | None = None
    email: str | None = None
    phase: str | None = None
    block: str | None = None
    street: str | None = None
    x_coordinate: float | None = None
    y_coordinate: float | None = None


class CustomerLoginPayload(BaseModel):
    account_number: int | None = None
    registered_name: str = ""
    last_receipt: str = ""


@router.get("/customer/count")
async def customer_count(api_key: ApiKey = Depends(require_staff("can_read_meters"))):
    result = await session().execute(
        select(func.count()).select_from(Customer).where(Customer.is_active.is_(True))
    )
    return {"count": result.scalar() or 0}


@router.get("/customer/all")
async def customer_all(
    request: Request, api_key: ApiKey = Depends(require_staff("can_read_meters"))
):
    try:
        page = int(request.query_params.get("page", "1"))
    except (ValueError, TypeError):
        page = 1
    try:
        size = int(request.query_params.get("size", "50"))
    except (ValueError, TypeError):
        size = 50
    q = request.query_params.get("q", "").strip()
    sort_by = request.query_params.get("sort_by", "customer_number")
    sort_dir = request.query_params.get("sort_dir", "asc")

    items, total = await _run_sync(
        list_customers,
        page=page,
        per_page=size,
        q=q or None,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    cnums = [c.customer_number for c in items]
    nfc_map: dict[str, str] = {}
    if cnums:
        result = await session().execute(
            select(NfcTag.customer_number, NfcTag.uid).where(NfcTag.customer_number.in_(cnums))
        )
        nfc_map = {row[0]: row[1] for row in result.all()}

    customers_data = []
    for c in items:
        customers_data.append(
            {
                "id": c.id,
                "customer_number": c.customer_number,
                "name": c.name,
                "address": c.address,
                "meter_serial_number": c.meter_serial_number or "",
                "contact_number": c.contact_number,
                "email": c.email,
                "phase": c.phase,
                "block": c.block,
                "street": c.street,
                "x_coordinate": c.x_coordinate,
                "y_coordinate": c.y_coordinate,
                "cumulative_balance": float(c.cumulative_balance or 0),
                "max_meter_value": float(c.max_meter_value or 99999),
                "total_due": float(c.total_due or 0),
                "is_active": c.is_active,
                "nfc_uid": nfc_map.get(c.customer_number),
            }
        )
    pages = max(1, (total + size - 1) // size) if size else 1
    return {
        "data": customers_data,
        "meta": {
            "current_page": page,
            "page_size": size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@router.get("/customer/{customer_number}")
async def customer_info(
    customer_number: int,
    request: Request,
):
    """Get full billing details for a specific customer.

    Staff callers authorize via ``require_staff`` exactly as before. The
    customer portal additionally forwards the verified ``billing_session``
    JWT as ``X-Customer-Token``, a token whose ``customer_number`` matches
    this path number authorizes the self-service context read, nothing
    else."""

    self_read = require_customer_self(customer_number, request)
    if self_read is None:
        # No matching customer session, fall back to the unchanged staff
        # path, which raises 401/403 itself on failure.
        await require_staff("can_read_meters")(request)

    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    await _run_sync(recalc_total_due, customer_number)
    from services.payment_service import recalc_cumulative_balance

    await _run_sync(recalc_cumulative_balance, customer_number)

    try:
        staff_filter = (
            int(request.query_params.get("staff_id"))
            if request.query_params.get("staff_id")
            else None
        )
    except (ValueError, TypeError):
        staff_filter = None
    try:
        token_filter = (
            int(request.query_params.get("token_id"))
            if request.query_params.get("token_id")
            else None
        )
    except (ValueError, TypeError):
        token_filter = None

    readings_query = (
        select(MeterReading)
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .where(MeterReading.customer_number == customer_number)
    )
    if token_filter:
        readings_query = readings_query.where(MeterReading.token_id == token_filter)
    if staff_filter:
        readings_query = readings_query.join(MeterReading.token).where(
            ApiKey.staff_id == staff_filter
        )
    readings_result = await session().execute(readings_query.order_by(desc(MeterReading.timestamp)))
    readings = readings_result.scalars().unique().all()

    latest_reading = readings[0] if len(readings) > 0 else None
    last_reading = readings[1] if len(readings) > 1 else None

    consumption = (
        float(round(latest_reading.reading_value - last_reading.reading_value, 2))
        if latest_reading and last_reading
        else 0
    )

    bills_result = await session().execute(
        select(Billing)
        .options(
            selectinload(Billing.reading),
            selectinload(Billing.cashier),
        )
        .where(Billing.customer_number == customer_number)
        .order_by(Billing.date_created.desc())
    )
    all_bills = bills_result.scalars().all()

    unpaid_bills_list: list[Billing] = []
    paid_bills_list: list[Billing] = []
    for b in all_bills:
        if not b.is_paid:
            await ensure_penalty(b)
            unpaid_bills_list.append(b)
        else:
            paid_bills_list.append(b)

    unpaid_bills = []
    for bill in unpaid_bills_list:
        reading = bill.reading
        if reading:
            month_str = reading.timestamp.strftime("%B %Y")
            ts = int(reading.timestamp.timestamp())
        else:
            month_str = bill.date_created.strftime("%B %Y") if bill.date_created else "Unknown"
            ts = int(bill.date_created.timestamp()) if bill.date_created else 0
        unpaid_bills.append(
            {
                "id": bill.id,
                "month": month_str,
                "amount": round(float(bill.billed_amount), 2),
                "penalty": round(float(bill.penalty), 2),
                "timestamp": ts,
            }
        )

    total_unpaid = sum(b["amount"] for b in unpaid_bills)
    total_penalties = sum(b["penalty"] for b in unpaid_bills)
    carryover_result = await session().execute(
        select(func.sum(Billing.carryover_offset)).where(Billing.customer_number == customer_number)
    )
    total_carryover = carryover_result.scalar() or 0
    balance = float(total_carryover)
    total_due = max(0, total_unpaid + total_penalties - balance)

    due_date = None
    days_remaining = None
    if unpaid_bills:
        due_dt = datetime.fromtimestamp(unpaid_bills[0]["timestamp"], tz=timezone.utc).replace(
            tzinfo=None
        ) + timedelta(days=7)
        due_date = due_dt.strftime("%m-%d-%Y")
        days_remaining = max(0, (due_dt - datetime.now(tz=timezone.utc).replace(tzinfo=None)).days)

    reading_pairs = []
    for i in range(len(readings)):
        curr = readings[i]
        prev = readings[i + 1] if i + 1 < len(readings) else None
        cons = float(round(curr.reading_value - prev.reading_value, 2)) if prev else 0.0

        bill = next((b for b in all_bills if b.reading_id == curr.id), None)
        if bill:
            wb = round(float(bill.billed_amount), 2)
            pen = round(float(bill.penalty), 2)
            td = round(wb + pen, 2)
            status = "Paid" if bill.is_paid else "Unpaid"
            billing_id = bill.id
            paid_amt = float(bill.paid_amount)
            receipt = bill.receipt_number
        else:
            wb = 0.0
            pen = 0.0
            td = 0.0
            status = "No bill"
            billing_id = None
            paid_amt = 0
            receipt = None

        carryover_off = float(bill.carryover_offset) if bill else 0.0

        reading_pairs.append(
            {
                "id": curr.id,
                "billing_id": billing_id,
                "reading_value": float(curr.reading_value),
                "consumption": cons,
                "water_bill": wb,
                "penalty": pen,
                "total_due": td,
                "timestamp": int(curr.timestamp.timestamp()),
                "period": int(curr.timestamp.timestamp()),
                "paid_amount": paid_amt,
                "receipt_number": receipt,
                "status": status,
                "carryover_offset": carryover_off,
                "is_latest_paid": False,
            }
        )

    latest_receipt: str | None = None
    latest_receipt_ts: datetime | None = None
    for b in all_bills:
        if b.is_paid and b.receipt_number and b.payment_timestamp:
            if latest_receipt_ts is None or b.payment_timestamp > latest_receipt_ts:
                latest_receipt_ts = b.payment_timestamp
                latest_receipt = b.receipt_number

    latest_receipt_billing_ids: set[int] = set()
    if latest_receipt:
        for b in all_bills:
            if b.receipt_number == latest_receipt:
                latest_receipt_billing_ids.add(b.id)

    for item in reading_pairs:
        item["is_latest_paid"] = item["billing_id"] in latest_receipt_billing_ids

    recent_result = await session().execute(
        select(Billing)
        .options(selectinload(Billing.cashier))
        .where(
            Billing.customer_number == customer_number,
            Billing.is_paid.is_(True),
            Billing.receipt_number.isnot(None),
        )
        .order_by(desc(Billing.date_paid))
        .limit(10)
    )
    recent_billings = recent_result.scalars().all()

    from pricing import compute_water_bill

    water_bill, bill_breakdown = compute_water_bill(consumption) if consumption > 0 else (0.0, [])
    carryover = abs(float(total_carryover))
    balance = float(total_carryover)
    latest_unpaid = len(unpaid_bills) > 0

    from models import PaymentMethod

    methods_result = await session().execute(
        select(PaymentMethod)
        .where(PaymentMethod.is_active.is_(True))
        .order_by(PaymentMethod.sort_order)
    )
    payment_methods = methods_result.scalars().all()

    return {
        "customer_number": customer.customer_number,
        "name": customer.name,
        "address": customer.address,
        "meter_serial_number": customer.meter_serial_number or "",
        "contact_number": customer.contact_number,
        "email": customer.email,
        "phase": customer.phase,
        "block": customer.block,
        "street": customer.street,
        "max_meter_value": float(customer.max_meter_value or 99999),
        "latest_reading": (
            {
                "id": latest_reading.id,
                "reading_value": float(latest_reading.reading_value),
                "reader": (
                    latest_reading.token.staff.name
                    if latest_reading.token and latest_reading.token.staff
                    else None
                ),
                "timestamp": int(latest_reading.timestamp.timestamp()),
            }
            if latest_reading
            else None
        ),
        "last_reading": (
            {
                "id": last_reading.id,
                "reading_value": float(last_reading.reading_value),
                "reader": (
                    last_reading.token.staff.name
                    if last_reading.token and last_reading.token.staff
                    else None
                ),
                "timestamp": int(last_reading.timestamp.timestamp()),
            }
            if last_reading
            else None
        ),
        "consumption": consumption,
        "bill_breakdown": bill_breakdown,
        "pricing_tiers": PRICING_TIERS,
        "water_bill": water_bill,
        "original_water_bill": water_bill,
        "carryover": carryover,
        "cumulative_balance": balance,
        "penalty": round(total_penalties, 2),
        "total_due": round(total_due, 2),
        "latest_unpaid": latest_unpaid,
        "unpaid_bills": unpaid_bills,
        "total_unpaid": round(total_unpaid, 2),
        "total_penalties": round(total_penalties, 2),
        "due_date": due_date,
        "days_remaining": days_remaining,
        "billing_items": reading_pairs,
        "recent_payments": [
            {
                "id": b.id,
                "receipt_number": b.receipt_number,
                "paid_amount": float(b.paid_amount),
                "timestamp": (
                    int(b.payment_timestamp.timestamp())
                    if b.payment_timestamp
                    else int(b.date_paid.timestamp())
                    if b.date_paid
                    else 0
                ),
                "cashier_id": b.cashier_id,
                "cashier": ((b.cashier.name or b.cashier.username) if b.cashier else None),
            }
            for b in recent_billings
        ],
        "payment_methods": [
            {
                "code": pm.code,
                "label": pm.label,
                "sort_order": pm.sort_order,
                "fee_percent": float(pm.fee_percent) if pm.fee_percent else 0,
                "fee_flat": float(pm.fee_flat) if pm.fee_flat else 0,
                "fee_minimum": float(pm.fee_minimum) if pm.fee_minimum else 0,
                "xendit_fee": float(pm.xendit_fee) if pm.xendit_fee else 0,
            }
            for pm in payment_methods
        ],
    }


@router.get("/customer/{customer_number}/details")
async def customer_details(
    customer_number: int,
    request: Request,
    api_key: ApiKey = Depends(require_staff("can_read_meters")),
):
    """Get customer profile with recent reading history."""

    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    history = request.query_params.get("history", "5")
    try:
        history = int(history)
    except (ValueError, TypeError):
        return JSONResponse({"error": "history must be an integer"}, status_code=400)

    readings_result = await session().execute(
        select(MeterReading)
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .where(MeterReading.customer_number == customer_number)
        .order_by(desc(MeterReading.timestamp))
        .limit(history)
    )
    readings = readings_result.scalars().unique().all()

    return {
        "customer": {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address,
            "meter_serial_number": customer.meter_serial_number or "",
            "contact_number": customer.contact_number,
            "email": customer.email,
            "phase": customer.phase,
            "block": customer.block,
            "street": customer.street,
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
            "cumulative_balance": float(customer.cumulative_balance or 0),
            "max_meter_value": float(customer.max_meter_value or 99999),
        },
        "readings": [
            {
                "id": r.id,
                "reading_value": float(r.reading_value),
                "reader": r.token.staff.name if r.token and r.token.staff else None,
                "timestamp": int(r.timestamp.timestamp()),
            }
            for r in readings
        ],
    }


@router.post("/customer/new", status_code=201)
async def customer_new(
    payload: CustomerCreatePayload,
    api_key: ApiKey = Depends(require_staff("can_enroll_customer")),
):
    data = payload.model_dump()
    customer, error = await _run_sync(create_customer, data)
    if error:
        status = 409 if "already exists" in error else 400
        return JSONResponse({"error": error}, status_code=status)
    return {
        "message": "Customer created",
        "customer_number": customer.customer_number,
    }


@router.put("/customer/update/{customer_number}")
async def customer_update(
    customer_number: int,
    payload: CustomerUpdatePayload,
    api_key: ApiKey = Depends(require_staff("can_enroll_customer")),
):
    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)
    await _run_sync(update_customer, customer, payload.model_dump(exclude_unset=True))
    return {"message": "Customer updated"}


@router.delete("/customer/delete/{customer_number}")
async def customer_delete(
    customer_number: int,
    api_key: ApiKey = Depends(require_staff("can_enroll_customer")),
):
    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)
    await _run_sync(toggle_active, customer)
    return {
        "message": f"Customer {'deactivated' if not customer.is_active else 'reactivated'}",
        "is_active": customer.is_active,
    }


@router.post("/customer/login")
async def customer_login(payload: CustomerLoginPayload):
    account_number = payload.account_number
    registered_name = str(payload.registered_name or "").strip()
    last_receipt = str(payload.last_receipt or "").strip()

    if account_number is None:
        return JSONResponse(
            {"error": "Customer number is required", "error_code": "CUS400"},
            status_code=400,
        )

    result = await session().execute(
        select(Customer).where(
            Customer.customer_number == int(account_number),
            Customer.is_active.is_(True),
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse(
            {"error": "Customer not found", "error_code": "CUS404"}, status_code=404
        )

    if (
        registered_name
        and customer.name
        and customer.name.lower().strip() != registered_name.lower().strip()
    ):
        return JSONResponse(
            {"error": "Name does not match", "error_code": "CUS403"}, status_code=403
        )

    return {
        "customer_number": customer.customer_number,
        "customer": {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address or "",
            "contact_number": customer.contact_number or "",
            "email": customer.email or "",
            "meter_serial_number": customer.meter_serial_number or "",
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
        },
    }


@router.get("/customers/changed")
async def customers_changed(
    request: Request, api_key: ApiKey = Depends(require_staff("can_read_meters"))
):
    try:
        since = int(request.query_params.get("since"))
    except (ValueError, TypeError):
        return JSONResponse(
            {"error": "since parameter is required (Unix timestamp)"}, status_code=400
        )

    try:
        since_dt = datetime.fromtimestamp(since)
    except (ValueError, OSError, OverflowError):
        return JSONResponse({"error": "Invalid since timestamp"}, status_code=400)

    modified_result = await session().execute(
        select(Customer.customer_number).where(
            Customer.date_modified > since_dt, Customer.is_active.is_(True)
        )
    )
    modified_customers = modified_result.all()

    reading_result = await session().execute(
        select(MeterReading.customer_number.distinct()).where(
            or_(
                MeterReading.date_created > since_dt,
                MeterReading.date_modified > since_dt,
            )
        )
    )
    reading_customers = reading_result.all()

    from models import ManagementLog

    dropped_result = await session().execute(
        select(ManagementLog.customer_number.distinct()).where(
            ManagementLog.date_created > since_dt,
            ManagementLog.action_type.in_(["drop", "edit"]),
            ManagementLog.target_type == "reading",
            ManagementLog.customer_number.isnot(None),
        )
    )
    dropped_logs = dropped_result.all()
    dropped_customers = {r[0] for r in dropped_logs if r[0]}

    all_changed = {c[0] for c in modified_customers}
    all_changed.update(c[0] for c in reading_customers)
    all_changed.update(dropped_customers)

    total_result = await session().execute(
        select(func.count()).select_from(Customer).where(Customer.is_active.is_(True))
    )
    return {
        "customer_numbers": list(all_changed),
        "server_time": int(datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp()),
        "total_customers": total_result.scalar() or 0,
    }
