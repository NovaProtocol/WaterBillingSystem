import datetime
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from shared.config import shared_static_dir, shared_templates_dir
from shared.errors import install_error_handlers
from shared.logger import attach_sqlite_logging
from shared.middleware import CacheControlMiddleware, RequestIDMiddleware

_TITLES = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 408: "Request Timeout", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("customer-portal")


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env("SECRET_KEY", "INTERNAL_API_KEY", "API_BASE_URL", "DEPLOYMENT_TYPE")

app = FastAPI(title="Water Billing Customer Portal")

app.mount("/static", StaticFiles(directory=shared_static_dir()), name="static")

templates_env = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
            FileSystemLoader(shared_templates_dir()),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
)
templates = Jinja2Templates(env=templates_env)

# pages.py uses the module-level templates object
import api_routes
import pages

app.include_router(pages.pages_bp)
app.include_router(api_routes.api_bp)
_DEBUG_DEPLOY = os.environ.get("DEPLOYMENT_TYPE", "").lower() in ("debug", "development")
app.add_middleware(RequestIDMiddleware)
app.add_middleware(CacheControlMiddleware, is_debug=_DEBUG_DEPLOY)
install_error_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Keep HTML error page for browser navigations; JSON envelope is handled by shared/errors
def _err(request: Request, code: int, title: str, msg: str):
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({"error": {"code": _TITLES.get(code, "Error"), "message": msg, "request_id": getattr(request.state, "request_id", "")}}, status_code=code)
    return templates.TemplateResponse(request, "common/error.html", {"code": code, "title": title, "message": msg}, status_code=code)


attach_sqlite_logging("customer-portal")

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
