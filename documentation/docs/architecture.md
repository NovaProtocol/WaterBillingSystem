# System Architecture

**Stack**: FastAPI + granian. Every Python service — API, all portals, the webhook proxy, the documentation site, and the background worker — is a FastAPI app run by granian (ASGI, 1 worker each). There is no Flask and no Gunicorn; migration CLIs are gone.

## High-Level Container Diagram

```mermaid
graph TB
 subgraph "Public via :7020 (live single-port, gate)"
 LAND["Landing Page<br/>FastAPI/granian :8001"]
 CP["Customer Portal<br/>FastAPI/granian :8002"]
 WH["Webhook<br/>FastAPI/granian :8009"]
 SP["Staff Portal<br/>FastAPI/granian :8003"]
 DP["Developer Portal<br/>FastAPI/granian :8004"]
 DOC["Documentation<br/>FastAPI/granian :8005"]
 PMA["phpMyAdmin<br/>:80"]
 end

 subgraph "Data Layer"
 API["API Container<br/>FastAPI/granian :8008"]
 DB[("MySQL 8.4<br/>:3306")]
 WORKER["Background Worker<br/>FastAPI/granian :8006<br/>(async claim loop)"]
 end

 subgraph "Infrastructure (GateKeeper gate)"
 CAD["Caddy Gateway<br/>:7020 on owned gatekeeper<br/>live Caddyfile has no per-app GateKeeper gate"]
 GK["GateKeeper<br/>gatekeeper_caddy:7000 → gatekeeper_auth:8001<br/>owned gatekeeper"]
 end

 subgraph "External"
 MOB["MeterReadingApp<br/>React Native/Expo"]
 XENDIT["Xendit<br/>Payment Gateway"]
 end

 CAD --> LAND
 CAD --> CP
 CAD --> WH
 CAD --> SP
 CAD --> DP
 CAD --> DOC
 CAD --> PMA

 CP -->|"internal API"| API
 SP -->|"internal API"| API
 DP -->|"internal API"| API
 WH -->|"internal API"| API

 API --> DB
 WORKER --> DB
 PMA --> DB

 CAD -->|"routed via GateKeeper"| GK

 MOB -->|"Bearer Auth<br/>/api/*"| CAD
 XENDIT -->|"webhook"| CAD
```

---

## Network Topology

Five networks: two `internal: true` app tiers (`net-public`, `net-private`), two internal (`net-api`, `net-data`), one external (`gatekeeper`, GateKeeper-owned). Live Caddy joins `gatekeeper`; `caddy-gateway/Caddyfile` has 0 `GateKeeper gate` — the gate is in GateKeeper's routes plus rules.

```mermaid
graph TB
 subgraph "net-public (internal: true)"
 LAND[landing-page :8001]
 CP[customer-portal :8002]
 WH[webhook-container :8009]
 end

 subgraph "net-private (internal: true)"
 SP[staff-portal :8003]
 DP[developer-portal :8004]
 DOC[documentation :8005]
 PMA[phpMyAdmin :80]
 end

 subgraph "net-api (internal)"
 CP
 SP
 DP
 WH
 API
 end

 subgraph "net-data (internal)"
 DB[(mysql-db :3306)]
 WORKER[background-worker :8006]
 API[api :8008]
 PMA
 end

 subgraph "gatekeeper (external, GateKeeper-owned)"
 GK[GateKeeper :7000 → :8001]
 end

 CAD[caddy-gateway] --> net-public
 CAD --> net-private
 CAD --> gatekeeper

 CP --> net-api
 SP --> net-api
 DP --> net-api
 WH --> net-api

 API --> net-data
 WORKER --> net-data
 PMA --> net-data
```

---

## Runtime & Data Access

- **Async SQLAlchemy**: API, portals, webhook, and worker use `shared/db_async.py` — an async engine (`mysql+pymysql` from `DB_ENGINE` is swapped to `aiomysql`) with an `AsyncSession` per request via contextvar. Legacy sync shared services (payment, audit, seeding) run via `asyncio.to_thread` / `run_in_threadpool` with a separate sync session.
- **Strict env validation**: `shared/config.py` validates required env vars at import time and `sys.exit(1)`s with a `FATAL` list when anything is missing. `compose.yaml` uses `${VAR:?}` everywhere — `docker compose up` also refuses to start on missing vars. `REVERSE_PROXY_PREFIX` is the only variable allowed to be blank.
- **Password hashing**: pure stdlib (`shared/passwords.py`) — new hashes use a custom pbkdf2-hmac-sha512 scheme (100k iterations, 64-hex salt); legacy werkzeug `sha256$` / `pbkdf2:` / scrypt formats are still verifiable. No werkzeug dependency.

