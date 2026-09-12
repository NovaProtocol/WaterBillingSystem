# API Container Setup

## Docker

`python:3.14-slim` base image, runs **granian** (ASGI, 1 worker). There is no Gunicorn and no Flask.

### Dockerfile

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN pip3 install --no-cache-dir -r /app/shared/requirements.txt
COPY shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY api/ /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8008
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8008", "--workers", "1", "app:app"]
```

Key points:
- `python:3.14-slim` base
- `shared/` module copied separately and added to `PYTHONPATH`
- granian ASGI, 1 worker
- Bytecode compilation for faster startup
- Internal port 8008

### Environment Variables

All from `.env` (`.env.example` is the source of truth). Every one is **required** — `compose.yaml` uses `${VAR:?}` so missing values refuse to start; the app's `require_env()` / `shared/config.py` crash the container on boot if anything is unset.

| Variable | Description |
|----------|-------------|
| `DEPLOYMENT_TYPE` | `DEBUG` or `PRODUCTION` |
| `SECRET_KEY` | Session/cookie signing key |
| `INTERNAL_API_KEY` | Internal service-to-service auth key |
| `API_BASE_URL` | Internal API endpoint (`http://api:8008`) |
| `NFC_PWD_SECRET` | Seed for NFC tag password derivation |
| `XENDIT_API_KEY` | Xendit API secret key |
| `XENDIT_WEBHOOK_TOKEN` | Xendit webhook verification token |
| `DB_ENGINE` | e.g., `mysql+pymysql` (async driver aiomysql is swapped in at runtime) |
| `DB_NAME` | Database name |
| `DB_HOST` | Database host (Docker: `mysql-db`) |
| `DB_PORT` | Database port (`3306`) |
| `DB_USERNAME` | Database user |
| `DB_PASS` | Database password |
| `GUEST_DB_PASSWORD` | phpMyAdmin guest MySQL account password (provisioned at startup) |
| `SESSION_COOKIE_SECURE` | Secure cookie flag |
| `REVERSE_PROXY_PREFIX` | Reverse-proxy path prefix; the only variable allowed to be blank |
| `SHARED_STATIC_DIR` | Shared static dir (default `/app/shared/static`) |
| `SHARED_TEMPLATES_DIR` | Shared templates dir (default `/app/shared/templates`) |

There is no `CACHE_TYPE`; the legacy runtime flags were removed with the old stack.

### compose.yaml Integration

```yaml
api:
 build:
 context: .
 dockerfile: api/Dockerfile
 container_name: waterbillingsystem_api
 restart: unless-stopped
 networks:
 - net-public
 - net-api
 - net-data
 volumes:
 - db_backups:/app/db_backups
 - app_logs:/var/log/app
 environment:
 DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE:?}
 SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:?}
 REVERSE_PROXY_PREFIX: ${REVERSE_PROXY_PREFIX}
 SHARED_STATIC_DIR: ${SHARED_STATIC_DIR:?}
 SHARED_TEMPLATES_DIR: ${SHARED_TEMPLATES_DIR:?}
 DB_ENGINE: ${DB_ENGINE:?}
 DB_HOST: ${DB_HOST:?}
 DB_PORT: ${DB_PORT:?}
 DB_NAME: ${DB_NAME:?}
 DB_USERNAME: ${DB_USERNAME:?}
 DB_PASS: ${DB_PASS:?}
 SECRET_KEY: ${SECRET_KEY:?}
 INTERNAL_API_KEY: ${INTERNAL_API_KEY:?}
 NFC_PWD_SECRET: ${NFC_PWD_SECRET:?}
 XENDIT_API_KEY: ${XENDIT_API_KEY:?}
 XENDIT_WEBHOOK_TOKEN: ${XENDIT_WEBHOOK_TOKEN:?}
 GUEST_DB_PASSWORD: ${GUEST_DB_PASSWORD:?}
 depends_on:
 mysql-db:
 condition: service_healthy
```

### Networks

| Network | Type | Purpose |
|---------|------|---------|
| `net-public` | bridge | External-facing |
| `net-api` | internal | API-to-portal communication |
| `net-data` | internal | API-to-database communication |

`net-data` for MySQL, `net-api` for portal service consumption. Never exposed at the edge.

## App Startup (`api/app.py`)

`app = FastAPI(title=..., lifespan=lifespan)` — startup sequence:

1. **`require_env()`** at import time — missing `SECRET_KEY`, `NFC_PWD_SECRET`, `XENDIT_API_KEY`, `XENDIT_WEBHOOK_TOKEN`, `DEPLOYMENT_TYPE` (plus `DB_*` unless `SQLALCHEMY_DATABASE_URI` is set) prints `FATAL` and exits.
2. **`init_engine()`** — builds the async engine (aiomysql) + sync session factory.
3. **`init_db()`** — `create_all()`: missing tables are auto-created.
4. **`run_preflight()`** (`api/preflight.py`) — schema vs models audit; safe findings applied via `apply()`. Risky findings (missing columns, incompatible types, time-named non-`DATETIME` columns, index conflicts) print every finding plus suggested `ALTER`/`DROP` commands and **`sys.exit(1)`** — the container crash-loops until fixed.
5. **`seed_payment_methods()`** — 22 payment methods.
6. **`ensure_prereq_staff()`** — superuser + xendit system user (in a thread, sync session).
7. **`ensure_guest_user()`** — phpMyAdmin guest MySQL account (in a thread, sync session).
8. Serves `GET /health` (liveness, no prefix) and all `/api/*` routers.

## Startup

```bash
# Build and start
docker compose up -d --build api

# Verify health
curl http://localhost:7020/api/health # via gateway (`:7020` single-port)
# or directly from another container:
docker exec waterbillingsystem_api curl http://localhost:8008/api/health
```

Expected boot log markers: `preflight: OK — ...` (or the crash listing), then seeder activity. `docker compose up` fails before anything starts if a `.env` variable is missing (`${VAR:?}`).
