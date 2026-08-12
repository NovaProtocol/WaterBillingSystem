from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from db_async import session
from fee_service import calculate_fee
from models import Customer, PaymentMethod, XenditTransaction

from routes.customer.common import logger

router = APIRouter()


class InvoicePayload(BaseModel):
    amount: float | int | None = None
    payment_method: str = ""
    success_url: str = ""
    cancel_url: str = ""


@router.post("/customer/{customer_number}/invoice")
async def customer_invoice(customer_number: int, payload: InvoicePayload):
    result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    amount = payload.amount
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        amount_float = 0
    if not amount_float or amount_float <= 0:
        return JSONResponse({"error": "Invalid amount"}, status_code=400)

    payment_method = str(payload.payment_method or "")
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

    api_key_str = os.environ["XENDIT_API_KEY"]
    if not api_key_str:
        return JSONResponse({"error": "Xendit not configured"}, status_code=503)

    names = (customer.name or str(customer_number)).strip().split(" ", 1)
    given_names = names[0] or str(customer_number)
    surname = names[1] if len(names) > 1 else ""

    xendit_payload = {
        "reference_id": external_id,
        "session_type": "PAY",
        "mode": "PAYMENT_LINK",
        "amount": total_amount,
        "currency": "PHP",
        "country": "PH",
        "allowed_payment_channels": channels,
        "success_return_url": payload.success_url,
        "cancel_return_url": payload.cancel_url,
        "description": f"Water bill payment - {customer.name or customer_number}",
        "customer": {
            "reference_id": external_id,
            "type": "INDIVIDUAL",
            "individual_detail": {"given_names": given_names},
        },
    }
    if surname:
        xendit_payload["customer"]["individual_detail"]["surname"] = surname
    if customer.email:
        xendit_payload["customer"]["email"] = customer.email
    if customer.contact_number:
        xendit_payload["customer"]["mobile_number"] = customer.contact_number

    auth = base64.b64encode(f"{api_key_str}:".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.xendit.co/sessions",
                json=xendit_payload,
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
