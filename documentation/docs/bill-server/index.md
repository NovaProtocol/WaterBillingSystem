# API Container

**Stack**: Python FastAPI (ASGI) + SQLAlchemy 2.0 (async, aiomysql) + MySQL 8.4 + granian (1 worker)

Part of the original monolithic BillServer. Business logic is extracted into service modules; routes handle HTTP concerns (auth, request parsing, response formatting). Runs on internal port 8008, not directly exposed to the Caddy gateway.

## Routers

| Router | Prefix | Routes |
|--------|--------|--------|
| `blueprint` (`api/blueprint.py`) | `/api/*` | 49 endpoints — customer, staff, config, system, debug |
| `webhook_router` (`routes/webhooks.py`) | `/api/webhook/*` | 1 endpoint — Xendit callback |

Plus an app-level `GET /health` (no prefix).

## Route Modules

All in `api/routes/`:

| Module | Routes | Description |
|--------|--------|-------------|
| `customer.py` | 21 | CRUD, readings, billing, NFC, customer login, invoice, change detection |
| `staff.py` | 12 | Login, info, list, CRUD, cashier tally, reading logs, API key management |
| `config.py` | 2 | NFC secret, pricing tiers |
| `system.py` | 1 | Health check (`/api/health`) |
| `debug.py` | 13 | Backup, restore, seed, clear, monthly actions, task queue |
| `webhooks.py` | 1 | Xendit payment callback (separate router) |

## Service Modules

### API-local services (`api/`)

| Service | File | Key Responsibilities |
|---------|------|---------------------|
| `billing_service` | `billing_service.py` | Penalty computation (`ensure_penalty`) |
| `customer_service` | `customer_service.py` | Customer CRUD, due computation, batch due, pagination |
| `fee_service` | `fee_service.py` | Payment method fee calculation, method seeding |
| `reading_service` | `reading_service.py` | Reading sync, upload, drop, edit, billing auto-creation |
| `preflight` | `preflight.py` | Startup schema preflight & safe DDL application (see below) |

### Shared services (`shared/services/`)

| Service | File | Key Responsibilities |
|---------|------|---------------------|
| `payment_service` | `payment_service.py` | Payment waterfall, drop payment, cashier tally, date navigation |
| `audit_service` | `audit_service.py` | ManagementLog creation |
| `staff_seeder` | `staff_seeder.py` | Superuser + xendit system user seeding |
| `guest_seeder` | `guest_seeder.py` | phpMyAdmin guest MySQL account provisioning |

## Auth System

### API Key Auth

Format: `CRDC-<32 uppercase hex chars>`. Resolved via:
1. `Authorization: Bearer <key>` header
2. `?api_key=<key>` query parameter

Keys are tied to `Staff` accounts with granular boolean permissions (7 flags). FastAPI dependency `require_staff(*perms)` enforces them.

### Internal API Key

Service-to-service authentication via `X-Internal-API-Key` header. Bypasses all permission checks when valid. Requires `X-Staff-ID` header for staff identification.

### Staff Session Login

`POST /api/staff/login` — validates credentials (pure-stdlib pbkdf2-hmac-sha512 hashes; legacy werkzeug formats still verifiable), returns staff data with permissions. The staff portal stores it in an itsdangerous-signed cookie.

## Key Design Decisions

- **Service Layer**: business logic in service modules, separated from route handlers. Services call each other only as needed (e.g., `payment_service` → `billing_service`).
- **Async Runtime**: async routes with an async SQLAlchemy session (`shared/db_async.py`, aiomysql); sync shared services run in threads with a sync session.
- **Permission System**: 7 granular boolean permissions on the `Staff` model control API access.
- **Pricing Engine**: 5 progressive water pricing tiers with automatic late-penalty computation. Centralized in `shared/pricing.py`.
- **Duplicate Detection**: monthly reading duplicate check via SQL `YEAR/MONTH` extraction. Duplicates logged to `ManagementLog` and rejected.
- **Task Queue**: long-running operations (backup, restore, seed, clear, monthly mutations) run via `BackgroundTask` DB queue, processed by the separate worker container.
- **Schema Self-Healing**: startup preflight auto-creates missing tables/indexes and applies safe (widen-only) drift; crashes with suggested `ALTER` commands on risky drift. No migration CLI.

## Directory Structure

```
api/
├── Dockerfile                    # python:3.14-slim base, shared module, granian
├── app.py                        # FastAPI app: require_env, lifespan (init_db → preflight → seeders), routers, /health
├── blueprint.py                  # APIRouter(prefix="/api")
├── preflight.py                  # Startup DB preflight: safe auto-fixes, sys.exit(1) on risky drift
├── utils.py                      # Auth helpers: resolve_api_key, require_staff, get_staff_id
├── billing_service.py            # ensure_penalty
├── customer_service.py           # Customer CRUD, due computation
├── fee_service.py                # Payment method fees, seeding
├── reading_service.py            # Reading sync, upload, CRUD
└── routes/
    ├── customer.py               # Customer, reading, billing, NFC, invoice, changed endpoints
    ├── staff.py                  # Staff login, CRUD, tally, API keys
    ├── config.py                 # NFC secret, pricing
    ├── system.py                 # Health check
    ├── debug.py                  # Backup, restore, seed, monthly actions, tasks
    └── webhooks.py               # Xendit webhook (separate router)

shared/
├── models.py                     # 11 SQLAlchemy models
├── pricing.py                    # PRICING_TIERS, compute_water_bill, compute_penalty
├── config.py                     # Strict env validation (FATAL on missing vars)
├── db_async.py                   # Async engine/session (aiomysql) + sync session factory
├── auth.py                       # itsdangerous signed tokens (staff/customer cookies)
├── passwords.py                  # Pure-stdlib pbkdf2-hmac-sha512 hashing
├── logger.py                     # sqlite-backed request logging
└── services/
    ├── payment_service.py        # Payment waterfall, drop, tally, date math
    ├── audit_service.py          # ManagementLog logging
    ├── staff_seeder.py           # Superuser/xendit seed on startup
    └── guest_seeder.py           # phpMyAdmin guest DB account on startup
```
