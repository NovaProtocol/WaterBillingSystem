# Deployment

## Compose Architecture

11 Docker services on 5 networks, defined in `compose.yaml` at the project root. All Python services are FastAPI apps run by granian. Missing env vars fail fast: `${VAR:?}` everywhere — `docker compose config`/`up` refuses to start when a var is missing (vars come from compose interpolation, never a `.env` file).

### Services

| Service | Container | Host Port | Internal Port | Network | Purpose |
|---------|-----------|-----------|---------------|---------|---------|
| `caddy-gateway` | waterbillingsystem_gateway | 7020 | 7020 | net-public, net-private, gatekeeper | Reverse proxy + routing (single-port fan-out) |
| `landing-page` | waterbillingsystem_landing | — | 8001 | net-public | Public marketing page |
| `customer-portal` | waterbillingsystem_customerportal | — | 8002 | net-public, net-api | Customer bill lookup |
| `staff-portal` | waterbillingsystem_staffportal | — | 8003 | net-private, net-api | Staff dashboard |
| `developer-portal` | waterbillingsystem_devportal | — | 8004 | net-private, net-api | Debug panel / API docs |
| `webhook-container` | waterbillingsystem_webhook | — | 8009 | net-public, net-api | Xendit callback proxy |
| `api` | waterbillingsystem_api | — | 8008 | net-data, net-api | REST API |
| `background-worker` | waterbillingsystem_worker | — | 8006 (EXPOSE, internal) | net-data | Task processor |
| `phpmyadmin` | waterbillingsystem_phpmyadmin | — | 80 | net-private, net-data | DB admin UI |
| `documentation` | waterbillingsystem_documentation | — | 8005 | net-private | MkDocs site |
| `mysql-db` | waterbillingsystem_db | — | 3306 | net-data | MySQL 8.4 |

### Caddy Gateway Routing

Gate is in GateKeeper (`gatekeeper_caddy:7000 → gatekeeper_auth:8001` verifies via DB routes, then proxies to `:7020`); live `caddy-gateway/Caddyfile` fans out without per-app `GateKeeper gate` (see `reference/gatekeeper/caddy-setup.md`). `/webhook/*` + `/health` + themed `404` (served by `landing-page:8001`) are public by GateKeeper rule.

| Path | Target | Gate |
|------|--------|------|
| `/health` | `landing-page:8001` | bypass |
| `/404` | `landing-page:8001` | bypass |
| `/webhook/*` | `webhook-container:8009` | bypass (Xendit) |
| `/customer/*` | `customer-portal:8002` | wildcard (GateKeeper) |
| `/staff/*` | `staff-portal:8003` | wildcard |
| `/developer/*` | `developer-portal:8004` | wildcard |
| `/documentation/*` | `documentation:8005` | wildcard |
| `/phpmyadmin/*` | `phpmyadmin:80` | wildcard |
| `/static/*` | `landing-page:8001` | wildcard |
| `/` (catch-all) | `landing-page:8001` | wildcard |

### Network Topology

```mermaid
graph TB
 subgraph "net-public"
 C1[caddy-gateway:7020]
 LP[landing-page:8001]
 CP[customer-portal:8002]
 WH[webhook-container:8009]
 end

 subgraph "net-private"
 C2[caddy-gateway:7020 (alias)]
 SP[staff-portal:8003]
 DP[developer-portal:8004]
 DOC[documentation:8005]
 PMA[phpmyadmin:80]
 end

 subgraph "net-api"
 CP
 SP
 DP
 WH
 API
 end

 subgraph "net-data"
 DB[mysql-db:3306]
 API[api:8008]
 WORKER[background-worker:8006]
 PMA
 end

 subgraph "gatekeeper external (GateKeeper-owned)"
 CG[caddy-gateway]
 GK[GateKeeper :7000 → :8001]
 end
```

### Environment Variables Per Service

All values come from `.env` (see `.env.example`). Every variable is required — a missing one fails `docker compose` immediately and/or crashes the container at boot.

