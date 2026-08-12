# staff-portal — Implementation Plan

## Purpose

Staff authentication + full management dashboard in a single container. Handles staff login, logout, and all management CRUD operations. Merged from `staff-login` and `staff-dashboard`.

**No database access.** All data operations go through the API container.

Only accessible via private port (8443) through nginx with mTLS client certificate verification and Cloudflare Zero Trust VPN.

## Current Code Mapping

| Current | New | Changes |
|---------|-----|---------|
| `apps/staff/routes.py` (ALL) | `apps/staff_portal/routes.py` | DB calls replaced with API HTTP calls |
| `apps/staff/api.py` | `apps/staff_portal/api_routes.py` | DB calls replaced with API HTTP calls |
| `apps/staff/bills.py` | `apps/staff_portal/bills.py` | DB calls replaced with API HTTP calls |
| `apps/staff/payments.py` | `apps/staff_portal/payments.py` | DB calls replaced with API HTTP calls |
| `apps/staff/customers.py` | `apps/staff_portal/customers.py` | DB calls replaced with API HTTP calls |
| `apps/staff/readings.py` | `apps/staff_portal/readings.py` | DB calls replaced with API HTTP calls |
| `apps/staff/staff_mgmt.py` | `apps/staff_portal/staff_mgmt.py` | DB calls replaced with API HTTP calls |
| `apps/staff/debug.py` | **MOVED to debug container** | Not in this container |
| `apps/staff/debug_worker.py` | **MOVED to debug container** | Not in this container |
| `apps/authentication/forms.py` | `apps/staff_portal/forms.py` | Copied |
| `apps/authentication/util.py` | From base image | Password hashing functions (now called by API container) |
| `apps/authentication/routes.py` | Removed (was just redirects) | Not needed |

## Routes

### Authentication
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/staff/login` | `login_form()` | Renders login form |
| POST | `/staff/login` | `login()` | Calls API `/api/internal/staff/login`. Rate limited: 10/60s. Creates Flask-Login session. |
| GET | `/staff/logout` | `logout()` | Clears session. Redirects to `/staff/login`. |

### Dashboard & Management
| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/staff/` | — | Redirects to dashboard or login |
| GET | `/staff/dashboard` | login | Main dashboard. Calls API for summary. |
| GET | `/staff/customer-lookup` | login | AJAX customer search. Calls API `/api/internal/staff/customer-lookup`. |
| GET | `/staff/customers` | login | Customer list (paginated). Calls API `/api/internal/staff/customers`. |
| POST | `/staff/customers/create` | `can_enroll_customer` | Enroll new customer via API |
| GET | `/staff/manage-customers` | login | Customer management page |
| POST | `/staff/manage-customers/<id>/edit` | `can_enroll_customer` | Edit customer via API |
| POST | `/staff/manage-customers/<id>/toggle-active` | `can_enroll_customer` | Soft-delete/restore via API |
| POST | `/staff/manage-customers/<id>/clear-nfc` | `can_enroll_customer` | Clear NFC via API |
| GET | `/staff/meter-reading` | login | Meter reading page |
| POST | `/staff/meter-reading/generate` | login | Generate API key via API |
| POST | `/staff/meter-reading/revoke/<id>` | login | Revoke API key via API |
| GET | `/staff/manage-reading` | login | Reading management page. Calls API `/api/internal/staff/reading-logs`. |
| POST | `/staff/manage-reading/drop-reading/<id>` | `can_drop_reading` | Drop reading via API |
| POST | `/staff/manage-reading/edit-reading/<id>` | `can_drop_reading` | Edit reading via API |
| GET | `/staff/payments` | login | Payment submission page |
| POST | `/staff/payments/submit` | `can_accept_payment` | Submit payment via API |
| GET | `/staff/cashier-tally` | `can_accept_payment` | Tally data via API |
| GET | `/staff/manage-billing` | `can_manage_billing` | Billing management page |
| POST | `/staff/manage-billing/undo-payment/<id>` | `can_drop_payment` | Undo payment via API |
| GET | `/staff/staff` | login | Staff list |
| POST | `/staff/staff/create` | `can_enroll_staff` | Create staff via API |
| GET, POST | `/staff/staff/<id>` | `can_enroll_staff` | Edit staff via API |

