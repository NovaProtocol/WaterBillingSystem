from __future__ import annotations

import os
import secrets

from db_async import session
from fastapi import HTTPException, Request
from models import ApiKey, Staff
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
    internal key) on success; raises HTTPException on auth failure.

    When called via the internal portal (X-Internal-API-Key), perms are
    re-checked against the staff identified by X-Staff-ID header/body if
    present. This prevents the blanket bypass that made portal perm checks
    cosmetic. For audit-sensitive routes (debug) the portal now forwards
    staff context via X-Staff-* headers."""

    async def _dep(request: Request):
        internal_key = request.headers.get("X-Internal-API-Key", "")
        if internal_key and secrets.compare_digest(internal_key, os.environ["INTERNAL_API_KEY"]):
            if not perms:
                return True
            # Re-derive staff from X-Staff-ID for internal callers when perms are required
            sid = await get_staff_id(request)
            hdr_sid = request.headers.get("X-Staff-ID") or request.headers.get("X-Staff-Id")
            if hdr_sid and not sid:
                try:
                    sid = int(hdr_sid)
                except Exception:
                    sid = None
            if sid:
                res = await session().execute(select(Staff).where(Staff.id == sid))
                st = res.scalar_one_or_none()
                if st:
                    if any(getattr(st, perm, False) for perm in perms):
                        return True
                    raise HTTPException(status_code=403, detail={"error": "Permission denied"})
            # No staff context forwarded — fall through to require explicit staff header
            raise HTTPException(status_code=403, detail={"error": "Permission denied — staff context required"})

        api_key = await resolve_api_key(request)
        if not api_key:
            raise HTTPException(status_code=401, detail={"error": "Authentication required"})
        if not api_key.staff:
            raise HTTPException(status_code=403, detail={"error": "Permission denied"})
        if perms and not any(getattr(api_key.staff, perm, False) for perm in perms):
            raise HTTPException(status_code=403, detail={"error": "Permission denied"})
        return api_key

    return _dep
