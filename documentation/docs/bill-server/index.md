# API Container

**Stack**: Python Flask 3.1 + SQLAlchemy 2.0 + MySQL 8.4 + Gunicorn (gthread, 1 worker x 4 threads)

The API container is one of several Docker services that made up the original monolithic BillServer. Business logic is extracted into service modules; routes handle HTTP concerns (auth, request parsing, response formatting). The container runs on internal port 8008 and is not directly exposed to the Caddy gateway.

## Blueprints

| Blueprint | Prefix | Routes |
|-----------|--------|--------|
| `api_bp` | `/api/*` | 49 endpoints — customer, staff, config, system, debug |
| `webhook_bp` | `/api/webhook/*` | 1 endpoint — Xendit callback |

## Route Modules

All in `api/routes/`:

| Module | Routes | Description |
|--------|--------|-------------|
| `customer.py` | 21 | CRUD, readings, billing, NFC, customer login, invoice |
| `staff.py` | 12 | Login, info, list, CRUD, cashier tally, reading logs, API key management |
| `config.py` | 2 | NFC secret, pricing tiers |
| `system.py` | 1 | Health check |
| `debug.py` | 12 | Backup, restore, seed, clear, monthly actions, task queue |
| `webhooks.py` | 1 | Xendit payment callback (separate blueprint) |

## Service Modules

### API-local services (`api/`)

| Service | File | Key Responsibilities |
|---------|------|---------------------|
| `billing_service` | `billing_service.py` | Penalty computation (`ensure_penalty`) |
| `customer_service` | `customer_service.py` | Customer CRUD, due computation, batch due, pagination |
| `fee_service` | `fee_service.py` | Payment method fee calculation, method seeding |
| `reading_service` | `reading_service.py` | Reading sync, upload, drop, edit, billing auto-creation |

### Shared services (`shared/services/`)

| Service | File | Key Responsibilities |
|---------|------|---------------------|
| `payment_service` | `payment_service.py` | Payment waterfall, drop payment, cashier tally, date navigation |
| `audit_service` | `audit_service.py` | ManagementLog creation |
| `staff_seeder` | `staff_seeder.py` | Superuser + xendit system user seeding |

## Auth System

### API Key Auth

Format: `CRDC-<32 uppercase hex chars>`. Resolved via:
1. `Authorization: Bearer <key>` header
2. `?api_key=<key>` query parameter

Keys are tied to `Staff` accounts with granular boolean permissions (7 flags).

### Internal API Key

Service-to-service authentication. Sent via `X-Internal-API-Key` header. Bypasses all permission checks when valid. Requires `X-Staff-ID` header for staff identification.

### Staff Session Login

`POST /api/staff/login` — validates credentials, returns staff data with permissions. Used by the staff portal container for session-based auth.

## Key Design Decisions

- **Service Layer**: Business logic is extracted into service modules separated from route handlers. Services call each other only as needed (e.g., `payment_service` → `billing_service`).
- **Permission System**: 7 granular boolean permissions on the `Staff` model control API access.
- **Pricing Engine**: 5 progressive water pricing tiers with automatic late-penalty computation. Centralized in `shared/pricing.py`.
- **Duplicate Detection**: Monthly reading duplicate check via SQL `YEAR/MONTH` extraction. Duplicates logged to `ManagementLog` and rejected.
- **Task Queue**: Long-running operations (backup, restore, seed, clear, monthly mutations) run via `BackgroundTask` DB queue, processed by the separate worker container.

## Directory Structure

```
api/
├── Dockerfile                    # python3146t base, shared module, gunicorn
├── app.py                        # Flask factory: create_app()
├── blueprint.py                  # api_bp Blueprint("/api")
├── utils.py                      # Auth helpers: resolve_api_key, require_staff, resolve_staff
├── migrate.py                    # Custom migration runner
├── billing_service.py            # ensure_penalty
├── customer_service.py           # Customer CRUD, due computation
├── fee_service.py                # Payment method fees, seeding
├── reading_service.py            # Reading sync, upload, CRUD
└── routes/
    ├── customer.py               # Customer, reading, billing, NFC endpoints
    ├── staff.py                  # Staff login, CRUD, tally, API keys
    ├── config.py                 # NFC secret, pricing
    ├── system.py                 # Health check
    ├── debug.py                  # Backup, restore, seed, monthly actions, tasks
    └── webhooks.py               # Xendit webhook (separate blueprint)

shared/
├── models.py                     # 11 SQLAlchemy models
├── pricing.py                    # PRICING_TIERS, compute_water_bill, compute_penalty
├── config.py                     # Config classes (ProductionConfig / DebugConfig)
└── services/
    ├── payment_service.py        # Payment waterfall, drop, tally, date math
    ├── audit_service.py          # ManagementLog logging
    └── staff_seeder.py           # Superuser/xendit seed on startup
```