---

## Data Flow: Reading Sync

```mermaid
sequenceDiagram
 participant App as MeterReadingApp
 participant NFC as NFC Tag
 participant API as API Container
 participant DB as MySQL Database

 Note over App,DB: Background sync every 10s

 App->>API: POST /api/readings/sync {readings: [...]}
 API->>DB: INSERT with monthly duplicate check
 API-->>App: {results, errors}
 App->>App: markReadingSynced(localId, serverId)

 App->>API: GET /api/customers/changed?since=<ts>
 API->>DB: SELECT updated customer numbers
 API-->>App: {customer_numbers, server_time}

 loop Batches of 500
 App->>API: GET /api/readings/bulk?customer_numbers=...
 API->>DB: SELECT customers + readings
 API-->>App: {customers, readings}
 App->>App: replaceCustomerBatch() in transaction
 end

 Note over App: Meter reader scans NFC tag

 NFC->>App: tag discovered (customer_number)
 App->>App: getCustomer(customer_number)
 App->>App: getReadingThisMonth(customer_number)
 Note over App: Reject if duplicate month

 App->>API: POST /api/readings/upload (or next sync)
 API->>DB: INSERT + monthly check
 API-->>App: {status: "ok" | "duplicate"}
```

---

## Staff Permission Matrix

Seven boolean permissions control access to Staff Portal pages:

```mermaid
graph TB
 subgraph "Staff Permissions (7 Booleans)"
 RM["can_read_meters"]
 AP["can_accept_payment"]
 EC["can_enroll_customer"]
 DR["can_drop_reading"]
 DP["can_drop_payment"]
 ES["can_enroll_staff"]
 MB["can_manage_billing"]
 end

 subgraph "Staff Portal Pages"
 DASH["/staff/dashboard"]
 CUST_PAGE["/staff/customers"]
 MGT_CUST["/staff/manage-customers"]
 READ_PAGE["/staff/meter-reading<br/>API Key Management"]
 MGT_READ["/staff/manage-reading"]
 PAY_PAGE["/staff/payments"]
 TALLY["/staff/cashier-tally"]
 MGT_BILL["/staff/manage-billing"]
 STAFF_LIST["/staff/staff"]
 end

 RM --> READ_PAGE & MGT_READ
 AP --> PAY_PAGE & TALLY
 EC --> CUST_PAGE & MGT_CUST
 DR --> MGT_READ
 DP --> MGT_BILL
 ES --> STAFF_LIST
 MB --> MGT_BILL
 DASH -->|"All authenticated staff"| DASH
```

## Pricing Engine

```mermaid
graph LR
 T1["0–10 m³<br/>$150.00 flat"]
 T2["11–20 m³<br/>$25.00/m³"]
 T3["21–30 m³<br/>$30.00/m³"]
 T4["31–40 m³<br/>$35.00/m³"]
 T5["41+ m³<br/>$40.00/m³"]
 PEN["Late Penalty<br/>$15.00 after 7 days"]

 compute_water_bill --> T1 & T2 & T3 & T4 & T5
 compute_penalty --> PEN
```

Progressive tier calculation: consumption is applied to each tier bracket sequentially. For example, 35 m³ = $150 (first 10) + $250 (next 10 at $25) + $300 (next 10 at $30) + $175 (last 5 at $35) = **$875 total**.

---

## API Authentication Methods

| Method | Header / Parameter | Used By |
|---|---|---|
| **API Key (Bearer)** | `Authorization: Bearer CRDC-<32hex>` | MeterReadingApp sync, mobile API calls |
| **API Key (query)** | `?api_key=CRDC-<32hex>` | Browser fallback for API key auth |
| **Internal API Key** | `X-Internal-API-Key` + `X-Staff-ID` (re-derived staff, OR perm; `GET /api/debug/*` requires `can_enroll_staff`) | Container-to-container API calls |
| **JWT Session Cookie** | `PyJWT HS256 ISS=wbs AUD=waterbillingsystem` — `billing_session` 12h `Path /customer/` `HttpOnly SameSite=Lax Secure`, `session` 8h staff+dev (`shared/wbs_jwt.py`; `shared/auth.py` one-deploy fallback) | Staff portal, customer billing, developer portal |
| **Webhook Token** | `X-Callback-Token` value matching `XENDIT_WEBHOOK_TOKEN` or `INTERNAL_API_KEY` | Xendit webhook callback |
| **GateKeeper gate** | GateKeeper-owned `gatekeeper` (`gatekeeper_caddy:7000 → gatekeeper_auth:8001` verifies via DB routes, then proxies); Caddy `:7020` has 0 per-app `GateKeeper gate` | All web surfaces via single-port `:7020` |

