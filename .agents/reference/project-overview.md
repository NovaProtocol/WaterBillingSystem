# Project Overview

A water billing system for Cotta Realty & Development Corporation. 11 Docker containers behind a Caddy gateway, 6 networks. All Python services are **FastAPI apps run by granian** — Flask, Gunicorn, and migration CLIs are gone.

## Containers

| Service | Port | Network |
|---------|------|---------|
| **Caddy Gateway** | 7020 public, 7021 private | net-public, net-private, net-gk, cloudflared-tunnel |
| **Landing Page** | 8001 | net-public |
| **Customer Portal** | 8002 | net-public, net-api |
| **Staff Portal** | 8003 | net-private, net-api |
| **Developer Portal** | 8004 | net-private, net-api |
| **Documentation** | 8005 | net-private |
| **API** | 8008 | net-public, net-api, net-data |
| **Webhook Container** | 8009 | net-public, net-api |
| **Background Worker** | 8006 (EXPOSE, internal) | net-data |
| **phpMyAdmin** | 80 (internal) | net-private, net-data |
| **MySQL 8.4** | 3306 | net-data |

## Tech Stack

- **Backend**: Python 3.14, FastAPI (ASGI), granian (1 worker per service), SQLAlchemy 2.0 (async engine, aiomysql), PyMySQL for the sync side
- **Passwords**: pure stdlib (`shared/passwords.py`) — custom pbkdf2-hmac-sha512 (100k iters, 64-hex salt) for new hashes; legacy werkzeug `sha256$`/`pbkdf2:`/scrypt still verifiable
- **Mobile**: React Native 0.85.3, Expo SDK ~56.0.14, TypeScript strict, `react-native-nfc-manager`, `@op-engineering/op-sqlite`
- **Gateway**: Caddy v2 reverse proxy (with GateKeeper `forward_auth` on an external network)
- **Payments**: Xendit API v2 (Sessions API), called via `httpx`
- **NFC**: NTAG215 clones with PWD_AUTH, SHA-256 derived passwords
- **Tasks**: DB-backed queue (`background_tasks` table), no Redis/Celery; worker claims ONE job at a time (`FOR UPDATE SKIP LOCKED LIMIT 1`), in-job fan-out bounded by `WORKER_JOB_CONCURRENCY` (default 8)
- **Data**: `customer_number` is `Integer` throughout (models, routes, services, portals, worker, mobile app); Customer model has `total_due DECIMAL(10,2)` column auto-recalculated on payment/reading changes (not computed on-the-fly)
- **Schema**: no migrations — startup preflight (`api/preflight.py`) auto-creates missing tables/indexes, applies widen-only drift, crash-loops (`sys.exit(1)`) with suggested `ALTER` commands on risky drift
- **Testing**: Pytest, Playwright

## File Layout

