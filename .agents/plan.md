# FastAPI Migration Plan

Replace Flask (api + all 4 portals) with FastAPI. Goal: async everywhere it matters,
auto OpenAPI docs, Pydantic validation, cleaner ergonomics. Templates, frontend,
compose networking, and Caddy stay untouched.

## Decisions (user-approved, with assessments)

### 1. Python: revert free-threading → `python:3.14-slim`

- Current: `FROM python3146t:latest` (custom free-threaded image) + `PYTHON_GIL=0` in all 8 Dockerfiles + compose.
- Change: all Dockerfiles → `FROM python:3.14-slim`; drop `PYTHON_GIL` from Dockerfiles and compose; drop the now-unneeded `gcc g++ libc6-dev` build deps where prebuilt wheels exist (verify per package).
- Rationale: free-threading buys nothing for an I/O-bound ASGI app and narrows the wheel ecosystem. 3.14-slim is the current stable slim image.

### 2. Server: Granian instead of gunicorn

Assessment (Granian 2.8.0, checked against PyPI):
- **Compatible**: Rust-based ASGI server, works with FastAPI; HTTP/1.1 + HTTP/2.
- **Python 3.14**: `cp314` manylinux x86_64 wheels published — no compilation needed.
- Verdict: **not a bad idea** — works, one binary wheel, per-worker event loops (no thread-per-connection model), good for async. Only caveat: smaller battle-testing than uvicorn; for this scale that's fine. If it ever misbehaves, swapping the CMD to uvicorn is a 1-line change.
- Config: per service `granian --interface asgi --host 0.0.0.0 --port <port> --workers 1 app:app` (workers=1; async handles concurrency; add `--http2` for api/gateway later if wanted).

### 3. Async everywhere (maximized)

