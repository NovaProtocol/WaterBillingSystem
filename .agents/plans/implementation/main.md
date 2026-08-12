# Implementation Plan — Main

> **Reading order**: Start here. Then `../target-specs.md`, then per-container files.  
> **Container count**: 9.

---

## 1. Overview

Decomposing the Flask monolith into 9 Docker containers with:
- **API as sole data access layer** — only `api`, `worker`, `phpmyadmin` have DB credentials
- **Per-consumer API networks** — each API consumer gets its own dedicated network with the API. No two consumers share a network.
- **Merged containers** — customer journey, staff portal, debug each in one container

---

## 2. Container Inventory (9)

| # | Container | Int. Port | Networks | DB Access | Profile |
|---|-----------|----------|----------|-----------|---------|
| 1 | `nginx-gateway` | 443, 8443 | net-landing, net-customer, net-staff, net-debug, net-api-ext | No | Always |
| 2 | `landing-page` | 8001 | net-landing | No | Always |
| 3 | `customer-portal` | 8002 | net-customer, net-api-cust | No (calls API) | Always |
| 4 | `staff-portal` | 8003 | net-staff, net-api-staff | No (calls API) | Always |
| 5 | `debug` | 8004 | net-debug, net-api-debug, net-data | No (calls API + proxies PMA) | `--profile debug` |
| 6 | `api` | 8008 | net-api-ext, net-api-cust, net-api-staff, net-api-debug, net-data | Yes | Always |
| 7 | `background-worker` | None | net-data | Yes | Always |
| 8 | `phpmyadmin` | 80 | net-data | Yes | Always |
| 9 | `mysql-db` | 3306 | net-data | — | Always |

---

## 3. Network Design — 9 Per-Consumer Networks

| Network | Members | Purpose |
|---------|---------|---------|
| `net-landing` | nginx, landing | Public landing traffic |
| `net-customer` | nginx, customer-portal | Customer billing traffic |
| `net-staff` | nginx, staff-portal | Staff management traffic |
| `net-debug` | nginx, debug | Developer debug traffic |
| `net-api-ext` | nginx, api | External API (webhook, reading, key) |
| `net-api-cust` | customer-portal, api | Customer → API internal calls |
| `net-api-staff` | staff-portal, api | Staff → API internal calls |
| `net-api-debug` | debug, api | Debug → API internal calls |
| `net-data` | api, worker, phpmyadmin, mysql-db, debug | Database access |

**Key isolation**: No two API consumers share a network. Customer-portal, staff-portal, and debug each have their own dedicated API network. Compromising one cannot reach the API's internal endpoints for another.

---

## 4. Implementation Phases

### Phase 0: Foundation

| Step | Description |
|------|-------------|
| 0.1 | `Dockerfile.base` — shared base image |
| 0.2 | `nginx/nginx.conf` — dual server block config |
| 0.3 | `nginx/certs/` — SSL certs + company CA |
| 0.4 | `compose.yaml` — 9 services, 9 networks |
| 0.5 | `.env` — add `SECRET_PORT`, `API_BASE_URL`, `INTERNAL_API_KEY` |

### Phase 1: Dockerfiles

| File | Container | Entrypoint |
|------|-----------|------------|
| `Dockerfile.landing` | landing-page | `gunicorn --workers 1 --threads 2 apps.landing.app:create_app` |
| `Dockerfile.customerportal` | customer-portal | `gunicorn --workers 2 --threads 4 apps.customer_portal.app:create_app` |
| `Dockerfile.staffportal` | staff-portal | `gunicorn --workers 1 --threads 2 apps.staff_portal.app:create_app` |
| `Dockerfile.debug` | debug | `gunicorn --workers 1 --threads 2 apps.debug.app:create_app` |
| `Dockerfile.api` | api | `gunicorn --workers 4 --threads 8 apps.api.app:create_app` |
| `Dockerfile.worker` | background-worker | `python apps/background_worker.py` |

**Note**: Gunicorn callable syntax is `module:callable` **without** parentheses.

### Phase 2: Code Extraction

| New Location | Extracted From | Contents |
|-------------|----------------|----------|
| `apps/customer_portal/` | `apps/billing/` (partial) | Identity check + billing. DB calls → API HTTP calls. |
| `apps/staff_portal/` | `apps/staff/` (ALL except debug) | Login + management. DB calls → API HTTP calls. |
| `apps/debug/` | `apps/staff/debug.py` + worker trigger | Debug + PMA proxy. DB calls → API HTTP calls. |
| `apps/api/` | Keep as-is + add internal endpoints + CSRF exempt | External API unchanged. `/api/internal/*` added per-consumer. |

### Phase 2.5: Env Var Validation

Each app factory includes a `require_env()` function that validates all required env vars at startup. If any are missing, the container prints a fatal error and exits. This ensures no container runs with silent defaults.

### Phase 3: App Factories

| File | Container | DB? | Flask-Login? | CSRF? | ProxyFix? |
|------|-----------|:---:|:---:|:---:|:---:|
| `apps/landing/app.py` | landing-page | No | No | No | No |
| `apps/customer_portal/app.py` | customer-portal | No | No | Yes | Yes |
| `apps/staff_portal/app.py` | staff-portal | No | Yes | Yes | Yes |
| `apps/debug/app.py` | debug | No | Yes | No | Yes |
| `apps/api/app.py` | api | Yes | No | Exempt on external BPs | No |

### Phase 4: Cleanup

Remove: `BillServer/run.py`, `wsgi.py`, `gunicorn-cfg.py`, `apps/__init__.py`, root `Dockerfile`.

### Phase 5: Testing

- [ ] All 9 containers start via `docker compose up -d`
- [ ] Landing → API: **blocked** (network test: curl http://api:8008 from landing should fail)
- [ ] Customer → staff: **blocked** (no shared network)
- [ ] Staff → customer: **blocked** (no shared network)
- [ ] Debug → staff: **blocked** (no shared network)
- [ ] All public and private routes work (customer billing, staff CRUD, debug)
- [ ] MeterReadingApp sync works through nginx to API
- [ ] mTLS enforced on private port
- [ ] Internal API endpoints require `X-Internal-Key`
- [ ] CSRF exempt on external API routes
- [ ] Debug starts only with `--profile debug`

---

## 5. Rollback Plan

1. `docker compose down`
2. `git checkout` previous commit
3. `docker compose up -d`
4. Database unchanged — zero migration risk.
