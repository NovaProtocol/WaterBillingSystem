from __future__ import annotations

import logging
import os

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from blueprint import blueprint
from db_async import session
from models import Config as AppConfig
from pricing import DUE_DAYS, LATE_PENALTY, PRICING_TIERS
from utils import require_staff, resolve_api_key

logger = logging.getLogger('api')


@blueprint.get("/config/nfc_secret")
async def config_nfc_secret(request: Request):
    api_key = await resolve_api_key(request)
    if not api_key or not api_key.is_active:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    if not api_key.staff or not (
        api_key.staff.can_read_meters or api_key.staff.can_enroll_customer
    ):
        return JSONResponse({"error": "Permission denied"}, status_code=403)

    result = await session().execute(
        select(AppConfig).where(AppConfig.key == "nfc_generation")
    )
    gen_row = result.scalar_one_or_none()
    generation = int(gen_row.value) if gen_row else 0

    return {
        "nfc_pwd_secret": os.environ["NFC_PWD_SECRET"],
        "nfc_generation": generation,
    }


@blueprint.get("/config/pricing")
async def config_pricing(auth: tuple = Depends(require_staff("can_read_meters"))):
    api_key, err = auth
    if err:
        return err
    return {
        "tiers": PRICING_TIERS,
        "late_penalty": LATE_PENALTY,
        "due_days": DUE_DAYS,
    }
