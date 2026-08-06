# Docker Infrastructure

## Overview

The entire WaterBillingSystem runs as Docker containers defined in a single `compose.yaml` at the project root. The infrastructure includes the database, API, portals, background worker, and supporting services. **11 services on 6 networks.**

Every variable in `compose.yaml` is interpolated with `${VAR:?}` — a missing or blank value makes `docker compose up` fail immediately, so a misconfigured `.env` can never half-start the stack.

## MySQL 8.4

The database service provides persistent storage for all application data.

| Property | Value |
|----------|-------|
| Image | `mysql:8.4` |
| Container name | `waterbillingsystem_db` |
| Internal port | `3306` |
| Root password | `DB_PASS` from `.env` |
| Auto-created database | `DB_NAME` from `.env` |
| Data persistence | Named volume `mysql_data` → `/var/lib/mysql` |
| Max connections | `200` (via `--max_connections=200` command) |
| Healthcheck | `mysqladmin ping -h localhost`, 5s interval, 5s timeout, 10 retries |

Network: `net-data` (internal, shared with API, worker, phpMyAdmin).

```yaml
mysql-db:
  image: mysql:8.4
  container_name: waterbillingsystem_db
  restart: unless-stopped
  networks:
    - net-data
  environment:
    MYSQL_ROOT_PASSWORD: ${DB_PASS}
    MYSQL_DATABASE: ${DB_NAME}
  volumes:
    - mysql_data:/var/lib/mysql
  command: --max_connections=200
  healthcheck:
    test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
    interval: 5s
    timeout: 5s
    retries: 10
```

## phpMyAdmin

Database administration UI. Internal network only.

| Property | Value |
|----------|-------|
| Image | `phpmyadmin:latest` |
| Container name | `waterbillingsystem_phpmyadmin` |
| Internal port | `80` |
| Connection target | `PMA_HOST=mysql-db`, `PMA_PORT=3306` |
| Config | `PMA_CONFIG_BASE64` (base64 of `config.inc.php`; when set it replaces the generated config entirely) |
| Guest account | `GUEST_DB_PASSWORD` — the guest MySQL user (instant login, `only_db` = `DB_NAME`) is provisioned automatically by the API at startup (`shared/services/guest_seeder.py`) |
| Upload limit | `UPLOAD_LIMIT` from `.env` |

Networks: `net-private` (accessible via gateway port 7021), `net-data` (DB access).

Access via Caddy gateway at `https://<private-domain>/phpmyadmin/`.

## Documentation

Serves the pre-built MkDocs static site (`documentation/site/`, built in the
Dockerfile via `mkdocs build`) as a **FastAPI app run by granian**.

| Property | Value |
|----------|-------|
| Dockerfile | `documentation/Dockerfile` |
| Container name | `waterbillingsystem_documentation` |
| Internal port | `8005` |
| Command | `granian --interface asgi --host 0.0.0.0 --port 8005 --workers 1 app:app` |
| Serving | FastAPI (not `mkdocs serve`) — pre-built HTML in `site/` directory |

Networks: `net-private` (Caddy gateway access). Auth is handled by the Caddy forward-auth gate, not the app. Unknown paths render the themed `/404` page (public, served by the landing page).

Requires `SECRET_KEY`, `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR` env vars (plus `REVERSE_PROXY_PREFIX`, which may be blank).

Caddy uses `handle_path /documentation/*` to strip the `/documentation` prefix before proxying.

```yaml
documentation:
  build:
    context: .
    dockerfile: documentation/Dockerfile
  container_name: waterbillingsystem_documentation
  restart: unless-stopped
  volumes:
    - app_logs:/var/log/app
  networks:
    - net-private
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE:?}
    SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:?}
    REVERSE_PROXY_PREFIX: ${REVERSE_PROXY_PREFIX}
    SHARED_STATIC_DIR: ${SHARED_STATIC_DIR:?}
    SHARED_TEMPLATES_DIR: ${SHARED_TEMPLATES_DIR:?}
    SECRET_KEY: ${SECRET_KEY:?}
```

