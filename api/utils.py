from __future__ import annotations

from flask import request

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
