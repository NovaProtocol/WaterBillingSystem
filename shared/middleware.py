from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

try:
    import structlog.contextvars as _ctx  # type: ignore

    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Bind request_id (+ account_id when resolvable) into structlog contextvars.

    Reads ``X-Request-ID`` or generates ``uuid4().hex``, binds to contextvars
    so ``structlog`` JSON lines carry it, echoes on response, exposes via CORS.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        if _HAS_STRUCTLOG:
            try:
                _ctx.bind_contextvars(request_id=request_id)
            except Exception:
                pass
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            existing = response.headers.get("Access-Control-Expose-Headers", "")
            expose = "X-Request-ID"
            if existing:
                parts = {p.strip() for p in existing.split(",") if p.strip()}
                parts.add(expose)
                response.headers["Access-Control-Expose-Headers"] = ", ".join(sorted(parts))
            else:
                response.headers["Access-Control-Expose-Headers"] = expose
            return response
        finally:
            if _HAS_STRUCTLOG:
                try:
                    _ctx.unbind_contextvars("request_id")
                except Exception:
                    pass
