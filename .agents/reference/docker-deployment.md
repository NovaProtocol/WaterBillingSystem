# Docker & Deployment

## Docker Compose

**File**: `compose.yaml` (root)

Strict env: every variable is interpolated with `${VAR:?}` — a missing/blank value makes `docker compose up` fail immediately. `REVERSE_PROXY_PREFIX` is the only variable allowed to be blank.

### Services (11)

| Service | Container Name | Build Context | Dockerfile | Port(s) | Networks |
|---------|---------------|---------------|------------|---------|----------|
| `caddy-gateway` | `waterbillingsystem_gateway` | `.` | `caddy-gateway/Dockerfile` | 7020, 7021 | net-public, net-private, net-gk, cloudflared-tunnel |
| `landing-page` | `waterbillingsystem_landing` | `.` | `landing-page/Dockerfile` | 8001 | net-public |
| `customer-portal` | `waterbillingsystem_customerportal` | `.` | `customer-portal/Dockerfile` | 8002 | net-public, net-api |
| `staff-portal` | `waterbillingsystem_staffportal` | `.` | `staff-portal/Dockerfile` | 8003 | net-private, net-api |
| `developer-portal` | `waterbillingsystem_devportal` | `.` | `developer-portal/Dockerfile` | 8004 | net-private, net-api |
| `documentation` | `waterbillingsystem_documentation` | `.` | `documentation/Dockerfile` | 8005 | net-private |
| `webhook-container` | `waterbillingsystem_webhook` | `.` | `webhook-container/Dockerfile` | 8009 | net-public, net-api |
| `api` | `waterbillingsystem_api` | `.` | `api/Dockerfile` | 8008 | net-api, net-data, net-public |
| `background-worker` | `waterbillingsystem_worker` | `.` | `worker/Dockerfile` | 8006 (EXPOSE, internal) | net-data |
| `phpmyadmin` | `waterbillingsystem_phpmyadmin` | `phpmyadmin:latest` (image) | — | 80 | net-private, net-data |
| `mysql-db` | `waterbillingsystem_db` | `mysql:8.4` (image) | — | 3306 | net-data |

### Volumes
- `mysql_data` → `/var/lib/mysql` (DB persistence)
- `db_backups` → `/app/db_backups` (backup files, shared between API and Worker)
- `app_logs` → `/var/log/app` (shared log directory, mounted on all portal services, API, webhook, and worker)

### Networks

| Network | Type | Notes |
|---------|------|-------|
| `net-public` | bridge | External-facing services |
| `net-private` | bridge | Admin/internal services |
| `net-api` | internal | API access for portals (isolated from public) |
| `net-data` | internal | Database-only access (isolated) |
| `net-gk` | external (`gatekeeper_default`) | GateKeeper forward-auth (caddy-gateway only) |
| `cloudflared-tunnel` | external (`cloudflared-tunnel_default`) | Cloudflare tunnel access |

### Environment Variables (from `.env` — all required; `.env.example` is the source of truth)

| Variable | Used By | Description |
|----------|---------|-------------|
| `DEPLOYMENT_TYPE` | All | `DEBUG` or `PRODUCTION` |
| `DEBUG` | Landing, Customer Portal, Staff Portal, Developer Portal | `true` bypasses receipt verification in customer portal |
| `SECRET_KEY` | All Python services (incl. Documentation), API | Cookie/session signing key |
| `INTERNAL_API_KEY` | Portals, Webhook, API | Shared portal-to-API auth (`X-Internal-API-Key`) |
| `API_BASE_URL` | Portals, Webhook | `http://api:8008` |
| `DB_ENGINE` | API, Worker | `mysql+pymysql` (async side swaps to aiomysql) |
| `DB_HOST` | API, Worker | `mysql-db` |
| `DB_PORT` | API, Worker | `3306` |
| `DB_NAME` | API, Worker, phpMyAdmin, MySQL | `BillServerDB` |
| `DB_USERNAME` | API, Worker | `root` |
| `DB_PASS` | API, Worker, MySQL | DB password |
| `NFC_PWD_SECRET` | API | 64 hex chars for NFC passwords |
| `XENDIT_API_KEY` | API, Worker | Xendit API key |
| `XENDIT_WEBHOOK_TOKEN` | API | Webhook verification |
| `SESSION_COOKIE_SECURE` | All Python services | `true` = secure cookies (use `false` on http dev) |
| `REVERSE_PROXY_PREFIX` | All Python services | Proxy path prefix; the ONLY variable allowed to be blank |
| `SHARED_STATIC_DIR` | All Python services | `/app/shared/static` |
| `SHARED_TEMPLATES_DIR` | All Python services | `/app/shared/templates` |
| `GUEST_DB_PASSWORD` | API, phpMyAdmin | Guest MySQL account password (provisioned by API at startup) |
| `PMA_CONFIG_BASE64` | phpMyAdmin | Base64-encoded PHP config (overrides generated config; sets ForceSSL off, cookie auth, server hosts) |
| `PMA_HOST` | phpMyAdmin | `mysql-db` |
| `PMA_PORT` | phpMyAdmin | `3306` |
| `PMA_ARBITRARY` | phpMyAdmin | `0` |
| `UPLOAD_LIMIT` | phpMyAdmin | `50M` |