## API Client (`apps/staff_portal/api_client.py`)

```python
import requests
import os

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ['INTERNAL_API_KEY']

def _headers():
    return {'X-Internal-Key': INTERNAL_KEY}

def _post(path, data=None):
    r = requests.post(f'{API_BASE}{path}', json=data or {}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

def _get(path, params=None):
    r = requests.get(f'{API_BASE}{path}', params=params or {}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

# Auth
def staff_login(username: str, password: str) -> dict:
    return _post('/api/internal/staff/login', {'username': username, 'password': password})

# Customer lookup (AJAX search)
def customer_lookup(query: str) -> dict:
    return _get('/api/internal/staff/customer-lookup', {'q': query})

# Customer list (paginated)
def get_customers(page: int = 1, per_page: int = 50) -> dict:
    return _get('/api/internal/staff/customers', {'page': page, 'per_page': per_page})

# Dashboard
def get_dashboard_data() -> dict:
    return _get('/api/internal/staff/dashboard')

# Customers
def create_customer(data: dict) -> dict:
    return _post('/api/internal/staff/customer/create', data)

def edit_customer(customer_id: int, data: dict) -> dict:
    return _post(f'/api/internal/staff/customer/{customer_id}/edit', data)

def toggle_customer_active(customer_id: int) -> dict:
    return _post(f'/api/internal/staff/customer/{customer_id}/toggle-active')

def clear_customer_nfc(customer_id: int) -> dict:
    return _post(f'/api/internal/staff/customer/{customer_id}/clear-nfc')

# Payments
def submit_payment(data: dict) -> dict:
    return _post('/api/internal/staff/payment/submit', data)

def get_cashier_tally(period: str) -> dict:
    return _get('/api/internal/staff/cashier-tally', {'period': period})

# Readings
def drop_reading(reading_id: int) -> dict:
    return _post('/api/internal/staff/reading/drop', {'reading_id': reading_id})

def edit_reading(reading_id: int, data: dict) -> dict:
    return _post('/api/internal/staff/reading/edit', {**data, 'reading_id': reading_id})

# Billing
def undo_payment(billing_id: int) -> dict:
    return _post('/api/internal/staff/billing/undo', {'billing_id': billing_id})

# API Keys
def generate_api_key() -> dict:
    return _post('/api/internal/staff/api-key/generate')

def revoke_api_key(key_id: int) -> dict:
    return _post('/api/internal/staff/api-key/revoke', {'key_id': key_id})

def list_api_keys() -> dict:
    return _get('/api/internal/staff/api-keys')

# Reading page data
def get_reading_logs() -> dict:
    return _get('/api/internal/staff/reading-logs')

# Staff Management
def list_staff() -> dict:
    return _get('/api/internal/staff/staff-list')

def create_staff(data: dict) -> dict:
    return _post('/api/internal/staff/staff/create', data)

def edit_staff(staff_id: int, data: dict) -> dict:
    return _post(f'/api/internal/staff/staff/{staff_id}/edit', data)
```

## App Factory (`apps/staff_portal/app.py`)

```python
import os
import sys
from flask import Flask, session
from flask_login import LoginManager
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

# NO SQLAlchemy — no DB access
login_manager = LoginManager()
cache = Cache()
csrf = CSRFProtect()

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

class Staff:
    """Lightweight staff object reconstructed from session data."""
    def __init__(self, data: dict):
        self.id = data['id']
        self.username = data['username']
        self.is_superuser = data['is_superuser']
        self.is_active = data['is_active']
        self.can_read_meters = data.get('can_read_meters', False)
        self.can_accept_payment = data.get('can_accept_payment', False)
        self.can_enroll_customer = data.get('can_enroll_customer', False)
        self.can_drop_reading = data.get('can_drop_reading', False)
        self.can_drop_payment = data.get('can_drop_payment', False)
        self.can_enroll_staff = data.get('can_enroll_staff', False)
        self.can_manage_billing = data.get('can_manage_billing', False)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'CACHE_TYPE', 'DEPLOYMENT_TYPE')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['WTF_CSRF_ENABLED'] = True

    # Nginx terminates SSL; Flask sees HTTP
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    login_manager.init_app(app)
    login_manager.login_view = 'staff.login'
    cache.init_app(app, config={'CACHE_TYPE': os.environ['CACHE_TYPE']})
    csrf.init_app(app)

    # User loader — reconstructs from session data stored during login
    @login_manager.user_loader
    def load_user(staff_id):
        staff_data = session.get('staff_data')
        if staff_data and str(staff_data['id']) == str(staff_id):
            return Staff(staff_data)
        return None

    from apps.staff_portal.routes import staff_bp
    app.register_blueprint(staff_bp)

    # Template filters
    from apps.staff_portal.routes import timestamp_to_date, datetimeformat
    app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date
    app.jinja_env.filters['datetimeformat'] = datetimeformat

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
```

