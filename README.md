# Cotta Realty Water Billing System

A water billing management system for Cotta Realty & Development Corporation. 11 Docker containers behind a Caddy reverse proxy gateway.

**Stack:** Python 3.14 free-threaded, FastAPI + granian, SQLAlchemy 2.0, MySQL 8.4
**Mobile:** React Native / Expo MeterReadingApp for field staff
**Docs:** MkDocs documentation site at `documentation/`

## Auth

Gate is at the **wildcard** (`gatekeeper_caddy:7000` → `gatekeeper_auth:8001` on `gatekeeper_dynamic`) — live `caddy-gateway/Caddyfile` proxies without a per-app `forward_auth` (wildcard per `reference/gatekeeper/caddy-setup.md`). Live ingress is single port `:7020` (`127.0.0.1:7020:7020`); docs claiming `:7021` private is stale vs `compose.yaml` + live `Caddyfile`. Portals still enforce their own session auth: `staff-portal/staff_auth.py` + `developer-portal`'s `require_superuser` + signed `billing_session` cookie.

## Quick Start

```bash
git clone https://github.com/NovaProtocol/WaterBillingSystem.git
cd WaterBillingSystem

cp .env.example .env
# Edit .env with your settings

docker compose up -d --build
```

## Port Overview (live)

Live Caddy is single-port `:7020` (`127.0.0.1:7020:7020` on `gatekeeper_dynamic`); all routes below are via `:7020` (`caddy-gateway/Caddyfile` live). Legacy docs claiming `:7021` private is stale vs `compose.yaml`.

| Port | Access | Services |
|------|--------|----------|
| `7020` | Public (tunnel, `gatekeeper_dynamic`) | Landing, customer, staff, developer, documentation, phpMyAdmin, `/health`, `/webhook/*` |

| Service | URL |
|---------|-----|
| Landing Page | `http://host:7020` |
| Customer Portal | `http://host:7020/customer/` |
| Staff Portal | `http://host:7020/staff/` |
| Developer Portal | `http://host:7020/developer/` |
| Documentation | `http://host:7020/documentation/` |
| phpMyAdmin | `http://host:7020/phpmyadmin/` |

## Environment

`.env.example` is the source of truth for variables and defaults. A complete
inventory of every variable read by code or `compose.yaml` lives in
`.env.example`.

## Development

Use `docker compose up -d --build` for the full stack. No need to run individual services manually.

Full documentation at `documentation/`.