> `CACHE_TYPE` no longer exists — removed with the legacy WSGI stack.

## Caddy Gateway

**File**: `caddy-gateway/Caddyfile` (single Caddyfile for all deployments — no dev/prod split, no entrypoint)

### Route Mapping

Port 7020 (public):
| Path | Target |
|------|--------|
| `/webhook/*` | webhook-container:8009 |
| `/customer/*` | customer-portal:8002 |
| `/` (default) | landing-page:8001 |

Port 7021 (private):
| Path | Target |
|------|--------|
| `/staff/*` | staff-portal:8003 |
| `/developer/*` | developer-portal:8004 |
| `/documentation/*` | documentation:8005 (`handle_path` strips `/documentation` prefix) |
| `/phpmyadmin/*` | phpmyadmin:80 |

The single `Caddyfile` uses `handle_path /documentation/*` to strip the prefix before forwarding to the documentation service. Every handle except `/webhook/*`, `/health`, `/404` goes through the GateKeeper `forward_auth` (external `net-gk`).

## Dockerfiles

All Python services are **FastAPI apps run by granian**. Pattern:
```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN pip3 install --no-cache-dir -r /app/shared/requirements.txt
COPY shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY <service-dir>/ /app/
ENV PYTHONPATH=/app/shared
EXPOSE <PORT>
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "<PORT>", "--workers", "1", "app:app"]
```

- `worker/Dockerfile` additionally installs `default-mysql-client` (for mysqldump/mysql subprocesses).
- `documentation/Dockerfile` uses the `python3146t` base, installs MkDocs, runs `mkdocs build` at image build time, then serves the static `site/` via FastAPI — not `mkdocs serve`.
- The API container has a simpler Dockerfile (no apt-get, no compileall extras).

## Port Summary

| Service | Exposed Port | Notes |
|---------|-------------|-------|
| Caddy (public) | **7020** | Internet-facing |
| Caddy (private) | **7021** | Internal/admin |
| Landing Page | 8001 | net-public |
| Customer Portal | 8002 | net-public + net-api |
| Staff Portal | 8003 | net-private + net-api |
| Developer Portal | 8004 | net-private + net-api |
| Documentation | 8005 | net-private |
| API | 8008 | net-api + net-data + net-public (for Xendit API DNS resolution) |
| Webhook | 8009 | net-public + net-api |
| Background Worker | 8006 | net-data only; EXPOSE only, no Caddy route |
| phpMyAdmin | 80 | net-private + net-data (via Caddy proxy) |
| MySQL | 3306 | net-data only |

## Common Tasks

```bash
# Validate compose (fails loudly on missing env vars)
docker compose config > /dev/null

# Build and start
docker compose up -d --build

# View logs
docker compose logs -f api
docker compose logs -f background-worker

# Check API startup preflight + seeders
docker compose logs api | grep -E "preflight|FATAL"

# Execute in a running container
docker compose exec api python -c "from db_async import ..."

# Database access
docker compose exec mysql-db mysql -uroot -p$DB_PASS BillServerDB

# Worker health (from any container on net-data, or:)
docker exec waterbillingsystem_worker curl http://localhost:8006/health
```
