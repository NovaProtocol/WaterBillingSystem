from __future__ import annotations

import secrets
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import auth

CSRF_SESSION_KEY = 'csrf_token'
CSRF_HEADER = 'X-CSRF-Token'
CSRF_FIELD = 'csrf_token'
UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def mint_csrf(session_payload: dict) -> str:
    token = secrets.token_urlsafe(32)
    session_payload[CSRF_SESSION_KEY] = token
    return token


def session_csrf(session_payload: dict | None) -> str | None:
    if not session_payload:
        return None
    return session_payload.get(CSRF_SESSION_KEY)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Stateless CSRF for signed-cookie sessions.

    The token lives inside the signed session payload (exposed to templates
    via the request context). Verified on unsafe methods from the
    X-CSRF-Token header or the `csrf_token` form field. Exempted paths are
    passed through untouched (webhooks, API relays, etc.).
    """

    def __init__(self, app, *, exempt_prefixes: tuple[str, ...] = ()):
        super().__init__(app)
        self.exempt_prefixes = exempt_prefixes

    async def dispatch(self, request: Request, call_next):
        if request.method not in UNSAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in self.exempt_prefixes):
            return await call_next(request)

        session_payload = auth.load_token(request.cookies.get('session'))
        expected = session_csrf(session_payload)
        if expected is None:
            from starlette.responses import JSONResponse
            return JSONResponse({'error': 'CSRF token missing from session'}, status_code=403)

        provided = request.headers.get(CSRF_HEADER)
        if provided is None:
            try:
                form = await request.form()
            except Exception:
                form = {}
            provided = form.get(CSRF_FIELD)

        if not provided or not secrets.compare_digest(provided, expected):
            from starlette.responses import JSONResponse
            return JSONResponse({'error': 'CSRF token mismatch'}, status_code=403)

        return await call_next(request)


class RateLimiter:
    """In-memory sliding-window rate limiter (per process)."""

    def __init__(self, limit: int = 10, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._hits[key] if now - t < self.window]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