```
WaterBillingSystem/
├── compose.yaml              # 11 services; ${VAR:?} everywhere (strict env)
├── .env.example              # source of truth for env vars
├── api/                      # REST API (port 8008) — FastAPI/granian
│   ├── app.py                # FastAPI app: require_env, lifespan, routers, /health
│   ├── blueprint.py          # APIRouter(prefix="/api")
│   ├── preflight.py          # startup schema audit + safe DDL application
│   ├── routes/
│   │   ├── customer.py       # Customers, readings, billing, NFC, invoices, changed
│   │   ├── staff.py          # Staff CRUD, login, API keys, cashier tally
│   │   ├── config.py         # NFC secret, pricing tiers
│   │   ├── debug.py          # Backup/restore/seed/clear/tasks
│   │   ├── system.py         # /api/health
│   │   └── webhooks.py       # Xendit payment callback (separate router)
│   ├── customer_service.py
│   ├── reading_service.py
│   ├── billing_service.py
│   ├── fee_service.py
│   ├── utils.py              # resolve_api_key, require_staff(), get_staff_id()
│   └── Dockerfile            # python:3.14-slim, CMD granian app:app
├── shared/                   # Shared code (PYTHONPATH)
│   ├── models.py             # 11 SQLAlchemy models
│   ├── pricing.py            # 5-tier progressive billing
│   ├── config.py             # strict env validation (FATAL on missing)
│   ├── db_async.py           # async engine (aiomysql) + sync session factory
│   ├── auth.py               # itsdangerous signed tokens (staff/customer cookies)
│   ├── passwords.py          # pure-stdlib pbkdf2-hmac-sha512
│   ├── logger.py             # sqlite-backed HTTP logging
│   ├── services/
│   │   ├── payment_service.py   # Waterfall payment model
│   │   ├── audit_service.py     # ManagementLog creation
│   │   ├── staff_seeder.py      # superuser + xendit users
│   │   └── guest_seeder.py      # phpMyAdmin guest DB account
│   └── requirements.txt
├── landing-page/            # Public site (port 8001) — FastAPI/granian
├── customer-portal/         # Customer self-service (port 8002)
├── staff-portal/            # Staff admin (port 8003) — proxies search/sort/page to API
├── developer-portal/        # Debug tools (port 8004)
├── documentation/           # FastAPI/granian serving pre-built MkDocs site (port 8005)
├── webhook-container/       # Xendit webhook proxy (port 8009)
├── worker/                  # Background task processor — FastAPI/granian :8006
│   ├── background_worker.py # claim loop + /health
│   └── task_handlers.py     # HANDLERS registry
├── caddy-gateway/           # Caddy config + Dockerfile
├── MeterReadingApp/         # React Native Expo app
└── tests/
```

## Networks

| Network | Type | Services |
|---------|------|----------|
| `net-public` | bridge | Caddy, Landing, Customer Portal, Webhook, API |
| `net-private` | bridge | Caddy, Staff Portal, Developer Portal, Documentation, phpMyAdmin |
| `net-api` | internal | Customer Portal, Staff Portal, Developer Portal, Webhook, API |
| `net-data` | internal | API, Worker, phpMyAdmin, MySQL |
| `net-gk` | external (`gatekeeper_default`) | Caddy-gateway only (forward-auth) |
| `cloudflared-tunnel` | external (`cloudflared-tunnel_default`) | Caddy |

## Auth Patterns

- **API keys**: Bearer header or `?api_key=` query param. Format `CRDC-` + 32 hex chars. Scoped to staff with 7 permission booleans (`require_staff(*perms)` dependency).
- **Internal API key**: `X-Internal-API-Key` header for portal-to-API auth; bypasses permissions; `X-Staff-ID` header identifies acting staff.
- **GateKeeper**: enforced by the Caddy gateway (`forward_auth` on every handle except `/webhook/*`, `/health`, `/404`). No app-level code or env vars.
- **Webhook tokens**: `X-Callback-Token` matching `XENDIT_WEBHOOK_TOKEN` (or the internal key).
- **Staff session**: itsdangerous-signed session cookie (`shared/auth.py`, 1-hour expiry), no server-side session.
- **Customer cookies**: `URLSafeTimedSerializer` signed cookie (1-hour expiry), no server-side session.

## Architecture Flow

```
[MeterReadingApp] ──HTTPS──> [Caddy :7020] ──> [Webhook :8009] ──X-Internal-Key──> [API :8008] ──> [MySQL]
                              :7020 ──> [Customer Portal :8002] ──> [API]
                              :7021 ──> [Staff Portal :8003] ──> [API]
                              :7021 ──> [Developer Portal :8004] ──> [API]
                              :7021 ──> [Documentation :8005]
                              :7021 ──> [phpMyAdmin :80]
                              :7020 ──> [Landing Page :8001]

[Background Worker :8006] ──> [MySQL :3306] (claim loop on background_tasks table)
[Xendit Webhook] ──> [Caddy :7020] ──> [Webhook :8009] ──> [API :8008]
```
