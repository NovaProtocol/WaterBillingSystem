from __future__ import annotations

import os

import grpc as _grpc

from shared.grpc_client import (
    get_billing_history_via_grpc,
    get_readings_via_grpc,
)
from shared.http_client import make_client

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = make_client(os.environ["API_BASE_URL"], container_name="customer-portal")
    return _client


async def customer_login(account_number: str, name: str = "", last_receipt: str = "") -> dict:
    # HTTP is the exclusive transport for login — no grpc fallback.
    r = await _get_client().post(
        "/api/customer/login",
        json={
            "account_number": int(account_number),
            "registered_name": name,
            "last_receipt": last_receipt,
        },
    )
    r.raise_for_status()
    return r.json()


async def get_billing(customer_number: int) -> dict:
    # HTTP is the exclusive transport for billing context — grpc GetCustomer
    # carries only core fields and would mask failures if used as fallback.
    # Fail loud on HTTP errors; do not silently try grpc.
    r = await _get_client().get(f"/api/customer/{customer_number}")
    r.raise_for_status()
    return r.json()


async def get_readings(customer_number: int, page: int = 1) -> dict:
    # gRPC is the exclusive transport for readings — no HTTP fallback.
    # Any AioRpcError surfaces as 503 at the caller, never masked.
    try:
        data = await get_readings_via_grpc(customer_number, page=page, size=12)  # type: ignore[misc]
    except _grpc.aio.AioRpcError as e:
        if e.code() == _grpc.StatusCode.NOT_FOUND:
            return {"items": [], "page": page, "per_page": 12, "total": 0, "pages": 1}
        raise
    if data is None:
        raise RuntimeError("grpc GetReadings returned no data")
    return {
        "items": data.get("readings", []),
        "page": data.get("page", page),
        "per_page": 12,
        "total": data.get("total", 0),
        "pages": data.get("pages", 1),
    }


async def get_payments(customer_number: int, page: int = 1) -> dict:
    r = await _get_client().get(
        f"/api/customer/{customer_number}/billing", params={"page": page, "size": 10}
    )
    r.raise_for_status()
    data = r.json()
    items = []
    for b in data.get("data", []):
        if b.get("is_paid"):
            ts = b.get("payment_timestamp") or b.get("date_paid") or 0
            b["timestamp"] = ts
            items.append(b)
    return {
        "items": items,
        "page": data.get("meta", {}).get("current_page", page),
        "per_page": data.get("meta", {}).get("page_size", 10),
        "total": len(items),
        "pages": data.get("meta", {}).get("total_pages", 1),
    }


async def get_billing_history(customer_number: int, page: int = 1) -> dict:
    # gRPC is the exclusive transport for billing history — no HTTP fallback.
    try:
        data = await get_billing_history_via_grpc(customer_number, page=page, size=12)  # type: ignore[misc]
    except _grpc.aio.AioRpcError as e:
        if e.code() == _grpc.StatusCode.NOT_FOUND:
            return {"items": [], "page": page, "per_page": 12, "total": 0, "pages": 1}
        raise
    if data is None:
        raise RuntimeError("grpc GetBillingHistory returned no data")
    items = []
    for b in data.get("records", []):
        items.append(
            {
                "month": b.get("month") or "",
                "usage": b.get("consumption") or 0,
                "billed_amount": b.get("billed_amount", 0),
                "penalty": b.get("penalty", 0),
                "paid_amount": b.get("paid_amount") if b.get("is_paid") else None,
            }
        )
    return {
        "items": items,
        "page": data.get("page", page),
        "per_page": 12,
        "total": data.get("total", 0),
        "pages": data.get("pages", 1),
    }


async def create_xendit_invoice(
    customer_number: int,
    amount: float,
    payment_method: str = "",
    success_url: str = "",
    cancel_url: str = "",
) -> dict:
    r = await _get_client().post(
        f"/api/customer/{customer_number}/invoice",
        json={
            "amount": amount,
            "payment_method": payment_method,
            "success_url": success_url,
            "cancel_url": cancel_url,
        },
    )
    r.raise_for_status()
    return r.json()
