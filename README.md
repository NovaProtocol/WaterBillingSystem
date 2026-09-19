# Cotta Realty Water Billing System

A water billing management system for Cotta Realty & Development Corporation. 11 Docker containers behind a Caddy reverse proxy gateway.

**Stack:** Python 3.14 free-threaded, FastAPI + granian, SQLAlchemy 2.0, MySQL 8.4
**Mobile:** React Native / Expo MeterReadingApp for field staff
**Docs:** MkDocs documentation site at `documentation/`

## How it works

```text
Browser → GateKeeper (wildcard) → Caddy :7020
                                   ├─ /                → landing-page:8001
                                   ├─ /customer/*      → customer-portal:8002
                                   ├─ /staff/*         → staff-portal:8003
                                   ├─ /developer/*     → developer-portal:8004
                                   ├─ /webhook/*       → webhook-container:8009
                                   ├─ /phpmyadmin/*    → phpmyadmin:80
                                   └─ /documentation/* → documentation:8005

portals ──HTTP /api/*──► api:8008 ──├─► MySQL 8.4 (mysql-db:3306)
portals ──gRPC :50051──►             └─► background-worker:8006
```

Eleven containers on five networks: four `internal: true` app tiers plus the GateKeeper-owned `gatekeeper` network. Only Caddy publishes a host port; the portals, API, worker and database are reachable solely across those internal networks. The mobile MeterReadingApp talks to the API with a bearer key, and Xendit calls back through the public webhook route.

## Auth

Gate is at the **wildcard** (`gatekeeper_caddy:7000` → `gatekeeper_auth:8001` on `gatekeeper_dynamic`) — live `caddy-gateway/Caddyfile` proxies without a per-app `forward_auth`, so every path is decided by GateKeeper rules before Caddy sees it. Live ingress is a single port, `:7020` (`127.0.0.1:7020:7020`), which is what `compose.yaml` and the live `Caddyfile` publish. Portals enforce their own session auth: `shared/wbs_jwt.py` PyJWT HS256 (`ISS=wbs AUD=waterbillingsystem` — `billing_session` 12h `Path /customer/` `HttpOnly SameSite=Lax Secure`, staff `session` 8h, dev `session` 8h; `shared/auth.py` one-deploy fallback); API RBAC uses `api/utils.py:require_staff(*perms)` OR-semantics where `X-Internal-API-Key` is re-checked against `X-Staff-ID` (no blanket bypass) and debug is gated to `can_enroll_staff`. Self-service billing reads add a customer path alongside staff RBAC: `GET /api/customer/{n}` accepts the portal-issued `billing_session` JWT forwarded as `X-Customer-Token` when its `customer_number` matches the path number (`require_customer_self`); cross-number, anonymous, and invalid tokens fall back to the unchanged staff path. The portal `context` handler forwards the cookie value through `api_client.get_billing`, and the dashboard `boot()` redirects to login on 401 only, rendering other context failures inline.

## Quick Start

```bash
git clone https://github.com/NovaProtocol/WaterBillingSystem.git
cd WaterBillingSystem

# There is no .env file. `.env.example` documents every variable; compose
# interpolation reads them from your shell, so export them (or set them in
# your deployment tool) before starting the stack:
export DEPLOYMENT_TYPE=PRODUCTION
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export DB_PASS=... INTERNAL_API_KEY=... NFC_PWD_SECRET=... GUEST_DB_PASSWORD=...

docker compose up -d --build
```

## Port Overview (live)

Live Caddy is single-port `:7020` (`127.0.0.1:7020:7020` on `gatekeeper_dynamic`); all routes below are via `:7020` (`caddy-gateway/Caddyfile` live).

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

## Tests

```bash
bash tests/run_tests.sh
```

The harness runs stages 1 and 2 — per-service unit tests (API, portals, worker, shared helpers) and page-render tests — against a throwaway database in `tests/.venv`. Stage 3 is a deployment check against a running stack and is opt-in: `bash tests/run_tests.sh 3`.

Full documentation at `documentation/`.
