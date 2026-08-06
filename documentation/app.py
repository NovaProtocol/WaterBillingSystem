import datetime
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from shared.logger import attach_sqlite_logging


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env('SECRET_KEY', 'DEPLOYMENT_TYPE')

SITE_DIR = Path(__file__).resolve().parent / "site"

app = FastAPI(title="Cotta Water Billing Docs")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def index():
    return FileResponse(SITE_DIR / "index.html")


@app.get("/{path:path}")
async def serve_docs(path: str):
    if not path:
        path = "index.html"
    parts = path.rstrip("/")
    candidates = [parts, os.path.join(parts, "index.html"), parts + ".html"]
    for c in candidates:
        full = os.path.normpath(os.path.join(str(SITE_DIR), c))
        if (full == str(SITE_DIR) or full.startswith(str(SITE_DIR) + os.sep)) and os.path.isfile(full):
            return FileResponse(full)
    return JSONResponse({"error": "Not found"}, status_code=404)


attach_sqlite_logging('documentation')

http_logger = logging.getLogger('http')


@app.middleware("http")
async def log_request(request: Request, call_next):
    response = await call_next(request)
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%d/%b/%Y:%H:%M:%S %z')
    referrer = request.headers.get('Referer', '-')
    ua = request.headers.get('User-Agent', '-')
    msg = (f'{request.client.host if request.client else "-"} - - [{now}] '
           f'"{request.method} {request.url.path} HTTP/{request.scope.get("http_version", "1.1")}" '
           f'{response.status_code} {response.headers.get("content-length", "-")} '
           f'"{referrer}" "{ua}"')
    http_logger.info(msg, extra={
        'http': {
            'method': request.method,
            'path': request.url.path,
            'status_code': response.status_code,
            'remote_addr': request.client.host if request.client else None,
            'container': request.headers.get('X-Container-Name', '-'),
        }
    })
    return response
