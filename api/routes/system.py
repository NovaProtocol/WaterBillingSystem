from __future__ import annotations

import logging

from sqlalchemy import text

from blueprint import blueprint
from db_async import session

logger = logging.getLogger('api')


@blueprint.get("/health")
async def health():
    try:
        await session().execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Health check DB query failed:")
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
