from __future__ import annotations

import datetime
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from shared.errors import install_error_handlers
from shared.logger import attach_sqlite_logging
from shared.middleware import RequestIDMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("api")
http_logger = logging.getLogger("http")


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db_async import engine, init_db, init_engine, session_scope, sync_session

    init_engine()
    await init_db()

    async with session_scope():
        from fee_service import seed_payment_methods
        from preflight import apply, run_preflight

        findings = run_preflight()  # sys.exit(1) on fatal findings
        await apply(findings, engine())  # applies safe DDL (MySQL only)
        await seed_payment_methods()

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

    # gRPC internal server on :50051 (api:50051) — internal-only, not via Caddy
    grpc_server = None
    try:
        from grpc_server import start_grpc_server  # noqa: E402

        grpc_server = await start_grpc_server()
        logger.info("gRPC server running on 0.0.0.0:50051")
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    yield

    if grpc_server is not None:
        try:
            from grpc_server import stop_grpc_server  # noqa: E402

            await stop_grpc_server(grace=5)
        except Exception as e:
            logger.warning("gRPC stop failed: %s", e)


def create_app() -> FastAPI:
    require_env(
        "SECRET_KEY",
        "NFC_PWD_SECRET",
        "XENDIT_API_KEY",
        "XENDIT_WEBHOOK_TOKEN",
        "DEPLOYMENT_TYPE",
    )
    if not os.environ.get("SQLALCHEMY_DATABASE_URI"):
        require_env("DB_ENGINE", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USERNAME", "DB_PASS")

    app = FastAPI(title="Cotta Water Billing API", lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)
    install_error_handlers(app)

    from routes.config import router as config_router
    from routes.customer import router as customer_router
    from routes.debug import router as debug_router
    from routes.staff import router as staff_router
    from routes.system import router as system_router
    from routes.webhooks import webhook_router

    for router in (
        config_router,
        customer_router,
        debug_router,
        staff_router,
        system_router,
        webhook_router,
    ):
        app.include_router(router)

    @app.get("/health")
    async def health():
        try:
            from db_async import session

            await session().execute(text("SELECT 1"))
            return {"status": "ok", "db": "connected"}
        except Exception as e:
            return JSONResponse({"status": "degraded", "db": str(e)}, status_code=503)

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        from db_async import session_scope

        async with session_scope():
            return await call_next(request)

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

    attach_sqlite_logging("api")

    return app


app = create_app()
