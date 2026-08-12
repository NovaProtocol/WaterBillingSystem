from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from billing_service import ensure_penalty
from db_async import session
from models import ApiKey, Billing
from services.payment_service import (
    drop_payment as service_drop_payment,
    submit_payment as service_submit_payment,
)
from utils import require_staff

from routes.customer.common import _run_sync

router = APIRouter()


class BillingNewPayload(BaseModel):
    amount: float | None = None
    staff_id: int | None = None


class BillingDropPayload(BaseModel):
    billing_id: int | None = None
    reason: str = ""
    staff_id: int | None = None


@router.get("/customer/{customer_number}/billing")
async def customer_billing(customer_number: int, request: Request, api_key: ApiKey = Depends(require_staff("can_read_meters"))):

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


@router.post("/customer/{customer_number}/billing/new")
async def customer_billing_new(customer_number: int, payload: BillingNewPayload, api_key: ApiKey = Depends(require_staff("can_accept_payment"))):

    amount = payload.amount
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid payment amount"}, status_code=400)
    if amount_float <= 0:
        return JSONResponse({"error": "Amount must be positive"}, status_code=400)

    staff_id = payload.staff_id if api_key is True else api_key.staff.id
    result, error, status = await _run_sync(service_submit_payment, customer_number, amount_float, staff_id)
    if error:
        return JSONResponse({"error": error}, status_code=status)
    return JSONResponse(result, status_code=status)


@router.post("/customer/{customer_number}/billing/drop")
async def customer_billing_drop(customer_number: int, payload: BillingDropPayload, api_key: ApiKey = Depends(require_staff("can_drop_payment"))):

    billing_id = payload.billing_id
    reason = str(payload.reason or "").strip()
    staff_id = payload.staff_id if api_key is True else api_key.staff.id
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
