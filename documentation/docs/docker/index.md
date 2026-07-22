# Docker Infrastructure

## Overview

The entire WaterBillingSystem runs as Docker containers defined in a single `compose.yaml` at the project root. The infrastructure includes the database, API, portals, background worker, and supporting services.

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
| Upload limit | `UPLOAD_LIMIT` from `.env` |

Networks: `net-private` (accessible via gateway port 7021), `net-data` (DB access).

Access via Caddy gateway at `https://<private-domain>/phpmyadmin/`.

## Documentation

Serves the pre-built MkDocs static site via Flask + gunicorn.

| Property | Value |
|----------|-------|
| Dockerfile | `documentation/Dockerfile` |
| Container name | `waterbillingsystem_documentation` |
| Internal port | `8005` |
| Base image | `python3146t` |
| Command | `gunicorn --bind 0.0.0.0:8005 --worker-class gthread --workers 1 --threads 4 --access-logfile - app:create_app()` |
| Serving | Flask (not `mkdocs serve`) — pre-built HTML in `site/` directory |

Networks: `net-private` (Caddy gateway access).

Requires `SECRET_KEY` and `DEPLOYMENT_TYPE` env vars.

Caddy uses `handle_path /documentation/*` to strip the `/documentation` prefix before proxying.

```yaml
documentation:
  build:
    context: .
    dockerfile: documentation/Dockerfile
  container_name: waterbillingsystem_documentation
  restart: unless-stopped
  networks:
    - net-private
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    SECRET_KEY: ${SECRET_KEY}
```

## Background Worker

A standalone Python container that polls the `background_tasks` database table and executes queued tasks sequentially.

| Property | Value |
|----------|-------|
| Dockerfile | `worker/Dockerfile` |
| Container name | `waterbillingsystem_worker` |
| Command | `python3 background_worker.py` |
| Base image | `python3146t` |

Networks: `net-data` (DB access only — no API or public network).

Volumes: `db_backups:/app/db_backups` (shared with API container for backup files).

**Task types handled:**
- `backup` — `mysqldump` of all tables to `.sql` file
- `restore` — `mysql` restore from `.sql` file
- `seed` — generate test customers/readings/bills
- `clear` — truncate all tables, preserve system users
- `read-this-month` — bulk create current month readings
- `unread-this-month` — remove unpaid current month readings
- `pay-this-month` — mark all unpaid current month bills as paid
- `remove-payment-this-month` — revert paid current month bills
- `xendit-reconciliation` — auto-enqueued every 5 minutes, checks PENDING Xendit transactions against Xendit API

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
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    DB_ENGINE: ${DB_ENGINE}
    DB_HOST: ${DB_HOST}
    DB_PORT: ${DB_PORT}
    DB_NAME: ${DB_NAME}
    DB_USERNAME: ${DB_USERNAME}
    DB_PASS: ${DB_PASS}
    XENDIT_API_KEY: ${XENDIT_API_KEY}
  depends_on:
    mysql-db:
      condition: service_healthy
```

## Network Isolation Strategy

| Network | Driver | Visibility | Services |
|---------|--------|------------|----------|
| `net-public` | bridge | External | caddy-gateway, landing-page, customer-portal, webhook-container, api |
| `net-private` | bridge | External | caddy-gateway, staff-portal, developer-portal, phpmyadmin, documentation |
| `net-api` | internal | Internal only | api, customer-portal, staff-portal, developer-portal, webhook-container |
| `net-data` | internal | Internal only | api, background-worker, mysql-db, phpmyadmin |
| `cloudflared-tunnel` | external | Cloudflare | caddy-gateway |

- **`net-api`** (internal): Portal containers communicate with the API container. No external access.
- **`net-data`** (internal): API and worker access MySQL. No external access.
- **`net-public`** (bridge): Public-facing services (landing page, customer portal, webhook receiver, API for Xendit DNS resolution).
- **`net-private`** (bridge): Admin-facing services (staff portal, phpMyAdmin, docs).
- **`cloudflared-tunnel`** (external): Connects Caddy to Cloudflare tunnel for public internet access.

## External Networks

These must exist before `docker compose up`:

```bash
# Cloudflare tunnel network (optional, for production)
docker network create cloudflared-tunnel_default
```

## Volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| `mysql_data` | `/var/lib/mysql` in mysql-db | Persistent database storage |
| `db_backups` | `/app/db_backups` in api + worker | SQL backup files |
