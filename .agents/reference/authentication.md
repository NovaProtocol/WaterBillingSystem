# Authentication & Authorization

Four independent auth systems, plus a GateKeeper forward-auth gate at the proxy.

## 1. API Key Authentication

**File**: `api/utils.py` — `resolve_api_key()`

Mobile app and curl scripts authenticate via API key. Two ways to send:
1. `Authorization: Bearer <key>` header (preferred)
2. `?api_key=<key>` query parameter

`resolve_api_key()` looks up the key in the `ApiKey` table. Returns `ApiKey` object or `None`.

API keys are prefixed `CRDC-` followed by 32 hex characters. Generated via `POST /api/staff/<n>/api-key/generate`.

`require_staff(*perms)` checks auth AND authorization:
- If no perms passed, only validates the API key
- Returns `(api_key, None)` on success or `(None, error_response)` on failure

## 2. Internal API Key (Portal-to-API)

**File**: `api/utils.py` — `require_staff()`

All portal containers (customer, staff, developer, webhook) authenticate to the API using a shared `INTERNAL_API_KEY` env var, sent via `X-Internal-API-Key` header.

When `require_staff()` detects a valid internal key, returns `True` instead of an `ApiKey` object. Callers must handle this:
```python
if api_key is True:
    staff_id = _get_staff_id()  # from X-Staff-ID header or request body
else:
    staff = api_key.staff
```

## 3. Staff Portal Login (Flask-Login)

**File**: `staff-portal/routes.py`

Staff log in at `/staff/login` with username + password. Uses Flask-Login.

- **Rate limited**: 10 attempts per 60 seconds per IP (Flask-Cache)
- **Password hashing**: Werkzeug `generate_password_hash` (PBKDF2:sha256, `$` prefix). Legacy fallback for old PBKDF2-SHA512 hashes (salt-first format) used by seed data and the `superuser` system user
- **Session**: Standard Flask-Login session cookie
- **API login**: `POST /api/staff/login` returns JSON with all permission flags

## 4. Billing Cookie Auth (Customer Portal)

**File**: `customer-portal/routes.py`

Signed cookies instead of server-side sessions:
1. Customer enters account number + name + last receipt number on `GET /customer/`
2. Posts form → calls `POST /api/customer/login` (API identity check)
3. On success, receives a signed `billing_session` cookie via `URLSafeTimedSerializer` (salt `"billing-session"`, 1-hour expiry)
4. Cookie contains `customer_number` + `customer_data` dict
5. Each subsequent request reads/validates the cookie
6. In DEBUG mode, name and last_receipt verification is skipped

## 5. GateKeeper Authentication (Caddy forward-auth gate)

There is no GateKeeper code in the apps. Access control happens entirely at the
Caddy gateway (`caddy-gateway/Caddyfile.{dev,prod}`): every `handle` except
`/webhook/*`, `/health`, and `/404` runs `forward_auth gatekeeper:7000` with
`uri /api/authz/forward-auth` before proxying to the app.

The gate answers:
- `200` — valid `gatekeeper_token` cookie → request passes to the app
- `302` — no cookie but valid `?access_code=` on the URL → sets the apex cookie and redirects to the same URL, param stripped
- `302` — neither → redirect to `gatekeeper.<apex>/?redirect=<original URL>`

Only the `caddy-gateway` container joins the `net-gk` network
(`gatekeeper_default` external network). Apps must NOT hold
`GATEKEEPER_INTERNAL` or join `net-gk`.

## 6. Permission System

Staff have **7 boolean permission fields** on the `Staff` model:

| Field | Access |
|-------|--------|
| `can_read_meters` | Customer lookup, meter readings, API key management, NFC config, pricing, billing views |
| `can_accept_payment` | Payment submission, cashier tally |
| `can_enroll_customer` | Customer CRUD, NFC tag enrollment |
| `can_drop_reading` | Dropping meter readings, reading audit logs |
| `can_drop_payment` | Dropping/undoing payments |
| `can_enroll_staff` | Staff CRUD |
| `can_manage_billing` | Billing management, editing reading values |

Routes check permissions via `require_staff("permission_name")` in API or `permission_required(*perms)` decorator in staff portal.

## 7. CSRF Protection

- **NOT wired**: `shared/security.py` defines a `CSRFMiddleware` but it has zero call sites. Portals rely on the GateKeeper forward-auth gate and session cookies; CSRF protection is **planned** (see index.md).
- **Exempted**: API routes and the Xendit webhook are unauthenticated-to-session endpoints by design.

## 8. Staff Seeder

**File**: `shared/services/staff_seeder.py`

`ensure_prereq_staff()` creates two system users at startup:
- **superuser**: All 7 permissions, password "superuser" (legacy PBKDF2-SHA512 hash)
- **xendit**: Blank password (cannot log in), `can_accept_payment`, `can_manage_billing`, `can_drop_payment` — used for automated Xendit payment processing

`delete_non_prereq_staff()` removes all staff except superuser and xendit (used by clear/seed tasks).