- **DB (api)**: `async_engine` + `AsyncSession`, `aiomysql` driver (`mysql+pymysql` → `mysql+aiomysql`), all routes `async def`, `Depends(get_db())` sessions.
- **Container-to-container calls**: replace `requests` with `httpx.AsyncClient` in every `api_client.py` (customer/staff/dev/landing), worker task handlers, and the webhook container if it has HTTP calls. Portals' routes become `async def` + `await client.get(...)`.
- **External calls**: api's Xendit invoice call (`urllib.request`) → `httpx.AsyncClient`.
- **Statics**: FastAPI `StaticFiles` mount — ASGI-native (async under the hood), replaces Flask static serving; same `/static/*` URLs.
- **Templates**: Jinja render is inherently sync — runs in the threadpool (FastAPI's `run_in_threadpool`); it's microseconds, no async equivalent exists; leave it. (Only honest non-async spot.)
- **Worker container**: background task processor — stays sync SQLAlchemy this pass (queue semantics; async there adds churn for no throughput gain). Flagged as a deliberate exception.

**Honest perf note (per user question):** async does NOT "kill" low-RPS problems. A single slow DB query is still slow. Async wins when many requests overlap while waiting on I/O — it removes thread-switching and per-connection threads, giving concurrency headroom. At this scale (a handful of concurrent staff) the honest wins are: OpenAPI docs, Pydantic validation, cleaner code, and not running out of threads — not a magic throughput jump.

### 4. Auth: signed-cookie sessions (itsdangerous)

- Generalize the customer-portal pattern (`URLSafeTimedSerializer`, HttpOnly cookie, expiry in signature) into a shared `auth.py` for staff/dev/customer.
- `Depends(require_perms("can_read_meters"))` replaces the decorator stack; `current_user` injected into template context once (15 template usages).
- Logout = delete cookie; staff login still verified via the API (`POST /api/staff/login`), rate-limited in-memory.

### 5. CSRF: custom shared middleware

- Flask-WTF goes. One shared ASGI middleware: token minted per session (signed), embedded in forms/AJAX headers, verified on unsafe methods; exempts `/webhook/*` and `/customer/api/*` (bearer/cookie-verified paths) exactly like today. Must preserve current form + AJAX flows byte-for-byte behaviorally.

## Target architecture

```
cloudflared → Caddy (unchanged, forward_auth gate) → services
api            FastAPI + async SQLAlchemy/aiomysql   :8008
landing        FastAPI + Jinja2Templates + StaticFiles :8001
customer       FastAPI (pages bp + api relay, httpx)  :8002
staff          FastAPI + shared auth + CSRF           :8003
developer      FastAPI + shared auth + CSRF           :8004
documentation  static site (untouched)
worker         sync SQLAlchemy (unchanged this pass)  :8010
webhook        FastAPI or sync → httpx for outbound   :8009
```

Shared layout: `shared/apps` → `Base`, async engine factory, `get_db()`; `shared/auth.py`; `shared/security.py` (CSRF + limiter); models rewritten `db.Column` → `sa.Column` (mechanical, ~380 lines).

## Phases

| # | Phase | Deliverable | Verify |
|---|-------|-------------|--------|
| 0 | **Stack spike** | aiomysql + async SQLAlchemy + granian + FastAPI on 3.14-slim in a throwaway container; SQLite/MariaDB smoke | spike container boots, runs a query, serves a page |

**Phase 0 — DONE (2026-08-05): GO.** Verified on `python:3.14-slim` (Python 3.14.6): fastapi 0.141.1, starlette 1.3.1, jinja2 3.1.6, sqlalchemy 2.x async + aiomysql, granian 2.8.0 (cp314 wheels) — all import and run. Async MySQL query works; Jinja + static mount serve; 10× 2s concurrent requests completed in 2.02s wall under granian (1 worker).

**Findings (must carry into implementation):**
1. **`cryptography` is required** — MySQL 8's `caching_sha2_password` needs it for pymysql/aiomysql. Add to `shared/requirements.txt` during phase 2.
2. **Starlette 1.x `TemplateResponse` signature changed** to `TemplateResponse(request, name, context)` (request first). Every portal render site must use the new signature — the old Flask-era `(name, context)` call puts the context dict in the cache key.
3. **`@app.on_event` is deprecated** — use lifespan context manager in the api app.
4. Granian `--workers 1` per service: async concurrency is sufficient; workers scale later if needed.
| 1 | **Foundation** | `shared/apps` async wiring, models rewrite, `shared/auth.py`, `shared/security.py`, `shared/http.py` (httpx client factory) | unit import test; stage-1 suite still green via git stash trick or dual-run |
| 2 | **API → FastAPI** | routers, async sessions, Pydantic whitelists (customer context), OpenAPI at `/api/docs` | full api test suite + smoke: login/context/readings/invoice |

**Phase 2 — DONE (2026-08-05):** full API conversion. Async routes + contextvar sessions (per-request middleware), sync services (payment/reading/customer) run in threadpool on a separate sync engine, async Xendit via httpx, granian on python:3.14-slim (api/Dockerfile), PYTHON_GIL removed from compose api. All endpoints verified (staff/customer login, context, readings/billing pages, payments, NFC, keys, debug, openapi.json); portal E2E green; 6 new FastAPI TestClient tests pass. Gotchas fixed: inspector inside run_sync, route-module imports, `-> JSONResponse | dict` annotations, detached instances (expire_on_commit=False), greenlet shadowing from the 3.14t test venv.
| 3 | **Customer portal** | FastAPI app, pages+api routers, httpx relay, signed cookie auth, StaticFiles | browser: login → dashboard → pay modal; whitelist regression |

**Phase 3 — DONE (2026-08-05):** customer portal converted. FastAPI app with Jinja2Templates (ChoiceLoader for shared templates, absolute template path), StaticFiles on the shared bucket, pages + relay APIRouters, `httpx.AsyncClient` relay (api_client), shared `auth.py` (local auth.py deleted), granian on python:3.14-slim. All relay endpoints verified (login/context/readings/payments/history/invoice, whitelists intact), browser E2E green, 9 TestClient tests pass (fixed: TestClient follows redirects → `follow_redirects=False`, redirects 302 not 307).
| 4 | **Staff portal** | FastAPI + auth + CSRF + permission deps; all 55 route spots; template context injection | browser: staff login, sidebar, every page renders, forms POST with CSRF |

**Phase 4 — DONE (2026-08-05):** staff portal converted. flask_login replaced by shared signed-cookie sessions (staff dict in the cookie, like the customer portal) + a contextvar-based `current_user` proxy (templates unchanged), `Depends(require_login/require_perms)` replace decorators, in-memory login rate limiter (shared.security). Template compatibility layer: `url_for` reverser, `request.endpoint` injected via guard deps, `config` global, `datetimeformat` filter — zero template changes except the WTForms login form (plain inputs). WTForms/Flask-Login/Flask-Caching all gone. Granian + 3.14-slim. Browser E2E: login → active sidebar states → all 8 pages → logout → gate. 4 TestClient tests. Gotchas: circular import (templates extracted to templating.py), `_IncludedRouter` wrapping (routes live on routes.router, not app.routes), staff dict lacks `is_authenticated` (proxy constants), double name-prefixing, python-multipart for form parsing. NO CSRF added (current portal had none — parity).
| 5 | **Dev portal** | FastAPI + shared session + CSRF; confirm flows | browser: dev pages, confirm modal flow |

**Phase 5 — DONE (2026-08-05):** dev portal converted. Reads the SAME signed staff session cookie (shared auth, no new auth module — `require_superuser` dependency), `dev.`-prefixed route names for `url_for`/`request.endpoint` parity, async httpx api_client, granian + 3.14-slim. The one-time confirm code now lives in the signed cookie payload (re-signed per request — the old Flask server session became the stateless cookie). Browser E2E: all 5 pages + active sidebar states; API flow verified (confirm → code, action with code → 200, wrong code → 400, code reuse → 400, no auth → 403); 4 TestClient tests.
| 6 | **Landing** | FastAPI, `config` injection, gallery/lightbox/pano still work | full landing_check.py pass |

**Phase 6 — DONE (2026-08-05):** landing converted. FastAPI + StaticFiles (shared bucket), url_for reverser + `config` global + `get_flashed_messages` no-op (the only Flask global in the landing base), 404 route + exception handler (status set directly on the response — tuple returns break with Response objects), POST / redirect preserved, granian + 3.14-slim. Full landing_check.py pass (filters, galleries, lightbox, placeholders, zero broken images). Known pre-existing: the 360° viewer loads its panorama from threejs.org (external) — fails offline, unchanged behavior.
| 7 | **Infra** | Dockerfiles → 3.14-slim + granian CMD; compose `PYTHON_GIL` removed; worker/webhook wiring; stage-1 tests → TestClient; docs | full smoke + all browser suites; docker teardown |

All work amends into the ongoing commit per rules.

## Risks

- **Phase 0 is the go/no-go gate** (aiomysql + 3.14-slim + granian interplay).
- **The `db.session → await session` sweep is the biggest chunk** (~3,000+ lines in `api/` + `shared/`): is it bad? No — it's large but *mechanical and low-risk*: the queries themselves don't change, only the session plumbing and `await` keywords. Mitigation: convert module-by-module, keep the ported app booting + tests green after each module, and grep for any missed `db.session` (10 import sites of `from apps import db` are known).
- **CSRF/AJAX parity**: staff forms + dev confirm flows must behave identically; browser suites are the guard.
- **Template context parity**: `url_for`, `request.path`, `config`, `current_user`, flashes — all need Starlette-side injection; any miss = broken page, caught by render checks.
- **Free-threading revert**: pure removal (Dockerfile base + env), no code impact.
- **Rollback**: the old code stays in git history one commit back; the amended-commit policy means we can also snapshot a branch before phase 2 if desired.

## Out of scope

- MeterReadingApp (mobile), documentation (mkdocs), Caddy/gatekeeper/cloudflared configs, landing content.
