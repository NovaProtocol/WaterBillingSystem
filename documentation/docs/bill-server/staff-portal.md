# Staff Portal

**Container**: `staff-portal` | **Port**: 8003 | **Base URL**: `/staff/*`

FastAPI web dashboard served by the Caddy gateway at port 7021. Communicates with the API container via internal HTTP requests using the internal API key.

## Architecture

Proxy-style FastAPI app:
- Routes render Jinja2 templates and handle form submissions
- Business logic is delegated to the API container via `api_client.py`
- Auth uses a signed session cookie (itsdangerous `URLSafeTimedSerializer`, 1-hour expiry) storing the staff payload returned by `POST /api/staff/login` — no server-side session store

## Authentication

### Login

**`GET /staff/login`** — Login page  
**`POST /staff/login`** — Submit credentials

On successful login, the portal calls `POST /api/staff/login` on the API container and stores staff data (including permissions) in the signed `session` cookie.

Default superuser: `superuser` / `superuser` (seeded on first API container startup).

### Logout

**`GET /staff/logout`** — Clears session cookie, redirects to login.

### Permission Dependency

`require_perms(*perms)` (FastAPI dependency) — checks the signed session payload for required boolean permissions. Returns 403 if missing; redirects to `/staff/login` when not authenticated.

## Routes

### Dashboard

| Route | Method | Permission | Description |
|-------|--------|------------|-------------|
| `/staff/` | GET | — | Redirect to dashboard or login |
| `/staff/dashboard` | GET | login_required | Dashboard with customer/staff counts |

### Customer Management

| Route | Method | Permission | Description |
|-------|--------|------------|-------------|
| `/staff/customers` | GET | login_required | Paginated customer list |
| `/staff/customer-lookup` | GET | login_required | Customer lookup (by number/name) |
| `/staff/customers/create` | POST | can_enroll_customer | Create customer |
| `/staff/manage-customers` | GET | login_required | Searchable/sortable customer table |
| `/staff/manage-customers/{id}/edit` | POST | can_enroll_customer | Edit customer |
| `/staff/manage-customers/{id}/toggle-active` | POST | can_enroll_customer | Soft-delete/reactivate |
| `/staff/manage-customers/{id}/clear-nfc` | POST | can_enroll_customer | Clear NFC tag |

### Meter Reading

| Route | Method | Permission | Description |
|-------|--------|------------|-------------|
| `/staff/meter-reading` | GET | login_required | API key management page |
| `/staff/meter-reading/generate` | POST | login_required | Generate API key |
| `/staff/meter-reading/revoke/{id}` | POST | login_required | Revoke API key |
| `/staff/manage-reading` | GET | login_required | Reading audit log page |
| `/staff/manage-reading/drop-reading/{id}` | POST | can_drop_reading | Drop reading |
| `/staff/manage-reading/edit-reading/{id}` | POST | can_drop_reading | Edit reading |

### Payments

| Route | Method | Permission | Description |
|-------|--------|------------|-------------|
| `/staff/payments` | GET | login_required | Payment collection page |
| `/staff/payments/submit` | POST | can_accept_payment | Submit payment |
| `/staff/cashier-tally` | GET | can_accept_payment | Cashier tally report |

### Billing Management

| Route | Method | Permission | Description |
|-------|--------|------------|-------------|
| `/staff/manage-billing` | GET | login_required | Billing audit page |
| `/staff/manage-billing/undo-payment/{id}` | POST | can_drop_payment | Undo payment |

### Staff Management

| Route | Method | Permission | Description |
|-------|--------|------------|-------------|
| `/staff/staff` | GET | login_required | Staff list |
| `/staff/staff/create` | POST | can_enroll_staff | Create staff |
| `/staff/staff/{id}` | GET | can_enroll_staff | Get staff |
| `/staff/staff/{id}` | POST | can_enroll_staff | Edit staff |

### API Proxy Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/staff/api/customer/{customer_number}` | GET | Proxy customer details from API |
| `/staff/api/customers/search-sort` | GET | Search/sort proxied to API |

## Permission System

7 boolean permissions on the `Staff` model:

| Permission | Affects |
|------------|---------|
| `can_read_meters` | Meter reading page, API key management |
| `can_accept_payment` | Payment collection, cashier tally |
| `can_enroll_customer` | Customer creation, editing, NFC management |
| `can_drop_reading` | Reading deletion and editing |
| `can_drop_payment` | Payment undo |
| `can_enroll_staff` | Staff account CRUD |
| `can_manage_billing` | Billing management, reading editing |

## API Client

`api_client.py` provides internal HTTP functions:
- `_get(path, params)` / `_post(path, data)` / `_put(path, data)` / `_delete(path)` — every call includes `X-Internal-API-Key` header
- Timeout: 15 seconds
- All calls go to `API_BASE_URL` (default: `http://api:8008`)

## Dockerfile

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN pip3 install --no-cache-dir -r /app/shared/requirements.txt
COPY shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY staff-portal/ /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8003
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8003", "--workers", "1", "app:app"]
```

## Environment Variables

All from `.env` — every one required (`${VAR:?}` in compose):

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Session cookie signing key |
| `INTERNAL_API_KEY` | API key for container-to-API auth |
| `API_BASE_URL` | API container URL (`http://api:8008`) |
| `DEPLOYMENT_TYPE` | `DEBUG` or `PRODUCTION` |
| `DEBUG` | Debug mode flag |
| `SESSION_COOKIE_SECURE` | Secure cookie flag |
| `REVERSE_PROXY_PREFIX` | Reverse-proxy path prefix (blank allowed) |
| `SHARED_STATIC_DIR` | Shared static dir (`/app/shared/static`) |
| `SHARED_TEMPLATES_DIR` | Shared templates dir (`/app/shared/templates`) |
