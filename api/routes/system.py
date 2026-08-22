from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(prefix="/api")
from db_async import session

logger = logging.getLogger("api")


@router.get("/health")
async def health():
    try:
        await session().execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Health check DB query failed:")
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
