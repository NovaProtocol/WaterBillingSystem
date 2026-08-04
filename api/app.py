import datetime
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from shared.logger import attach_sqlite_logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('api')


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db_async import init_db, init_engine, session_scope, sync_session

    init_engine()
    await init_db()

    try:
        from migrate import run_migrations
        from fee_service import seed_payment_methods
        async with session_scope():
            await run_migrations()
            await seed_payment_methods()
    except Exception as e:
        logger.error(f"Startup DB tasks failed: {e}")

    try:
        from services.staff_seeder import ensure_prereq_staff
        await run_in_threadpool(ensure_prereq_staff, sync_session())
    except Exception as e:
        logger.error(f"Staff seeder failed: {e}")

    try:
        from services.guest_seeder import ensure_guest_user
        await run_in_threadpool(ensure_guest_user, sync_session())
    except Exception as e:
        logger.error(f"Guest seeder failed: {e}")

    yield


require_env('SECRET_KEY',
            'NFC_PWD_SECRET', 'XENDIT_API_KEY', 'XENDIT_WEBHOOK_TOKEN',
            'DEPLOYMENT_TYPE')
if not os.environ.get('SQLALCHEMY_DATABASE_URI'):
    require_env('DB_ENGINE', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USERNAME', 'DB_PASS')

app = FastAPI(title="Cotta Water Billing API", lifespan=lifespan)

import routes.config  # noqa: F401  (registers routes on the blueprint)
import routes.customer  # noqa: F401
import routes.debug  # noqa: F401
import routes.staff  # noqa: F401
import routes.system  # noqa: F401
from blueprint import blueprint as api_router  # noqa: E402
from routes.webhooks import webhook_router  # noqa: E402

app.include_router(api_router)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    try:
        from db_async import session
        await session().execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return JSONResponse({"status": "degraded", "db": str(e)}, status_code=503)


attach_sqlite_logging('api')

http_logger = logging.getLogger('http')


@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    from db_async import session_scope

    async with session_scope():
        return await call_next(request)


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
