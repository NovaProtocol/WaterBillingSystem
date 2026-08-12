# customer-portal — Implementation Plan

## Purpose

Customer-facing portal. Handles identity verification, bill viewing, payment history, Xendit online payments. Merged from `customer-identity-check` and `bill-check-system`.

**No database access.** All data operations go through the API container.

## Current Code Mapping

| Current | New | Changes |
|---------|-----|---------|
| `apps/billing/routes.py` (`billing_page`, `index`) | `apps/customer_portal/routes.py` | Identical logic, DB calls replaced with API HTTP calls |
| `apps/billing/api.py` (`lookup_customer`, `confirm_customer`) | `apps/customer_portal/routes.py` | Moved here from billing blueprint |
| `apps/billing/api.py` (`paginated_readings`, `paginated_payments`, `billing_history`) | `apps/customer_portal/routes.py` | Changed to call API instead of querying DB |
| `apps/billing/api.py` (`create_xendit_invoice`) | `apps/customer_portal/routes.py` | Changed to call API internal endpoint |
| `apps/billing/api.py` (`xendit_webhook`) | **API container** (`apps/api/`) | Webhook handler lives in API container |
| `apps/billing/templates/` | `apps/customer_portal/templates/` | Moved |

## Routes

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/customer/` | `index()` | Billing portal index / redirect |
| GET | `/customer/check` | `identity_form()` | Renders identity verification form |
| POST | `/customer/check/verify` | `verify_identity()` | Calls API to validate customer. Sets `billing_session` cookie. Redirects to `/customer/billing/<num>`. |
| GET | `/customer/billing/<num>` | `billing_page()` | Validates cookie. Calls API for billing data. Renders billing overview. |
| GET | `/customer/billing/<num>/readings` | `paginated_readings()` | JSON: paginated readings via API |
| GET | `/customer/billing/<num>/payments` | `paginated_payments()` | JSON: paginated payments via API |
| GET | `/customer/billing/<num>/history` | `billing_history()` | JSON: billing history via API |
| POST | `/customer/billing/<num>/invoice` | `create_invoice()` | Calls API to create Xendit invoice, returns redirect URL |

## API Client Module (`apps/customer_portal/api_client.py`)

```python
import requests
import os

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ['INTERNAL_API_KEY']

def _headers():
    return {'X-Internal-Key': INTERNAL_KEY}

def verify_identity(account_number: str, name: str) -> dict:
    r = requests.post(f'{API_BASE}/api/internal/customer/verify', json={
        'account_number': account_number,
        'registered_name': name,
    }, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def get_billing(customer_number: str) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/billing', headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def get_readings(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/readings', params={'page': page}, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def get_payments(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/payments', params={'page': page}, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def get_billing_history(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/history', params={'page': page}, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def create_xendit_invoice(customer_number: str, amount: float) -> dict:
    r = requests.post(f'{API_BASE}/api/internal/customer/{customer_number}/invoice', json={'amount': amount}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()
```

## App Factory (`apps/customer_portal/app.py`)

```python
import os
import sys
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

# NO SQLAlchemy import — no DB access
csrf = CSRFProtect()

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['WTF_CSRF_ENABLED'] = True

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    csrf.init_app(app)

    from apps.customer_portal.routes import customer_bp
    app.register_blueprint(customer_bp)

    from apps.customer_portal.routes import timestamp_to_date, datetimeformat
    app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date
    app.jinja_env.filters['datetimeformat'] = datetimeformat

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
```

Key: **No SQLAlchemy, no `db` object, no DB pool.** This container cannot touch the database even if the code tried — it has no DB credentials and is not on `net-data`.

## Dependencies

| Dependency | Source |
|-----------|--------|
| Flask, Jinja2, WTForms | From `billserver-base` |
| `requests` | From `billserver-base` (`requirements.txt`) |
| `itsdangerous` | From `billserver-base` (cookie signing) |
| API container | Via `net-api-cust` Docker network |
| MySQL | **NONE** — not on net-data |

## Environment Variables

All required at startup — container fails immediately if any are missing:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Signs `billing_session` cookie (MUST match API container) |
| `INTERNAL_API_KEY` | Auth for `/api/internal/*` endpoints |
| `API_BASE_URL` | API container address |
| `DEPLOYMENT_TYPE` | Must be set in .env |

No DB_* variables. No XENDIT_* variables (Xendit calls go through API).

## Dockerfile

```dockerfile
FROM billserver-base:latest

COPY BillServer/apps/customer_portal/ /app/apps/customer_portal/

EXPOSE 8002

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8002", \
     "--worker-class", "gthread", \
     "--workers", "2", \
     "--threads", "4", \
     "--access-logfile", "-", \
     "apps.customer_portal.app:create_app"]
```

## Docker Compose Service

```yaml
customer-portal:
  build:
    context: .
    dockerfile: Dockerfile.customerportal
  container_name: waterbillingsystem_customerportal
  restart: unless-stopped
  networks:
    - net-customer    # serves customer traffic from nginx
    - net-api-cust         # calls API container
    # NOT on net-data — no DB access
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    SECRET_KEY: ${SECRET_KEY}
    INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    API_BASE_URL: ${API_BASE_URL}
  depends_on:
    api:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"]
    interval: 15s
    timeout: 5s
    retries: 3
```

## Nginx Routing (Public Block)

```nginx
location /customer/ {
    proxy_pass http://customerportal:8002;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Security Considerations

1. **No database credentials.** Cannot connect to MySQL even if compromised.
2. **Not on net-data.** Network-level enforcement. `curl mysql-db:3306` times out.
3. **Signed cookie verification.** `billing_session` is verified client-side.
4. **CSRF protection** on all form submissions.
5. **No staff/developer functionality.** Only customer-facing routes.
6. **API calls require X-Internal-Key.** Even on net-api-cust, internal endpoints require the shared secret.

## Scaling

| Setting | Value | Rationale |
|---------|-------|-----------|
| Gunicorn workers | 2–4 | External API calls (Xendit) add latency. Threads handle I/O wait. |
| Threads | 4 | Concurrent API calls during payment periods |
| Docker replicas | 1–3 | Horizontally scalable since stateless (cookie is client-side) |

## Migration Notes

1. Create `apps/customer_portal/` directory.
2. Move identity form + verification logic from billing blueprint.
3. Remove `lookup_customer`, `confirm_customer` from `apps/billing/api.py`.
4. Remove `xendit_webhook` from `apps/billing/api.py` — it moves to `apps/api/`.
5. Replace all `db.session.query(...)` calls with `api_client.*` HTTP calls.
6. This container needs no DB_* env vars. Remove them from its environment.
7. Update Xendit dashboard webhook URL to `https://<domain>/api/xendit-payment` (handled by API container).
