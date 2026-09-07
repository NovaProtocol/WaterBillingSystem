from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("webhook")

router = APIRouter()

API_BASE_URL = os.environ["API_BASE_URL"]
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]


@router.post("/webhook/xendit")
async def xendit_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    # Xendit webhook is HTTP-exclusive (api:8008 via API_BASE_URL).
    # No gRPC fallback or health probe — fail loud via HTTP status/logs.
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{API_BASE_URL}/api/webhook/xendit-payment",
                json=body,
                headers={
                    "X-Callback-Token": INTERNAL_API_KEY,
                    "User-Agent": "webhook/1.0",
                    "X-Container-Name": "webhook",
                    "Content-Type": "application/json",
                },
            )
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.exception("webhook_proxy_failed", extra={"path": "/webhook/xendit"})
        return JSONResponse(
            {"error": {"code": "UPSTREAM_UNAVAILABLE", "message": str(e), "request_id": request.headers.get("X-Request-ID", "")}},
            status_code=502,
        )