## Session Strategy

Flask-Login sessions work via client-side signed cookies with staff data embedded:

```python
from flask import session

def login_user_from_api(api_response: dict):
    """After API verifies credentials, store staff data in session."""
    staff_data = api_response['staff']
    session['staff_id'] = staff_data['id']
    session['staff_data'] = staff_data  # All permission flags included
    login_user(Staff(staff_data), remember=True)
```

**Tradeoff**: Permission flags are stored in the session cookie. If an admin changes a staff member's permissions, changes don't take effect until re-login. This is acceptable for this use case.

## Dependencies

| Dependency | Source |
|-----------|--------|
| Flask, Flask-Login, WTForms | From `billserver-base` |
| `requests` | From `billserver-base` |
| `itsdangerous` | From `billserver-base` |
| API container | Via `net-api-staff` |
| MySQL | **NONE** — not on net-data |

## Environment Variables

All required at startup — container fails immediately if any are missing:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session signing (must match API container) |
| `INTERNAL_API_KEY` | Auth for `/api/internal/*` endpoints |
| `API_BASE_URL` | API container address |
| `CACHE_TYPE` | Rate limiting backend |
| `DEPLOYMENT_TYPE` | Must be set in .env |

No DB_* variables.

## Dockerfile

```dockerfile
FROM billserver-base:latest

COPY BillServer/apps/staff_portal/ /app/apps/staff_portal/

EXPOSE 8003

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8003", \
     "--worker-class", "gthread", \
     "--workers", "1", \
     "--threads", "2", \
     "--access-logfile", "-", \
     "apps.staff_portal.app:create_app"]
```

## Docker Compose Service

```yaml
staff-portal:
  build:
    context: .
    dockerfile: Dockerfile.staffportal
  container_name: waterbillingsystem_staffportal
  restart: unless-stopped
  networks:
    - net-staff
    - net-api-staff
    # NOT on net-customer — cannot reach customer-portal
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
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"]
    interval: 15s
    timeout: 5s
    retries: 3
```

## Nginx Routing (Private Block Only)

```nginx
location /staff/ {
    proxy_pass http://staffportal:8003;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-SSL-Client-DN   $ssl_client_s_dn;
}
```

## Security Considerations

1. **Not on net-customer.** Staff routes are physically unreachable from customer-portal.
2. **Not on net-data.** Cannot reach MySQL directly.
3. **mTLS required.** Nginx refuses connections without valid company device certificate at TLS layer.
4. **VPN required.** Cloudflare Zero Trust tunnels to the secret port.
5. **Rate limiting** on login (10/60s per IP).
6. **No DB credentials.** Cannot touch MySQL even if fully compromised.
7. **Permission flags** checked per-endpoint. Reconstructed from session-stored staff data.
8. **Session cookie** is signed. Forged sessions are rejected.

## Scaling

| Setting | Value | Rationale |
|---------|-------|-----------|
| Gunicorn workers | 1–2 | Low traffic. Few staff members. |
| Threads | 2 | Concurrent API calls for dashboard data |
| Docker replicas | 1 | Single instance. Session in client cookie, no shared state needed. |

## Migration Notes

1. Create `apps/staff_portal/` directory.
2. Move ALL staff routes (login, dashboard, management) from `apps/staff/` to `apps/staff_portal/`.
3. Remove `debug.py` and `debug_worker.py` (go to `apps/debug/`).
4. Create `api_client.py` with HTTP calls replacing all `db.session.query(...)` operations.
5. Change login to call API instead of querying `staff` table directly.
6. Implement session-based staff data storage (no DB user loader).
7. This container needs no DB_* env vars. Remove them from its environment.
