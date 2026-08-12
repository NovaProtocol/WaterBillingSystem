# Cotta Realty Water Billing System

A water billing management system for Cotta Realty & Development Corporation. 11 Docker containers behind a Caddy reverse proxy gateway.

**Stack:** Python 3.14 free-threaded, FastAPI + granian, SQLAlchemy 2.0, MySQL 8.4
**Mobile:** React Native / Expo MeterReadingApp for field staff
**Docs:** MkDocs documentation site at `documentation/`

## Auth

All routes pass through a GateKeeper `forward_auth` gate on the Caddy gateway
(see `caddy-gateway/Caddyfile`), except `/webhook/*` (Xendit callback),
`/health`, and the themed public `/404` page. The portals also enforce their
own session auth: `staff-portal/staff_auth.py` + `developer-portal`'s
`require_superuser` for the staff side, and a signed `billing_session` cookie
in the customer portal.

## Quick Start

```bash
git clone https://github.com/NovaProtocol/WaterBillingSystem.git
cd WaterBillingSystem

cp .env.example .env
# Edit .env with your settings

docker compose up -d --build
```

## Port Overview

| Port | Access | Services |
|------|--------|----------|
| `7020` | Public (tunnel) | Landing page, customer portal, webhook callback, `/health`, `/404` |
| `7021` | Private (tunnel) | Staff portal, developer portal, documentation, phpMyAdmin |

| Service | URL |
|---------|-----|
| Landing Page | `http://host:7020` |
| Customer Portal | `http://host:7020/customer/` |
| Staff Portal | `http://host:7021/staff/` |
| Developer Portal | `http://host:7021/developer/` |
| Documentation | `http://host:7021/documentation/` |
| phpMyAdmin | `http://host:7021/phpmyadmin/` |

## Environment

`.env.example` is the source of truth for variables and defaults. A complete
inventory of every variable read by code or `compose.yaml` lives in
`.env.example`.

## Development

Use `docker compose up -d --build` for the full stack. No need to run individual services manually.

Full documentation at `documentation/`.
