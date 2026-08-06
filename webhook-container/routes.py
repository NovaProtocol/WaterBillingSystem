import logging
import os
import sys

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from shared.logger import attach_sqlite_logging

logger = logging.getLogger('webhook')

router = APIRouter()

API_BASE_URL = os.environ['API_BASE_URL']
INTERNAL_API_KEY = os.environ['INTERNAL_API_KEY']


@router.post('/webhook/xendit')
async def xendit_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{API_BASE_URL}/api/webhook/xendit-payment",
                json=body,
                headers={
                    'X-Callback-Token': INTERNAL_API_KEY,
                    'User-Agent': 'webhook/1.0',
                    'X-Container-Name': 'webhook',
                    'Content-Type': 'application/json',
                },
            )
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.exception(f"Xendit webhook proxy failed:")
        return JSONResponse({'error': str(e)}, status_code=502)
