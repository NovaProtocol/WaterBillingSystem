import datetime
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from shared.config import shared_static_dir
from shared.logger import attach_sqlite_logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('developer-portal')


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE')

app = FastAPI(title="Cotta Developer Portal")

app.mount('/static', StaticFiles(directory=shared_static_dir()), name='static')

import routes  # noqa: E402  (registers routes on the router)

app.include_router(routes.router)

# Parity with the old Flask endpoints: url_for('dev.x') and
# request.endpoint == 'dev.x' in templates.
for route in routes.router.routes:
    if getattr(route, 'name', None):
        route.name = 'dev.' + route.name


@app.get('/health')
async def health():
    return {'status': 'ok', 'debug': 'enabled'}


attach_sqlite_logging('developer-portal')

http_logger = logging.getLogger('http')


@app.middleware('http')
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
