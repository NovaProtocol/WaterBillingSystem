import datetime
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from shared.config import shared_static_dir, shared_templates_dir
from shared.logger import attach_sqlite_logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('customer-portal')


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE')

app = FastAPI(title="Cotta Customer Portal")

app.mount('/static', StaticFiles(directory=shared_static_dir()), name='static')

templates_env = Environment(
    loader=ChoiceLoader([
        FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')),
        FileSystemLoader(shared_templates_dir()),
    ]),
    autoescape=select_autoescape(['html', 'xml']),
)
templates = Jinja2Templates(env=templates_env)

# pages.py uses the module-level templates object
import pages  # noqa: E402  (registers routes on the router)
import api_routes  # noqa: E402

app.include_router(pages.pages_bp)
app.include_router(api_routes.api_bp)


@app.get('/health')
async def health():
    return {'status': 'ok'}


attach_sqlite_logging('customer-portal')

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