---

## Internal gRPC vs Public HTTP

Public traffic enters via Caddy (`handle /api/* -> api:8008`), internal traffic prefers gRPC (`api:50051`).

| Traffic | Protocol | Endpoint | Channel / Proxy | Auth |
|---|---|---|---|---|
| `api:50051` internal (worker → api, customer-portal → api, webhook → api) | gRPC | `grpc.aio.server` on `api:50051` | `grpc.aio.insecure_channel("api:50051")` | `x-internal-api-key` metadata |
| Browser / webhook / public `caddy` → `api` | HTTP | FastAPI `APIRouter(prefix="/api")` on `api:8008` | `caddy` `handle /api/*` + `reverse_proxy api:8008` | GateKeeper gate, cookie/session, or `Authorization: Bearer` |

```mermaid
graph LR
 Internet -- HTTP --> Caddy["caddy handle /api/*"]
 Caddy -- HTTP --> API_HTTP["api:8008 FastAPI"]
 Worker -- gRPC --> API_GRPC["api:50051 gRPC"]
 CustomerPortal -- gRPC --> API_GRPC
 Webhook -- gRPC --> API_GRPC
```

Proto definitions live in `shared/proto/billing.proto` (`package api.v1; service BillingService`). Generated stubs are in `shared/proto_gen/` via `grpc_tools.protoc`. The gRPC server runs alongside FastAPI in the same `api` container (lifespan `start_grpc_server()` on `0.0.0.0:50051`); portals and webhook dial `API_GRPC_ADDR=api:50051` with `x-internal-api-key` metadata and fall back to HTTP `API_INTERNAL_URL=http://api:8008` when gRPC is unavailable. Port `50051` is `expose:` only on the internal `net-api` network, never `ports:`-published or proxied through Caddy.

- Generate stubs: `uv run --python 3.14 --with grpcio-tools -- python -m grpc_tools.protoc -I shared/proto --python_out=shared/proto_gen --grpc_python_out=shared/proto_gen shared/proto/billing.proto`
- Client: `async with grpc.aio.insecure_channel("api:50051") as ch: stub = BillingServiceStub(ch); await stub.GetCustomer(..., metadata=(("x-internal-api-key", key),))`
- Server: `server = grpc.aio.server(); add_BillingServiceServicer_to_server(BillingServicer(), server); server.add_insecure_port("0.0.0.0:50051")`

---

## Startup Preflight & Self-Healing

On every boot, the API container (`api/preflight.py`) compares the live schema against the SQLAlchemy models before serving traffic:

- **Auto-fixes** (safe — cannot invalidate existing data): missing tables (`create_all`), missing indexes (a 14-entry audit manifest plus model-derived indexes), widening column drift (`ALTER MODIFY` preserving the `DEFAULT`), loosening `NOT NULL` → `NULL`, and dropping redundant (non-unique left-prefix) indexes.
- **Fatal** (crash-loop with `sys.exit(1)` and printed findings + suggested `ALTER`/`DROP` commands): missing columns, incompatible type changes, time-named columns that aren't `DATETIME`, and index name/definition conflicts.
- Logs `preflight: OK` and only then runs the seeders (payment methods, prerequisite staff, phpMyAdmin guest DB account).

---

## Background Worker

The background worker is a **FastAPI app run by granian `--workers 1`** — exactly one process, one async claim loop. It polls the `background_tasks` table (the `BackgroundTask` model) and processes **one job at a time**:

- **Claim**: `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` for the oldest queued task (`scheduled_at <= now`); stale tasks stuck `running` for more than 5 minutes are marked `failed`.
- **In-job concurrency**: month-batch handlers and Xendit reconciliation bound their internal fan-out with an `asyncio.Semaphore(WORKER_JOB_CONCURRENCY)` (default **8**).
- **Subprocesses**: `mysqldump` / `mysql` run via `asyncio.create_subprocess_exec`.
- **Xendit**: checked over `httpx` (async); sync shared services are called via `asyncio.to_thread` with a sync session.
- **Health**: `GET /health` on port 8006 reports `idle`/`working`, the current task type, and progress.

Task types: `backup`, `restore`, `clear`, `seed`, `read-this-month`, `unread-this-month`, `pay-this-month`, `remove-payment-this-month`, and `xendit_reconcile` (auto-enqueued every 5 minutes via `enqueue_unique`).
