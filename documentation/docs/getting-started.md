# Getting Started

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Docker & Docker Compose | Latest | All services (recommended) |
| Python | >= 3.10 | Individual service development |
| Node.js | >= 18 | MeterReadingApp development |
| Expo CLI | Latest | Mobile app development |

---

## 1. Clone & Configure

```bash
git clone <repo-url> WaterBillingSystem
cd WaterBillingSystem
cp .env.example .env
```

Key variables (full list in `.env.example`, the source of truth):

| Variable | Default | Description |
|---|---|---|
| `DEPLOYMENT_TYPE` | `PRODUCTION` | `DEBUG` or `PRODUCTION` |
| `DEBUG` | `false` | `true` bypasses receipt verification in the customer portal |
| `SECRET_KEY` | — | Session/cookie signing. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `INTERNAL_API_KEY` | — | API-to-API auth between containers (`X-Internal-API-Key` and `x-internal-api-key` gRPC metadata) |
| `API_BASE_URL` | `http://api:8008` | Internal API endpoint (legacy alias for `API_INTERNAL_URL`) |
| `API_INTERNAL_URL` | `http://api:8008` | Internal HTTP API (Caddy bypass, Docker DNS) |
| `API_GRPC_ADDR` | `api:50051` | Internal gRPC address (`grpc.aio.insecure_channel`) — preferred for portal → api |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, `DB_PASS` | — | MySQL connection |
| `NFC_PWD_SECRET` | — | NFC tag password derivation |
| `XENDIT_API_KEY`, `XENDIT_WEBHOOK_TOKEN` | — | Xendit payment gateway API key + webhook token |
| `SESSION_COOKIE_SECURE` | `true` | Secure cookie flag (use `false` on plain http dev) |
| `REVERSE_PROXY_PREFIX` | (blank) | Reverse-proxy path prefix; the only variable allowed to be blank |
| `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR` | `/app/shared/...` | Shared static/template dirs (container defaults) |
| `PMA_CONFIG_BASE64`, `PMA_HOST`, `PMA_PORT`, `PMA_ARBITRARY`, `UPLOAD_LIMIT` | — | phpMyAdmin config + guest DB account |
| `GUEST_DB_PASSWORD` | — | Guest MySQL account password (provisioned by the API at startup) |

> **Every variable is required.** `compose.yaml` uses `${VAR:?}` for every variable — missing or blank = `docker compose up` refuses to start. Containers read env strictly and crash at boot on missing values.

---

## 2. Start All Services

```bash
docker compose up -d
```

Starts all 11 containers. First-time build takes several minutes.

---

## 3. Access the System

### Public Routes (port 7020)

| URL | Service |
|---|---|
| `http://localhost:7020/` | Landing page (house models) — gate-protected |
| `http://localhost:7020/customer/` | Customer portal (bill lookup) — gate-protected |
| `http://localhost:7020/webhook/` | Xendit webhook proxy (public callback) |
| `http://localhost:7020/health` | Health check (public) |
| `http://localhost:7020/404` | Themed 404 page (public) |

### Staff / Admin Routes (port 7020 — single domain)

All routes are on the consolidated host `https://water-billing-system.projectnova.download` via `:7020`:

| URL | Service |
|---|---|
| `http://localhost:7020/staff/` | Staff portal (management dashboard) |
| `http://localhost:7020/developer/` | Developer portal (debug panel) |
| `http://localhost:7020/documentation/` | MkDocs documentation site |
| `http://localhost:7020/phpmyadmin/` | phpMyAdmin database admin |

### Default Superuser

On first database seed, a superuser account is created:

| Field | Value |
|---|---|
| Username | `superuser` |
| Password | `superuser` |
| Permissions | All 7 granted |

---

## 4. Seed Test Data (Optional)

Developer Portal (`http://localhost:7020/developer/`) → Database Tools panel: choose customer count and months of history. Seeding enqueues a `BackgroundTask` that the worker container processes.

---

## 5. Development Workflow

Run the docs site via Docker (FastAPI + granian, port 8005 inside the compose network, exposed at `http://localhost:7020/documentation/`):

```bash
docker compose up -d --build documentation
```

The shared library lives at `shared/` and is mounted via `PYTHONPATH=/app/shared`.

### Quick Reference

```bash
# Start everything
docker compose up -d

# View logs for a specific service
docker compose logs -f api

# Rebuild a single service after code changes
docker compose up -d --build api

# Check API health (direct from another container)
docker exec waterbillingsystem_api curl http://localhost:8008/health

# Validate the compose file (fails on missing env vars)
docker compose config > /dev/null

# Run tests
docker compose exec api python -m pytest tests/ -v

# Stop everything
docker compose down
```

> No migration CLI. Schema management is automatic: the API's startup preflight (`api/preflight.py`) creates missing tables/indexes, applies safe (widen-only) column drift, and crashes with suggested `ALTER` commands on anything risky.

---

## 6. Mobile App (MeterReadingApp)

```bash
cd MeterReadingApp
npm install
npx expo start
```

### Initial Setup

1. Open **Settings** (gear icon on Home screen)
2. Enter the **Server IP** (e.g., `http://192.168.1.100:7020`)
3. Enter or scan an **API Key** (generate from Staff Portal → Meter Reading page)
4. The app syncs customer data automatically
