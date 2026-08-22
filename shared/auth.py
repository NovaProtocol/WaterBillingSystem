from __future__ import annotations

import os

from itsdangerous import URLSafeTimedSerializer

SALT = "portal-session"
MAX_AGE = 3600

_serializer = URLSafeTimedSerializer(os.environ["SECRET_KEY"], salt=SALT)


def make_token(payload: dict) -> str:
    return _serializer.dumps(payload)


def load_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=MAX_AGE)
    except Exception:
        return None