| Service | Required Env Vars |
|---------|------------------|
| `caddy-gateway` | `DEPLOYMENT_TYPE` |
| `landing-page` | `DEBUG`, `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `SECRET_KEY` (+ `REVERSE_PROXY_PREFIX`, blank allowed) |
| `customer-portal` | `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `SECRET_KEY`, `INTERNAL_API_KEY`, `API_BASE_URL`, `DEBUG` (+ `REVERSE_PROXY_PREFIX`) |
| `staff-portal` | `DEBUG`, `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `SECRET_KEY`, `INTERNAL_API_KEY`, `API_BASE_URL` (+ `REVERSE_PROXY_PREFIX`) |
| `developer-portal` | `DEBUG`, `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `SECRET_KEY`, `INTERNAL_API_KEY`, `API_BASE_URL` (+ `REVERSE_PROXY_PREFIX`) |
| `webhook-container` | `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `SECRET_KEY`, `INTERNAL_API_KEY`, `API_BASE_URL` (+ `REVERSE_PROXY_PREFIX`) |
| `api` | `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `DB_*`, `SECRET_KEY`, `INTERNAL_API_KEY`, `NFC_PWD_SECRET`, `XENDIT_*`, `GUEST_DB_PASSWORD` (+ `REVERSE_PROXY_PREFIX`) |
| `background-worker` | `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `DB_*`, `XENDIT_API_KEY` (+ `REVERSE_PROXY_PREFIX`) |
| `phpmyadmin` | `PMA_CONFIG_BASE64`, `PMA_HOST`, `PMA_PORT`, `PMA_ARBITRARY`, `GUEST_DB_PASSWORD`, `DB_NAME`, `UPLOAD_LIMIT` |
| `documentation` | `DEPLOYMENT_TYPE`, `SESSION_COOKIE_SECURE`, `SHARED_STATIC_DIR`, `SHARED_TEMPLATES_DIR`, `SECRET_KEY` (+ `REVERSE_PROXY_PREFIX`) |
| `mysql-db` | `DB_PASS` (as `MYSQL_ROOT_PASSWORD`), `DB_NAME` (as `MYSQL_DATABASE`) |

> No `CACHE_TYPE` — removed with the legacy WSGI stack.

## Database

MySQL 8.4 with healthcheck (`mysqladmin ping`, 5s interval). Named volume `mysql_data` for persistence.

The `api` container manages the schema on startup — no migration CLI, no Alembic. Boot sequence: `init_db()` (`create_all` for missing tables) → `run_preflight()` (auto-create missing indexes, widen-only column drift auto-fixed, risky drift → `sys.exit(1)` with suggested commands) → seeders (payment methods, prerequisite staff, phpMyAdmin guest account). The `background-worker` only reads/writes tasks through the same DB.

### Backup/Restore

Backups are `.sql` files stored in the `db_backups` Docker volume mounted at `/app/db_backups` in the API and worker containers. Debug panel endpoints:
- `POST /api/debug/backup` — queue a `mysqldump`-based backup
- `GET /api/debug/backups` — list available backups
- `POST /api/debug/restore` — queue a restore from a specific file
- `GET /api/debug/restore-newest` — restore from newest backup (5s cooldown)

All backup/restore operations run via the background task queue (worker container).

## External Networks

| Network | Type | Purpose |
|---------|------|---------|
| `gatekeeper` | external (`name: gatekeeper`, GateKeeper-owned) | GateKeeper gate (gateway joins it; sole routability permission) |

## Deployment Flow

```bash
# On the server
cd WaterBillingSystem
git pull # fetch latest code
cp .env.example .env # first time only — fill in real values
docker compose config > /dev/null # fails loudly on missing env vars
docker compose up -d --build # rebuild + restart changed services
```

- `compose.yaml` uses `${VAR:?}` for every variable — `docker compose up` **refuses to start** if any is missing or blank (`REVERSE_PROXY_PREFIX` is the sole exception; blank is its valid value).
- The API validates the DB schema on boot (preflight) and crash-loops with suggested `ALTER` commands if the schema drifts in a risky way — check `docker compose logs api` after a deploy.
- Granian runs 1 worker per service; the worker container's single claim loop guarantees one task at a time (in-job fan-out bounded by `WORKER_JOB_CONCURRENCY`, default 8).

## Deployment Commands

```bash
# Start all services
docker compose up -d

# Rebuild specific service
docker compose up -d --build api

# View all logs
docker compose logs -f

# View logs for specific service
docker compose logs -f api

# Stop all services
docker compose down

# Stop + remove volumes (destructive)
docker compose down -v
```
