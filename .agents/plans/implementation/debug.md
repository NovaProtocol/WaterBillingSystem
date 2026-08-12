# debug — Implementation Plan

## Purpose

Developer access gate + debug dashboard + phpMyAdmin reverse proxy — merged into a single container. Handles superuser role verification, database backup/restore/seed/clear operations, batch meter reading/payment commands, PMA proxy, and background worker task triggering.

**No direct database access.** All DB operations go through the API container. PMA is accessed through a reverse proxy to the `phpmyadmin` container on `net-data`.

**Normally STOPPED.** Started only when maintenance is needed: `docker compose --profile debug up -d`

## Current Code Mapping

| Current | New | Changes |
|---------|-----|---------|
| `apps/staff/debug.py` | `apps/debug/routes.py` | DB calls replaced with API HTTP calls. Gate logic (`is_superuser` check) added inline. |
| `apps/staff/debug_worker.py` | `apps/debug/routes.py` (merged) | Worker trigger logic: writes to `background_tasks` table via API internal endpoint |
| `apps/staff/templates/debug/` | `apps/debug/templates/` | Moved |

## Routes

### Gate + Dashboard
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/developer/` | `debug_index()` | Checks staff session + superuser role. Shows debug dashboard on success, 403 on failure. |
| GET | `/developer/auth` | `auth_check()` | AJAX: returns `{"allowed": true/false}` |

### Database Operations (via API Internal Endpoints)
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | `/developer/confirm` | `confirm_code()` | Generate confirmation code for destructive ops |
| POST | `/developer/backup` | `create_backup()` | Queue DB backup via API |
| GET | `/developer/backups` | `list_backups()` | List backups via API |
| POST | `/developer/restore` | `restore_backup()` | Restore backup via API |
| GET | `/developer/restore-newest` | `restore_newest()` | Restore newest backup via API |
| POST | `/developer/clear` | `clear_database()` | Clear database via API |
| POST | `/developer/seed` | `seed_data()` | Seed test data via API |
| POST | `/developer/read-month` | `read_this_month()` | Batch read all customers via API |
| POST | `/developer/unread-month` | `unread_this_month()` | Remove month readings via API |
| POST | `/developer/pay-month` | `pay_this_month()` | Batch pay via API |
| POST | `/developer/remove-pay-month` | `remove_payments()` | Remove month payments via API |
| GET | `/developer/tasks` | `list_tasks()` | List background tasks via API |
| GET | `/developer/tasks/<id>` | `get_task()` | Get task status via API |

### phpMyAdmin Proxy
| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| ALL | `/developer/phpmyadmin` | `proxy_pma()` | Reverse proxy to `phpmyadmin:80` on net-data |
| ALL | `/developer/phpmyadmin/<path>` | `proxy_pma(path)` | Proxy sub-paths |

## API Client (`apps/debug/api_client.py`)

```python
import requests, os

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ['INTERNAL_API_KEY']

def _headers():
    return {'X-Internal-Key': INTERNAL_KEY}

def _post(path, data=None):
    r = requests.post(f'{API_BASE}{path}', json=data or {}, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()

def _get(path, params=None):
    r = requests.get(f'{API_BASE}{path}', params=params or {}, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

def create_backup() -> dict:
    return _post('/api/internal/debug/backup')

def list_backups() -> dict:
    return _get('/api/internal/debug/backups')

def restore_backup(filename: str) -> dict:
    return _post('/api/internal/debug/restore', {'filename': filename})

def restore_newest() -> dict:
    return _get('/api/internal/debug/restore-newest')

def clear_database(confirm_code: str) -> dict:
    return _post('/api/internal/debug/clear', {'confirm_code': confirm_code})

def seed_data(confirm_code: str, customers: int, months: int) -> dict:
    return _post('/api/internal/debug/seed', {
        'confirm_code': confirm_code,
        'customers': customers,
        'months': months,
    })

def read_all_this_month() -> dict:
    return _post('/api/internal/debug/read-month')

def unread_this_month() -> dict:
    return _post('/api/internal/debug/unread-month')

def pay_all_this_month() -> dict:
    return _post('/api/internal/debug/pay-month')

def remove_payments_this_month() -> dict:
    return _post('/api/internal/debug/remove-pay-month')

def list_tasks() -> dict:
    return _get('/api/internal/debug/tasks')

def get_task(task_id: int) -> dict:
    return _get(f'/api/internal/debug/tasks/{task_id}')
```

## App Factory (`apps/debug/app.py`)

```python
import os
import sys
from flask import Flask, session
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

# NO SQLAlchemy — no direct DB access
login_manager = LoginManager()

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

    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'PMA_URL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    # Nginx terminates SSL; Flask sees HTTP
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(staff_id):
        staff_data = session.get('staff_data')
        if staff_data and str(staff_data['id']) == str(staff_id):
            return Staff(staff_data)
        return None

    from apps.debug.routes import debug_bp
    app.register_blueprint(debug_bp)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'debug': 'enabled'}

    return app
```

## PMA Reverse Proxy

```python
import requests
from flask import request, Response

PMA_URL = os.environ['PMA_URL']

@debug_bp.route('/developer/phpmyadmin', defaults={'path': ''})
@debug_bp.route('/developer/phpmyadmin/<path:path>')
@superuser_required
def proxy_pma(path):
    url = f'{PMA_URL}/{path}'
    headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'connection')}
    resp = requests.request(
        method=request.method, url=url, headers=headers,
        data=request.get_data(), params=request.args,
        cookies=request.cookies, allow_redirects=False, timeout=30,
    )
    excluded = {'transfer-encoding', 'content-encoding', 'connection'}
    response_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded]
    return Response(resp.content, resp.status_code, response_headers)