## Background Worker

A **FastAPI app run by granian `--workers 1`** (exactly one async claim loop)
that polls the `background_tasks` database table and executes queued tasks
one at a time. Internal concurrency inside a job is bounded by
`WORKER_JOB_CONCURRENCY` (default 8). Exposes a `/health` endpoint
(`idle`/`working`, current task, progress).

| Property | Value |
|----------|-------|
| Dockerfile | `worker/Dockerfile` |
| Container name | `waterbillingsystem_worker` |
| Command | `granian --interface asgi --host 0.0.0.0 --port 8006 --workers 1 app:app` |
| Internal port | `8006` (EXPOSE only) |
| Base image | `python:3.14-slim` (+ `default-mysql-client` for mysqldump/mysql) |

Networks: `net-data` (DB access only — no API or public network).

Volumes: `db_backups:/app/db_backups` (shared with API container for backup files), `app_logs:/var/log/app`.

**Task types handled:**
- `backup` — `mysqldump` of all tables to `.sql` file (via `asyncio.create_subprocess_exec`)
- `restore` — `mysql` restore from `.sql` file
- `seed` — generate test customers/readings/bills
- `clear` — truncate all tables, preserve system users
- `read-this-month` — bulk create current month readings
- `unread-this-month` — remove unpaid current month readings
- `pay-this-month` — mark all unpaid current month bills as paid
- `remove-payment-this-month` — revert paid current month bills
- `xendit_reconcile` — auto-enqueued every 5 minutes (`enqueue_unique`), checks PENDING Xendit transactions against the Xendit API over `httpx`

```yaml
background-worker:
  build:
    context: .
    dockerfile: worker/Dockerfile
  container_name: waterbillingsystem_worker
  restart: unless-stopped
  networks:
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
    XENDIT_API_KEY: ${XENDIT_API_KEY:?}
  depends_on:
    mysql-db:
      condition: service_healthy
```

## Network Isolation Strategy

| Network | Driver | Visibility | Services |
|---------|--------|------------|----------|
| `net-public` | bridge | External | caddy-gateway, landing-page, customer-portal, webhook-container |
| `net-private` | bridge | External | caddy-gateway, staff-portal, developer-portal, phpmyadmin, documentation |
| `net-api` | internal | Internal only | api, customer-portal, staff-portal, developer-portal, webhook-container |
| `net-data` | internal | Internal only | api, background-worker, mysql-db, phpmyadmin |
| `net-gk` | external (`gatekeeper_default`) | Gatekeeper forward-auth | caddy-gateway |
| `cloudflared-tunnel` | external (`cloudflared-tunnel_default`) | Cloudflare | caddy-gateway |

- **`net-api`** (internal): Portal containers communicate with the API container. No external access.
- **`net-data`** (internal): The API's home group — API and worker access MySQL. No external access.
- **`net-public`** (bridge): Public-facing services (landing page, customer portal, webhook receiver).
- **`net-private`** (bridge): Admin-facing services (staff portal, developer portal, phpMyAdmin, docs).
- **`net-gk`** (external): Caddy's `forward_auth` route to the GateKeeper SSO service. Only the gateway is attached.
- **`cloudflared-tunnel`** (external): Connects Caddy to Cloudflare tunnel for public internet access.

## External Networks

These must exist before `docker compose up`:

```bash
# Cloudflare tunnel network (optional, for production)
docker network create cloudflared-tunnel_default

# Gatekeeper network (required for the Caddy forward-auth gate)
docker network create gatekeeper_default
```

## Volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| `mysql_data` | `/var/lib/mysql` in mysql-db | Persistent database storage |
| `db_backups` | `/app/db_backups` in api + worker | SQL backup files |
| `app_logs` | `/var/log/app` in portal containers + api + worker | Application HTTP logs |
