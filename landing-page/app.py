import datetime
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from shared.config import shared_static_dir
from shared.logger import attach_sqlite_logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('landing-page')


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env('SECRET_KEY', 'DEPLOYMENT_TYPE')

app = FastAPI(title="Cotta Realty Landing")

app.mount('/static', StaticFiles(directory=shared_static_dir()), name='static')

import routes  # noqa: E402  (registers routes on the router)

app.include_router(routes.router)

# Parity with the old Flask endpoints: url_for('landing_blueprint.x') in templates.
for route in routes.router.routes:
    if getattr(route, 'name', None):
        route.name = 'landing_blueprint.' + route.name


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.get('/404', response_class=HTMLResponse)
async def not_found_page(request: Request):
    resp = routes.templates.TemplateResponse(request, 'landing/404.html', {})
    resp.status_code = 404
    return resp


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    resp = routes.templates.TemplateResponse(request, 'landing/404.html', {})
    resp.status_code = 404
    return resp


attach_sqlite_logging('landing-page')

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