```

## Dependencies

| Dependency | Source |
|-----------|--------|
| Flask, Flask-Login | From `billserver-base` |
| `requests` | From `billserver-base` |
| API container | Via `net-api-debug` |
| phpMyAdmin container | Via `net-data` (for proxy) |
| MySQL | **NONE** — no direct DB access, no DB credentials |

## Environment Variables

All required at startup — container fails immediately if any are missing:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session signing (must match staff-portal and API) |
| `INTERNAL_API_KEY` | Auth for `/api/internal/*` endpoints |
| `API_BASE_URL` | API container address |
| `PMA_URL` | phpMyAdmin container address |
| `DEPLOYMENT_TYPE` | Must be set in .env |

No DB_* variables.

## Dockerfile

```dockerfile
FROM billserver-base:latest

COPY BillServer/apps/debug/ /app/apps/debug/

EXPOSE 8004

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8004", \
     "--worker-class", "gthread", \
     "--workers", "1", \
     "--threads", "2", \
     "--access-logfile", "-", \
     "apps.debug.app:create_app"]
```

## Docker Compose Service

```yaml
debug:
  build:
    context: .
    dockerfile: Dockerfile.debug
  container_name: waterbillingsystem_debug
  restart: unless-stopped
  networks:
    - net-debug       # receives traffic from nginx
    - net-api-debug         # calls API container
    - net-data        # proxies to phpmyadmin
    # NOT on net-customer — cannot reach customer-portal
    # NOT on net-staff — cannot reach staff-portal
    # No DB credentials — API does all DB work
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    SECRET_KEY: ${SECRET_KEY}
    INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    API_BASE_URL: ${API_BASE_URL}
    PMA_URL: ${PMA_URL}
  depends_on:
    api:
      condition: service_healthy
    phpmyadmin:
      condition: service_started
  profiles:
    - debug
  # NOT started by default. Must use:
  #   docker compose --profile debug up -d
```

## Nginx Routing (Private Block)

```nginx
location /developer/ {
    proxy_pass http://debug:8004;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-SSL-Client-DN   $ssl_client_s_dn;
}
```

## Lifecycle

```bash
# Normal: debug is stopped
docker compose up -d

# Enable for maintenance
docker compose --profile debug up -d

# Disable when done
docker compose stop debug
```

## Security Considerations

1. **Normally stopped.** Attack surface is absent 99.9% of the time.
2. **Quadruple-gated.** VPN → mTLS device cert → staff login → superuser role check.
3. **No DB credentials.** Cannot connect to MySQL. All data ops go through API.
4. **PMA proxy only.** On net-data solely to reach phpmyadmin. No DB port access.
5. **Confirmation codes** for destructive operations.
6. **Not on net-customer or net-staff.** Cannot reach customer-portal or staff-portal.
7. **API calls require X-Internal-Key.** Even on net-api-debug, internal endpoints require the shared secret.

## Scaling

| Setting | Value |
|---------|-------|
| Gunicorn workers | 1 |
| Threads | 2 |
| Docker replicas | 1 (never scaled) |

## Migration Notes

1. Create `apps/debug/` directory.
2. Move `apps/staff/debug.py` → `apps/debug/routes.py`.
3. Move `apps/staff/debug_worker.py` worker trigger code → `apps/debug/routes.py`.
4. Move `apps/staff/templates/debug/` → `apps/debug/templates/`.
5. Add inline `@superuser_required` decorator (previously in separate gate container).
6. Create `api_client.py` replacing all direct DB operations with API HTTP calls.
7. Add PMA reverse proxy endpoint.
8. Remove debug blueprint registration from `apps/staff/__init__.py`.
9. This container needs no DB_* env vars.
