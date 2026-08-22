from __future__ import annotations

import os
import secrets

from db_async import session
from fastapi import HTTPException, Request
from models import ApiKey
from sqlalchemy import select
from sqlalchemy.orm import selectinload


async def resolve_api_key(request: Request) -> ApiKey | None:
    auth_header = request.headers.get("Authorization", "")
    api_key_param = request.query_params.get("api_key", "")
    key_str = ""
    if auth_header.startswith("Bearer "):
        key_str = auth_header[7:]
    elif api_key_param:
        key_str = api_key_param
    if not key_str:
        return None
    result = await session().execute(
        select(ApiKey)
        .options(selectinload(ApiKey.staff))
        .where(ApiKey.key == key_str, ApiKey.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def json_body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def get_staff_id(request: Request) -> int | None:
    header = request.headers.get("X-Staff-ID")
    if header:
        try:
            return int(header)
        except (ValueError, TypeError):
            pass
    body = await json_body(request)
    try:
        return int(body.get("staff_id")) if body.get("staff_id") is not None else None
    except (ValueError, TypeError):
        return None


def require_staff(*perms: str):
    """FastAPI dependency factory. Returns the ApiKey (or True for the
    internal key) on success; raises HTTPException on auth failure."""

    async def _dep(request: Request):
        internal_key = request.headers.get("X-Internal-API-Key", "")
        if internal_key and secrets.compare_digest(internal_key, os.environ["INTERNAL_API_KEY"]):
            return True

        api_key = await resolve_api_key(request)
        if not api_key:
            raise HTTPException(status_code=401, detail={"error": "Authentication required"})
        if not api_key.staff:
            raise HTTPException(status_code=403, detail={"error": "Permission denied"})
        for perm in perms:
            if not getattr(api_key.staff, perm, False):
                raise HTTPException(status_code=403, detail={"error": "Permission denied"})
        return api_key

    return _dep
