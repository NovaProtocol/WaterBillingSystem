from __future__ import annotations

import os

from flask import Response, jsonify, request

from models import ApiKey


def resolve_api_key() -> ApiKey | None:
    auth_header = request.headers.get("Authorization", "")
    api_key_param = request.args.get("api_key", "")
    key_str = ""
    if auth_header.startswith("Bearer "):
        key_str = auth_header[7:]
    elif api_key_param:
        key_str = api_key_param
    if not key_str:
        return None
    return ApiKey.query.filter_by(key=key_str, is_active=True).first()


def _get_staff_id() -> int | None:
    staff_id = request.headers.get("X-Staff-ID", type=int)
    if not staff_id:
        staff_id = (request.get_json(silent=True) or {}).get("staff_id", type=int)
    return staff_id


def require_staff(*perms: str) -> tuple[ApiKey | None, Response | None]:
    internal_key = request.headers.get("X-Internal-API-Key", "")
    if internal_key and internal_key == os.environ.get("INTERNAL_API_KEY", ""):
        return True, None

    api_key = resolve_api_key()
    if not api_key:
        return None, (jsonify({"error": "Authentication required"}), 401)
    if not api_key.staff:
        return None, (jsonify({"error": "Permission denied"}), 403)
    for perm in perms:
        if not getattr(api_key.staff, perm, False):
            return None, (jsonify({"error": "Permission denied"}), 403)
    return api_key, None


def resolve_staff() -> int | None:
    auth = require_staff()
    if auth[1]:
        return None
    api_key = auth[0]
    if api_key is True:
        return _get_staff_id()
    return api_key.staff.id
