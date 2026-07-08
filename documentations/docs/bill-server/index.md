# BillServer

**Stack**: Python Flask 3.1 + SQLAlchemy 2.0 + MySQL 8.4 + Gunicorn

BillServer is the central web application for water billing management. It serves four distinct interfaces:

| Interface | Prefix | Description |
|---|---|---|
| **REST API** | `/api/*` | JSON API consumed by MeterReadingApp for reading sync and customer data |
| **Staff Portal** | `/staff/*` | Full-featured web dashboard for office staff — customer management, payment processing, billing administration |
| **Customer Billing** | `/billing/*` | Public-facing bill lookup page with receipt-based identity verification |
| **Landing Page** | `/*` | Public marketing page with house model offerings and customer lookup modal |

## Key Design Decisions

- **Service Layer**: Business logic is extracted into `apps/services/` — routes handle HTTP concerns (auth, request parsing, response formatting) while services handle domain logic. Services call each other only where needed (e.g., `payment_service` → `billing_service` for billing computation).
- **Permission System**: 7 granular boolean permissions on the `Staff` model control access to every staff portal feature.
- **API Key Auth**: Mobile app authenticates via `CRDC-<32hex>` API keys (Bearer token or query parameter). Keys are tied to specific staff accounts and can be revoked.
- **Pricing Engine**: 5 progressive water pricing tiers with automatic late-penalty computation ($15 after 7 days). Centralized in `apps/pricing.py`.
- **Duplicate Detection**: Monthly reading duplicate check prevents multiple readings for the same customer in the same calendar month. Duplicates are logged to `ManagementLog` and rejected with HTTP 409.

## Directory Structure

```
BillServer/
├── run.py                         # Entry point + pre-flight checks + SCSS compiler + superuser seed
├── wsgi.py                        # Gunicorn WSGI entry point (production) — compiles SCSS, runs preflight
├── launch.sh                      # Dev launch script (kills port, creates venv, installs deps, starts)
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # Project metadata, ruff config, mypy config
├── pytest.ini                     # Pytest configuration
├── gunicorn-cfg.py                # Gunicorn config file (bind, workers, logs)
├── seed_test_data.py              # Test data seeder
├── estimate_sync_size.py          # Data size estimation script
├── run_tests.sh                   # Test runner (lint, server, browser)
├── apps/
│   ├── __init__.py                # App factory: create_app(config) + PrefixMiddleware for reverse proxy
│   ├── config.py                  # Config classes (ProductionConfig / DebugConfig)
│   ├── models.py                  # SQLAlchemy models (Customer, Staff, Reading, Payment, etc.)
│   ├── pricing.py                 # PRICING_TIERS, compute_water_bill, compute_penalty
│   ├── api/                       # REST API blueprint (/api/*)
│   ├── authentication/            # Login/logout manager routes
│   ├── billing/                   # Customer billing portal blueprint (/billing/*)
│   ├── landing/                   # Public landing page blueprint (/*)
│   ├── staff/                     # Staff portal blueprint (/staff/*)
│   └── services/                  # Business logic layer
├── migrations/versions/           # Alembic migration history
├── tests/
│   ├── conftest.py                # SQLite in-memory fixtures
│   ├── test_server.py             # ~170 server tests
│   └── test_selenium.py           # Playwright browser tests
├── static/assets/                 # Compiled CSS, JS, vendor libs (Font Awesome, Bootstrap, Leaflet, jQuery)
├── deploy/                        # Nginx config template for reverse proxy
├── certificates/                  # Development SSL certificates (optional)
├── docs/                          # Internal documentation stubs
└── .cache/                        # Cache directory (auto-created by production config)
```
