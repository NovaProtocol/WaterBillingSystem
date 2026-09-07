import datetime
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.config import shared_static_dir
from shared.errors import install_error_handlers
from shared.logger import attach_sqlite_logging
from shared.middleware import RequestIDMiddleware

_TITLES = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 408: "Request Timeout", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("developer-portal")


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env("SECRET_KEY", "INTERNAL_API_KEY", "API_BASE_URL", "DEPLOYMENT_TYPE")

app = FastAPI(title="Cotta Developer Portal")

app.mount("/static", StaticFiles(directory=shared_static_dir()), name="static")

import routes

app.include_router(routes.router)

# Parity with the old Flask endpoints: url_for('dev.x') and
# request.endpoint == 'dev.x' in templates.
for route in routes.router.routes:
    if getattr(route, "name", None):
        route.name = "dev." + route.name

app.add_middleware(RequestIDMiddleware)
install_error_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok", "debug": "enabled"}


from templating import templates as _templates


def _err(request: Request, code: int, title: str, msg: str):
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({"error": title, "code": code}, status_code=code)
    return _templates.TemplateResponse(request, "common/error.html", {"code": code, "title": title, "message": msg}, status_code=code)


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    # Dev login gate uses 302 with Location header – let the redirect through
    if exc.status_code in (301, 302, 303, 307, 308):
        loc = ""
        if getattr(exc, "headers", None):
            loc = exc.headers.get("Location") or exc.headers.get("location") or ""
        if not loc and getattr(exc, "detail", None):
            loc = str(exc.detail) if "/" in str(exc.detail) else ""
        return RedirectResponse(url=loc or "/staff/login", status_code=exc.status_code, headers=getattr(exc, "headers", None))
    code = exc.status_code if exc.status_code in _TITLES else 500
    title = _TITLES.get(code, "Error")
    detail = str(exc.detail) if exc.detail else ""
    if code == 403:
        title = "Access denied"
        msg = (
            detail
            if detail and "permission" in detail.lower()
            else "You do not have permission to access the developer portal."
        )
    elif code == 404:
        msg = "The page you're looking for doesn't exist."
    else:
        msg = detail or title
    return _err(request, code, title, msg)


@app.exception_handler(Exception)
async def _exc(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await _http(request, exc)
    return _err(request, 500, "Internal Server Error", "Something went wrong.")


attach_sqlite_logging("developer-portal")

http_logger = logging.getLogger("http")


@app.middleware("http")
async def log_request(request: Request, call_next):
    response = await call_next(request)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%b/%Y:%H:%M:%S %z")
    referrer = request.headers.get("Referer", "-")
    ua = request.headers.get("User-Agent", "-")
    msg = (
        f"{request.client.host if request.client else '-'} - - [{now}] "
        f'"{request.method} {request.url.path} HTTP/{request.scope.get("http_version", "1.1")}" '
        f"{response.status_code} {response.headers.get('content-length', '-')} "
        f'"{referrer}" "{ua}"'
    )
    http_logger.info(
        msg,
        extra={
            "http": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "remote_addr": request.client.host if request.client else None,
                "container": request.headers.get("X-Container-Name", "-"),
            }
        },
    )
    return response
