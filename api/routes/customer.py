from __future__ import annotations

import base64
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from blueprint import blueprint
from billing_service import ensure_penalty
from customer_service import (
    create_customer,
    list_customers,
    recalc_total_due,
    toggle_active,
    update_customer,
)
from db_async import session, sync_session
from fee_service import calculate_fee
from models import (
    ApiKey,
    Billing,
    Config,
    Customer,
    ManagementLog,
    MeterReading,
    NfcTag,
    PaymentMethod,
    XenditTransaction,
)
from pricing import PRICING_TIERS
from reading_service import (
    drop_reading as service_drop_reading,
    edit_reading as service_edit_reading,
    upload_reading as service_upload_reading,
)
from services.payment_service import (
    drop_payment as service_drop_payment,
    submit_payment as service_submit_payment,
)
from utils import get_staff_id, require_staff

logger = logging.getLogger('api')


def _run_sync(fn, *args, **kwargs):
    def _call():
        s = sync_session()
        try:
            return fn(*args, session=s, **kwargs)
        finally:
            s.close()

    return run_in_threadpool(_call)


@blueprint.get("/customer/count")
async def customer_count(auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err
    result = await session().execute(
        select(func.count()).select_from(Customer).where(Customer.is_active.is_(True))
    )
    return {"count": result.scalar() or 0}


@blueprint.get("/customer/all")
async def customer_all(request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err
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
        list_customers, page=page, per_page=size, q=q or None,
        sort_by=sort_by, sort_dir=sort_dir,
    )

    cnums = [c.customer_number for c in items]
    nfc_map: dict[str, str] = {}
    if cnums:
        result = await session().execute(
            select(NfcTag.customer_number, NfcTag.uid).where(
                NfcTag.customer_number.in_(cnums)
            )
        )
        nfc_map = {row[0]: row[1] for row in result.all()}

    customers_data = []
    for c in items:
        customers_data.append({
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
        })
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


@blueprint.get("/customer/{customer_number}")
async def customer_info(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    """Get full billing details for a specific customer."""
    api_key, err = auth
    if err:
        return err

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
        staff_filter = int(request.query_params.get("staff_id")) if request.query_params.get("staff_id") else None
    except (ValueError, TypeError):
        staff_filter = None
    try:
        token_filter = int(request.query_params.get("token_id")) if request.query_params.get("token_id") else None
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
    readings_result = await session().execute(
        readings_query.order_by(desc(MeterReading.timestamp))
    )
    readings = readings_result.scalars().unique().all()

    latest_reading = readings[0] if len(readings) > 0 else None
    last_reading = readings[1] if len(readings) > 1 else None

    consumption = (
        float(round(latest_reading.reading_value - last_reading.reading_value, 2))
        if latest_reading and last_reading
        else 0
    )

    # Query stored bills for this customer
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

    # Separate into unpaid and paid
    unpaid_bills_list: list[Billing] = []
    paid_bills_list: list[Billing] = []
    for b in all_bills:
        if not b.is_paid:
            await ensure_penalty(b)
            unpaid_bills_list.append(b)
        else:
            paid_bills_list.append(b)

    # Build unpaid bills display
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
        select(func.sum(Billing.carryover_offset)).where(
            Billing.customer_number == customer_number
        )
    )
    total_carryover = carryover_result.scalar() or 0
    balance = float(total_carryover)
    total_due = max(0, total_unpaid + total_penalties - balance)

    due_date = None
    days_remaining = None
    if unpaid_bills:
        due_dt = datetime.fromtimestamp(unpaid_bills[0]["timestamp"], tz=timezone.utc).replace(tzinfo=None) + timedelta(days=7)
        due_date = due_dt.strftime("%m-%d-%Y")
        days_remaining = max(0, (due_dt - datetime.now(tz=timezone.utc).replace(tzinfo=None)).days)

    # Build billing items with reading history
    reading_pairs = []
    for i in range(len(readings)):
        curr = readings[i]
        prev = readings[i + 1] if i + 1 < len(readings) else None
        cons = float(round(curr.reading_value - prev.reading_value, 2)) if prev else 0.0

        # Find the bill for this reading
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

    # Determine the latest receipt group for waterfall undo.
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

    # Recent payments: find bills that have been paid
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

    # Estimated bill for latest consumption only (for display consistency)
    from pricing import compute_water_bill
    water_bill, bill_breakdown = compute_water_bill(consumption) if consumption > 0 else (0.0, [])
    carryover = abs(float(total_carryover))
    balance = float(total_carryover)
    latest_unpaid = len(unpaid_bills) > 0

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
                "cashier": (
                    (b.cashier.name or b.cashier.username) if b.cashier else None
                ),
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


@blueprint.get("/customer/{customer_number}/details")
async def customer_details(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    """Get customer profile with recent reading history."""
    api_key, err = auth
    if err:
        return err

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


@blueprint.post("/customer/new")
async def customer_new(request: Request, auth: tuple = Depends(require_staff("can_enroll_customer"))):
    api_key, err = auth
    if err:
        return err
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    customer, error = await _run_sync(create_customer, data)
    if error:
        status = 409 if "already exists" in error else 400
        return JSONResponse({"error": error}, status_code=status)
    return JSONResponse({
        "message": "Customer created",
        "customer_number": customer.customer_number,
    }, status_code=201)


@blueprint.put("/customer/update/{customer_number}")
async def customer_update(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_enroll_customer"))):
    api_key, err = auth
    if err:
        return err
    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    await _run_sync(update_customer, customer, data)
    return {"message": "Customer updated"}


@blueprint.delete("/customer/delete/{customer_number}")
async def customer_delete(customer_number: int, auth: tuple = Depends(require_staff("can_enroll_customer"))):
    api_key, err = auth
    if err:
        return err
    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)
    await _run_sync(toggle_active, customer)
    return {
        "message": f'Customer {"deactivated" if not customer.is_active else "reactivated"}',
        "is_active": customer.is_active,
    }


@blueprint.post("/customer/login")
async def customer_login(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    account_number = data.get("account_number")
    registered_name = str(data.get("registered_name", "") or "").strip()
    last_receipt = str(data.get("last_receipt", "") or "").strip()

    if account_number is None:
        return JSONResponse({"error": "Customer number is required", "error_code": "CUS400"}, status_code=400)

    result = await session().execute(
        select(Customer).where(
            Customer.customer_number == int(account_number),
            Customer.is_active.is_(True),
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found", "error_code": "CUS404"}, status_code=404)

    if registered_name and customer.name and customer.name.lower().strip() != registered_name.lower().strip():
        return JSONResponse({"error": "Name does not match", "error_code": "CUS403"}, status_code=403)

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
        }
    }


@blueprint.post("/customer/{customer_number}/invoice")
async def customer_invoice(customer_number: int, request: Request):
    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    amount = data.get("amount", 0)
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        amount_float = 0
    if not amount_float or amount_float <= 0:
        return JSONResponse({"error": "Invalid amount"}, status_code=400)

    payment_method = str(data.get("payment_method", "") or "")
    if not payment_method:
        return JSONResponse({"error": "Payment method is required"}, status_code=400)

    method_result = await session().execute(
        select(PaymentMethod).where(
            PaymentMethod.code == payment_method,
            PaymentMethod.is_active.is_(True),
        )
    )
    method = method_result.scalar_one_or_none()
    method_xendit_fee = float(method.xendit_fee) if method and method.xendit_fee else 0

    fee_rate, fee_amount = await calculate_fee(amount_float, payment_method)
    total_amount = round(amount_float + fee_amount + method_xendit_fee, 2)

    external_id = f"wbs-{customer_number}-{int(datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp())}-{secrets.token_hex(4)}"

    channels = [method.channel_code] if method and method.channel_code else []

    api_key_str = os.environ.get("XENDIT_API_KEY", "")
    if not api_key_str:
        return JSONResponse({"error": "Xendit not configured"}, status_code=503)

    names = (customer.name or str(customer_number)).strip().split(" ", 1)
    given_names = names[0] or str(customer_number)
    surname = names[1] if len(names) > 1 else ""

    payload = {
        "reference_id": external_id,
        "session_type": "PAY",
        "mode": "PAYMENT_LINK",
        "amount": total_amount,
        "currency": "PHP",
        "country": "PH",
        "allowed_payment_channels": channels,
        "success_return_url": data.get("success_url", ""),
        "cancel_return_url": data.get("cancel_url", ""),
        "description": f"Water bill payment - {customer.name or customer_number}",
        "customer": {
            "reference_id": external_id,
            "type": "INDIVIDUAL",
            "individual_detail": {"given_names": given_names},
        },
    }
    if surname:
        payload["customer"]["individual_detail"]["surname"] = surname
    if customer.email:
        payload["customer"]["email"] = customer.email
    if customer.contact_number:
        payload["customer"]["mobile_number"] = customer.contact_number

    auth = base64.b64encode(f"{api_key_str}:".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.xendit.co/sessions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth}",
                },
            )
            if resp.status_code >= 400:
                error_body = resp.text
                logger.exception(f"Xendit HTTPError for customer {customer_number}: {error_body}")
                return JSONResponse({"error": f"Xendit error: {error_body}"}, status_code=502)
            session_data = resp.json()
    except Exception as e:
        logger.exception(f"Invoice failed for customer {customer_number}:")
        return JSONResponse({"error": f"Unexpected error: {str(e)}"}, status_code=500)

    session_id = session_data.get("payment_session_id", "")
    payment_link_url = session_data.get("payment_link_url", "")
    if not payment_link_url:
        return JSONResponse({"error": "No redirect URL from Xendit"}, status_code=502)

    txn = XenditTransaction(
        customer_number=customer_number,
        xendit_pr_id=session_id,
        external_id=external_id,
        amount=total_amount,
        base_amount=amount_float,
        fee_amount=fee_amount,
        fee_rate=fee_rate,
        payment_method=payment_method,
        status="PENDING",
    )
    session().add(txn)
    await session().commit()

    return {
        "redirect_url": payment_link_url,
        "external_id": external_id,
        "id": session_id,
        "base_amount": float(amount_float),
        "fee_amount": fee_amount,
        "fee_rate": fee_rate,
    }


# ── Reading CRUD ────────────────────────────────────────────────────────


@blueprint.get("/customer/{customer_number}/reading")
async def customer_readings(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err

    try:
        page = int(request.query_params.get("page", "1"))
    except (ValueError, TypeError):
        page = 1
    try:
        size = int(request.query_params.get("size", "50"))
    except (ValueError, TypeError):
        size = 50

    count_result = await session().execute(
        select(func.count()).select_from(MeterReading).where(
            MeterReading.customer_number == customer_number
        )
    )
    total = count_result.scalar() or 0

    result = await session().execute(
        select(MeterReading)
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .where(MeterReading.customer_number == customer_number)
        .order_by(desc(MeterReading.timestamp))
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        {
            "id": r.id,
            "reading_value": float(r.reading_value),
            "reader": r.token.staff.name if r.token and r.token.staff else None,
            "timestamp": int(r.timestamp.timestamp()),
        }
        for r in result.scalars().unique().all()
    ]
    pages = max(1, (total + size - 1) // size) if size else 1
    return {
        "data": items,
        "meta": {
            "current_page": page,
            "page_size": size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@blueprint.post("/customer/{customer_number}/reading/new")
async def customer_reading_new(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    reading_value = data.get("reading_value")
    timestamp = data.get("timestamp", datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp())
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    staff_name = data.get("staff_name") if api_key is True else api_key.staff.name

    if reading_value is None:
        return JSONResponse({"error": "reading_value is required"}, status_code=400)

    try:
        reading_float = float(reading_value)
        ts_float = float(timestamp)
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid reading_value or timestamp"}, status_code=400)

    if api_key is True:
        token_result = await session().execute(
            select(ApiKey).where(ApiKey.is_active.is_(True)).limit(1)
        )
        token = token_result.scalar_one_or_none()
        token_id = token.id if token else None
    else:
        token_id = api_key.id
    reading, error, status = await _run_sync(
        service_upload_reading, customer_number, reading_float, ts_float,
        token_id, staff_id, staff_name,
    )
    if error:
        return JSONResponse({"error": error}, status_code=status)

    return JSONResponse({
        "success": True,
        "reading_id": reading.id,
        "customer_number": customer_number,
        "reading_value": float(reading_value),
        "timestamp": int(timestamp),
        "reader": staff_name,
    }, status_code=201)


@blueprint.post("/customer/{customer_number}/reading/drop")
async def customer_reading_drop(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_drop_reading"))):
    api_key, err = auth
    if err:
        return err

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    reading_id = data.get("reading_id")
    reason = str(data.get("reason", "") or "").strip()
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    if not reading_id:
        return JSONResponse({"error": "reading_id is required"}, status_code=400)
    if not reason:
        return JSONResponse({"error": "Reason is required"}, status_code=400)
    try:
        await _run_sync(service_drop_reading, reading_id, staff_id, reason)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    return {"message": "Reading dropped"}


@blueprint.post("/customer/{customer_number}/reading/edit")
async def customer_reading_edit(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_manage_billing"))):
    api_key, err = auth
    if err:
        return err

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    reading_id = data.get("reading_id")
    try:
        new_value = float(data.get("reading_value", 0))
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid reading value"}, status_code=400)
    if not reading_id:
        return JSONResponse({"error": "reading_id is required"}, status_code=400)
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    await _run_sync(service_edit_reading, reading_id, new_value, staff_id)
    return {"message": "Reading updated"}


@blueprint.get("/customers/changed")
async def customers_changed(request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err

    try:
        since = int(request.query_params.get("since"))
    except (ValueError, TypeError):
        return JSONResponse({"error": "since parameter is required (Unix timestamp)"}, status_code=400)

    try:
        since_dt = datetime.fromtimestamp(since)
    except (ValueError, OSError, OverflowError):
        return JSONResponse({"error": "Invalid since timestamp"}, status_code=400)

    modified_result = await session().execute(
        select(Customer.customer_number)
        .where(Customer.date_modified > since_dt, Customer.is_active.is_(True))
    )
    modified_customers = modified_result.all()

    reading_result = await session().execute(
        select(MeterReading.customer_number.distinct())
        .where(
            or_(
                MeterReading.date_created > since_dt,
                MeterReading.date_modified > since_dt,
            )
        )
    )
    reading_customers = reading_result.all()

    dropped_result = await session().execute(
        select(ManagementLog.customer_number.distinct())
        .where(
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


# ── Billing CRUD ────────────────────────────────────────────────────────


@blueprint.get("/customer/{customer_number}/billing")
async def customer_billing(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err

    try:
        page = int(request.query_params.get("page", "1"))
    except (ValueError, TypeError):
        page = 1
    try:
        size = int(request.query_params.get("size", "50"))
    except (ValueError, TypeError):
        size = 50

    count_result = await session().execute(
        select(func.count()).select_from(Billing).where(
            Billing.customer_number == customer_number
        )
    )
    total = count_result.scalar() or 0

    result = await session().execute(
        select(Billing)
        .options(selectinload(Billing.reading))
        .where(Billing.customer_number == customer_number)
        .order_by(desc(Billing.date_created))
        .offset((page - 1) * size)
        .limit(size)
    )
    billings = result.scalars().all()
    items = []
    for b in billings:
        await ensure_penalty(b)
        reading = b.reading
        items.append({
            "id": b.id,
            "reading_id": b.reading_id,
            "month": reading.timestamp.strftime("%B %Y") if reading else None,
            "previous_reading": float(b.previous_reading_value) if b.previous_reading_value else None,
            "current_reading": float(b.current_reading_value) if b.current_reading_value else None,
            "consumption": float(b.consumption) if b.consumption else None,
            "billed_amount": float(b.billed_amount),
            "penalty": float(b.penalty),
            "paid_amount": float(b.paid_amount),
            "is_paid": b.is_paid,
            "receipt_number": b.receipt_number,
            "cashier_id": b.cashier_id,
            "payment_timestamp": int(b.payment_timestamp.timestamp()) if b.payment_timestamp else None,
            "date_paid": int(b.date_paid.timestamp()) if b.date_paid else None,
            "created_at": int(b.date_created.timestamp()) if b.date_created else None,
        })
    pages = max(1, (total + size - 1) // size) if size else 1
    return {
        "data": items,
        "meta": {
            "current_page": page,
            "page_size": size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@blueprint.post("/customer/{customer_number}/billing/new")
async def customer_billing_new(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_accept_payment"))):
    api_key, err = auth
    if err:
        return err

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    amount = data.get("amount", 0)
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid payment amount"}, status_code=400)
    if amount_float <= 0:
        return JSONResponse({"error": "Amount must be positive"}, status_code=400)

    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    result, error, status = await _run_sync(service_submit_payment, customer_number, amount_float, staff_id)
    if error:
        return JSONResponse({"error": error}, status_code=status)
    return JSONResponse(result, status_code=status)


@blueprint.post("/customer/{customer_number}/billing/drop")
async def customer_billing_drop(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_drop_payment"))):
    api_key, err = auth
    if err:
        return err

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    billing_id = data.get("billing_id")
    reason = str(data.get("reason", "") or "").strip()
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    if not billing_id:
        return JSONResponse({"error": "billing_id is required"}, status_code=400)
    if not reason:
        return JSONResponse({"error": "Reason is required"}, status_code=400)

    billing = await session().get(Billing, billing_id)
    if not billing:
        return JSONResponse({"error": "Billing record not found"}, status_code=404)
    if not billing.is_paid:
        return JSONResponse({"error": "Bill is not paid"}, status_code=400)

    result = await _run_sync(service_drop_payment, billing_id, staff_id, reason)
    if result and "error" in result:
        return JSONResponse(result, status_code=400)
    return result or {"message": "Payment dropped"}


# ── NFC ──────────────────────────────────────────────────────────────────


@blueprint.get("/customer/{customer_number}/nfc")
async def customer_nfc(customer_number: int, auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err

    result = await session().execute(
        select(NfcTag).where(NfcTag.customer_number == customer_number)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        return {"nfc_uid": None}

    return {
        "nfc_uid": tag.uid,
        "customer_number": tag.customer_number,
    }


@blueprint.get("/customer/all/nfc")
async def customer_all_nfc(auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err

    result = await session().execute(
        select(NfcTag).order_by(desc(NfcTag.date_created))
    )
    tags = result.scalars().all()
    return {
        "tags": [
            {"uid": t.uid, "customer_number": t.customer_number}
            for t in tags
        ]
    }


@blueprint.post("/customer/{customer_number}/nfc/create")
async def customer_nfc_create(customer_number: int, request: Request, auth: tuple = Depends(require_staff("can_enroll_customer"))):
    api_key, err = auth
    if err:
        return err

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    uid = str(data.get("uid", "") or "").strip()
    if not uid:
        return JSONResponse({"error": "uid is required"}, status_code=400)

    existing_result = await session().execute(
        select(NfcTag).where(NfcTag.uid == uid)
    )
    if existing_result.scalar_one_or_none():
        return JSONResponse({"error": "Tag UID already assigned"}, status_code=409)

    customer_result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    if api_key is True:
        enrolled_by = await get_staff_id(request) or 1
    else:
        enrolled_by = api_key.staff.id

    tag = NfcTag(uid=uid, customer_number=customer_number, enrolled_by_id=enrolled_by)
    session().add(tag)
    customer.date_modified = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    await session().commit()

    return JSONResponse({"message": "Tag assigned", "uid": uid, "customer_number": customer_number}, status_code=201)


@blueprint.post("/customer/{customer_number}/nfc/delete")
async def customer_nfc_delete(customer_number: int, auth: tuple = Depends(require_staff("can_enroll_customer"))):
    api_key, err = auth
    if err:
        return err

    tag_result = await session().execute(
        select(NfcTag).where(NfcTag.customer_number == customer_number)
    )
    tag = tag_result.scalar_one_or_none()
    if not tag:
        return JSONResponse({"error": "No NFC tag assigned to this customer"}, status_code=404)

    customer_result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = customer_result.scalar_one_or_none()
    await session().delete(tag)

    gen_result = await session().execute(
        select(Config).where(Config.key == "nfc_generation")
    )
    gen_row = gen_result.scalar_one_or_none()
    if gen_row:
        gen_row.value = str(int(gen_row.value) + 1)
    else:
        session().add(Config(key="nfc_generation", value="1"))

    if customer:
        customer.date_modified = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    await session().commit()

    return {"message": "Tag deleted", "uid": tag.uid}
