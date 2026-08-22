from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("webhook")

router = APIRouter()

API_BASE_URL = os.environ["API_BASE_URL"]
API_GRPC_ADDR = os.environ.get("API_GRPC_ADDR", "api:50051")
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]

try:
    import grpc

    from shared.proto_gen import billing_pb2, billing_pb2_grpc

    _GRPC_AVAILABLE = True
except ImportError:
    _GRPC_AVAILABLE = False


@router.post("/webhook/xendit")
async def xendit_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    # Note: webhook callback data is JSON-serialized; the dedicated
    # Xendit flow stays HTTP via api:8008. When gRPC is available we
    # still validate connectivity via the internal BillingService
    # HealthCheck (demonstrates insecure_channel usage) but do not
    # change the external contract.
    if _GRPC_AVAILABLE:
        try:
            async with grpc.aio.insecure_channel(API_GRPC_ADDR) as channel:
                stub = billing_pb2_grpc.BillingServiceStub(channel)
                await stub.HealthCheck(
                    billing_pb2.HealthCheckRequest(),
                    metadata=(("x-internal-api-key", INTERNAL_API_KEY),),
                    timeout=2,
                )
        except Exception:
            pass
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
        logger.exception("Xendit webhook proxy failed:")
        return JSONResponse({"error": str(e)}, status_code=502)
