from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_async import session
from models import ApiKey


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
    """FastAPI dependency factory. Returns (api_key_or_True, err_or_None) so
    route bodies keep the original Flask shape:
        api_key, err = auth
        if err: return err
    """

    async def _dep(request: Request):
        internal_key = request.headers.get("X-Internal-API-Key", "")
        if internal_key and internal_key == os.environ.get("INTERNAL_API_KEY", ""):
            return True, None

        api_key = await resolve_api_key(request)
        if not api_key:
            return None, JSONResponse({"error": "Authentication required"}, status_code=401)
        if not api_key.staff:
            return None, JSONResponse({"error": "Permission denied"}, status_code=403)
        for perm in perms:
            if not getattr(api_key.staff, perm, False):
                return None, JSONResponse({"error": "Permission denied"}, status_code=403)
        return api_key, None

    return _dep
