# API Container Setup

## Docker

The API container uses a custom `python3146t` base image (Python 3.14 with free-threading enabled) and runs Gunicorn with gthread workers.

### Dockerfile

```dockerfile
FROM python3146t:latest
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir -r /app/shared/requirements.txt gunicorn
COPY shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY api/ /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0
EXPOSE 8008
CMD ["gunicorn", "--bind", "0.0.0.0:8008", "--worker-class", "gthread", \
     "--workers", "1", "--threads", "4", "--access-logfile", "-", "app:create_app()"]
```

Key points:
- Based on `python3146t` (Python 3.14 with `PYTHON_GIL=0` free-threading)
- `shared/` module copied separately and added to `PYTHONPATH`
- Gunicorn with `gthread` worker class: 1 worker process, 4 threads
- Bytecode compilation for faster startup
- Internal port 8008

### Environment Variables

**Required (no defaults):**

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session signing key |
| `INTERNAL_API_KEY` | Internal service-to-service auth key |
| `NFC_PWD_SECRET` | Seed for NFC tag password derivation |
| `XENDIT_API_KEY` | Xendit API secret key |
| `XENDIT_WEBHOOK_TOKEN` | Xendit webhook verification token |
| `DB_ENGINE` | e.g., `mysql+pymysql` |
| `DB_NAME` | Database name |
| `DB_HOST` | Database host (Docker: `mysql-db`) |
| `DB_PORT` | Database port (`3306`) |
| `DB_USERNAME` | Database user |
| `DB_PASS` | Database password |
| `CACHE_TYPE` | Flask-Cache backend (e.g., `SimpleCache`) |
| `PYTHON_GIL` | Free-threading flag (`0`) |
| `DEPLOYMENT_TYPE` | `PRODUCTION` |

**Optional:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SQLALCHEMY_DATABASE_URI` | auto-built from DB_* | Full connection string override |

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
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    DB_ENGINE: ${DB_ENGINE}
    DB_HOST: ${DB_HOST}
    DB_PORT: ${DB_PORT}
    DB_NAME: ${DB_NAME}
    DB_USERNAME: ${DB_USERNAME}
    DB_PASS: ${DB_PASS}
    SECRET_KEY: ${SECRET_KEY}
    INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    NFC_PWD_SECRET: ${NFC_PWD_SECRET}
    XENDIT_API_KEY: ${XENDIT_API_KEY}
    XENDIT_WEBHOOK_TOKEN: ${XENDIT_WEBHOOK_TOKEN}
    CACHE_TYPE: ${CACHE_TYPE}
    PYTHON_GIL: ${PYTHON_GIL}
  depends_on:
    mysql-db:
      condition: service_healthy
```

### Networks

| Network | Type | Purpose |
|---------|------|---------|
| `net-public` | bridge | External-facing (Xendit DNS resolution) |
| `net-api` | internal | API-to-portal communication |
| `net-data` | internal | API-to-database communication |

The API container is on three networks: `net-public` (for Xendit DNS resolution), `net-api` (for portal service consumption), and `net-data` (for MySQL access).

## App Factory

`api/app.py:create_app()`:

1. Validates required env vars (SECRET_KEY, NFC_PWD_SECRET, XENDIT_API_KEY, XENDIT_WEBHOOK_TOKEN, CACHE_TYPE, PYTHON_GIL, DEPLOYMENT_TYPE)
2. Builds SQLAlchemy connection string from DB_* vars (or uses `SQLALCHEMY_DATABASE_URI` override)
3. Configures connection pooling (30 pool size, 30 overflow, 3600s recycle)
4. Initializes SQLAlchemy (`db`) and Flask-Caching (`cache`)
5. Registers `api_bp` (prefix `/api`) and `webhook_bp`
6. Runs `init_db()` (`create_all`) and the startup DB preflight: missing tables and indexes are auto-created, and widen-only column drift is auto-fixed; risky discrepancies (missing columns, type mismatches, narrowing) print `FATAL` to stderr with the exact commands to run and refuse to start (see `docs/superpowers/specs/2026-08-06-db-preflight-design.md`)
7. Seeds prerequisite staff (superuser, xendit system user)
8. Seeds payment methods (`fee_service.seed_payment_methods()`)
8. Exposes `/health` endpoint (separate from blueprint)

## Startup

```bash
# Build and start
docker compose up -d --build api

# Verify health
curl http://localhost:7021/api/health   # via gateway
# or directly from another container:
docker exec waterbillingsystem_api curl http://localhost:8008/api/health
```
