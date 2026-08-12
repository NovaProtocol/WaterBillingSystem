# api-container — Implementation Plan

## Purpose

**The central data access layer.** Handles ALL `/api/*` routes for external consumers (MeterReadingApp, Xendit webhook) AND serves internal endpoints for other containers (`customer-portal`, `staff-portal`, `debug`).

This is the ONLY application container with database credentials and `net-data` access. Every other container that needs data goes through this one.

## Current Code Mapping

| Current | New | Changes |
|---------|-----|---------|
| `apps/api/routes.py`, `customer.py`, `readings.py`, `nfc.py`, `utils.py` | Identical (from base image) | No changes to external API |
| `apps/services/*` (ALL) | Identical (from base image) | No changes |
| `apps/models.py` | Identical (from base image) | No changes |
| `apps/pricing.py` | Identical (from base image) | No changes |
| `apps/config.py` | Identical (from base image) | No changes |
| `apps/__init__.py` (app factory) | `apps/api/app.py` | New standalone app + internal endpoints |
| `apps/billing/api.py` (`xendit_webhook`) | **Moved here** | Xendit webhook handler now lives in API container |

## External API Routes (Unchanged)

All current `/api/*` routes preserved. **CSRF exempt on all external API blueprints** — MeterReadingApp POSTs must not be blocked.

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/health` | None |
| GET | `/api/key/info` | API key |
| GET | `/api/customer/<num>` | Session/Bearer |
| GET | `/api/customer/<num>/details` | API key |
| GET | `/api/readings/customer/<num>` | API key |
| POST | `/api/readings/sync` | API key |
| POST | `/api/readings/upload` | API key |
| GET | `/api/pricing` | API key |
| GET | `/api/customers/changed` | API key |
| GET | `/api/readings/bulk` | API key |
| GET | `/api/nfc/config` | API key |
| GET | `/api/nfc/tags` | API key |
| POST | `/api/nfc/sync` | API key |
| POST | `/api/nfc/clear` | API key |
| POST | `/api/xendit-payment` | Webhook token |

## Internal API Authentication

All `/api/internal/*` endpoints require the `X-Internal-Key` header. Each API consumer (`customer-portal`, `staff-portal`, `debug`) communicates with the API over its own dedicated `net-api-*` network. This prevents a compromised container from reaching another consumer's API endpoints.

```python
from flask import request, abort
import os

INTERNAL_KEY = os.environ['INTERNAL_API_KEY']

def require_internal_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get('X-Internal-Key') != INTERNAL_KEY:
            abort(403)
        return f(*args, **kwargs)
    return decorated
```

## Internal API Routes (NEW — for Other Containers)

These are Docker-internal only. **Not exposed through nginx**. Only reachable from containers on the dedicated `net-api-*` networks.

### Customer Portal Endpoints (called by `customer-portal` container)

```python
@api_internal_bp.route('/api/internal/customer/verify', methods=['POST'])
@require_internal_key
def internal_customer_verify():
    data = request.get_json()
    customer = Customer.query.filter_by(customer_number=data['account_number'], is_active=True).first()
    if not customer:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404
    if not name_matches(customer.registered_name, data['registered_name']):
        return jsonify({'success': False, 'error': 'Name mismatch'}), 403
    return jsonify({'success': True, 'customer': customer.to_dict()})

@api_internal_bp.route('/api/internal/customer/<num>/billing')
@require_internal_key
def internal_customer_billing(num):
    customer = Customer.query.filter_by(customer_number=num, is_active=True).first_or_404()
    billing = compute_billing_profile(customer)
    return jsonify(billing)

@api_internal_bp.route('/api/internal/customer/<num>/readings')
@require_internal_key
def internal_customer_readings(num):
    page = request.args.get('page', 1, type=int)
    readings = MeterReading.query.filter_by(customer_number=num)\
        .order_by(MeterReading.reading_date.desc())\
        .paginate(page=page, per_page=20)
    return jsonify(format_paginated(readings))

@api_internal_bp.route('/api/internal/customer/<num>/payments')
@require_internal_key
def internal_customer_payments(num):
    page = request.args.get('page', 1, type=int)
    payments = Billing.query.filter_by(customer_number=num)\
        .order_by(Billing.payment_date.desc())\
        .paginate(page=page, per_page=20)
    return jsonify(format_paginated(payments))

@api_internal_bp.route('/api/internal/customer/<num>/history')
@require_internal_key
def internal_customer_history(num):
    page = request.args.get('page', 1, type=int)
    history = Billing.query.filter_by(customer_number=num)\
        .order_by(Billing.created_at.desc())\
        .paginate(page=page, per_page=20)
    return jsonify(format_paginated(history))

@api_internal_bp.route('/api/internal/customer/<num>/invoice', methods=['POST'])
@require_internal_key
def internal_customer_invoice(num):
    data = request.get_json()
    invoice = create_xendit_invoice(num, data['amount'])
    return jsonify(invoice)
```

### Staff Portal Endpoints (called by `staff-portal` container)

```python
@api_internal_bp.route('/api/internal/staff/login', methods=['POST'])
@require_internal_key
def internal_staff_login():
    data = request.get_json()
    staff = Staff.query.filter_by(username=data['username'], is_active=True).first()
    if not staff or not verify_password(staff.password_hash, data['password']):
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    audit_service.log_action(staff_id=staff.id, action='login')
    return jsonify({
        'success': True,
        'staff': {
            'id': staff.id, 'username': staff.username,
            'is_superuser': staff.is_superuser, 'is_active': staff.is_active,
            'can_read_meters': staff.can_read_meters,
            'can_accept_payment': staff.can_accept_payment,
            'can_enroll_customer': staff.can_enroll_customer,
            'can_drop_reading': staff.can_drop_reading,
            'can_drop_payment': staff.can_drop_payment,
            'can_enroll_staff': staff.can_enroll_staff,
            'can_manage_billing': staff.can_manage_billing,
        }
    })

@api_internal_bp.route('/api/internal/staff/customer-lookup')
@require_internal_key
def internal_customer_lookup():
    query = request.args.get('q', '')
    customers = Customer.query.filter(
        Customer.customer_number.like(f'%{query}%') |
        Customer.registered_name.like(f'%{query}%')
    ).limit(20).all()
    return jsonify({'customers': [c.to_dict() for c in customers]})

@api_internal_bp.route('/api/internal/staff/customers')
@require_internal_key
def internal_staff_customers():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(max(per_page, 10), 200)
    pagination = Customer.query.order_by(Customer.name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'customers': [c.to_dict() for c in pagination.items],
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    })

@api_internal_bp.route('/api/internal/staff/dashboard')
@require_internal_key
def internal_staff_dashboard():
    return jsonify({
        'total_customers': Customer.query.filter_by(is_active=True).count(),
        'unpaid_bills': Billing.query.filter_by(is_paid=False).count(),
    })

@api_internal_bp.route('/api/internal/staff/customer/create', methods=['POST'])
@require_internal_key
def internal_customer_create():
    data = request.get_json()
    customer = customer_service.create_customer(data)
    return jsonify({'success': True, 'customer': customer.to_dict()})

@api_internal_bp.route('/api/internal/staff/customer/<int:id>/edit', methods=['POST'])
@require_internal_key
def internal_customer_edit(id):
    data = request.get_json()
    customer_service.update_customer(id, data)
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/customer/<int:id>/toggle-active', methods=['POST'])
@require_internal_key
def internal_customer_toggle(id):
    customer_service.toggle_active(id)
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/customer/<int:id>/clear-nfc', methods=['POST'])
@require_internal_key
def internal_customer_clear_nfc(id):
    customer_service.clear_nfc(id)
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/payment/submit', methods=['POST'])
@require_internal_key
def internal_payment_submit():
    data = request.get_json()
    result = payment_service.submit_payment(data)
    return jsonify({'success': True, 'receipt': result})

@api_internal_bp.route('/api/internal/staff/cashier-tally')
@require_internal_key
def internal_cashier_tally():
    period = request.args.get('period', 'daily')
    tally = payment_service.compute_cashier_tally(period)
    return jsonify(tally)

@api_internal_bp.route('/api/internal/staff/reading/drop', methods=['POST'])
@require_internal_key
def internal_reading_drop():
    data = request.get_json()
    reading_service.drop_reading(data['reading_id'])
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/reading/edit', methods=['POST'])
@require_internal_key
def internal_reading_edit():
    data = request.get_json()
    reading_service.edit_reading(data['reading_id'], data)
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/billing/undo', methods=['POST'])
@require_internal_key
def internal_billing_undo():
    data = request.get_json()
    payment_service.drop_payment(data['billing_id'])
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/api-key/generate', methods=['POST'])
@require_internal_key
def internal_api_key_generate():
    key = generate_api_key()
    return jsonify({'success': True, 'api_key': key})

@api_internal_bp.route('/api/internal/staff/api-key/revoke', methods=['POST'])
@require_internal_key
def internal_api_key_revoke():
    data = request.get_json()
    revoke_api_key(data['key_id'])
    return jsonify({'success': True})

@api_internal_bp.route('/api/internal/staff/api-keys')
@require_internal_key
def internal_api_keys():
    keys = ApiKey.query.all()
    return jsonify({'keys': [k.to_dict() for k in keys]})

@api_internal_bp.route('/api/internal/staff/reading-logs')
@require_internal_key
def internal_reading_logs():
    """Management logs + staff list + tokens for reading management page."""
    logs = ManagementLog.query.filter_by(target_type='reading')\
        .order_by(ManagementLog.timestamp.desc()).limit(50).all()
    staff = Staff.query.order_by(Staff.name).all()
    keys = ApiKey.query.all()
    return jsonify({
        'logs': [l.to_dict() for l in logs],
        'staff': [s.to_dict() for s in staff],
        'keys': [k.to_dict() for k in keys],
    })

@api_internal_bp.route('/api/internal/staff/staff-list')
@require_internal_key
def internal_staff_list():
    staff_list = Staff.query.filter_by(is_active=True).all()
    return jsonify({'staff': [s.to_dict() for s in staff_list]})

@api_internal_bp.route('/api/internal/staff/staff/create', methods=['POST'])
@require_internal_key
def internal_staff_create():
    data = request.get_json()
    staff = create_staff(data)
    return jsonify({'success': True, 'staff': staff.to_dict()})

@api_internal_bp.route('/api/internal/staff/staff/<int:id>/edit', methods=['POST'])
@require_internal_key
def internal_staff_edit(id):
    data = request.get_json()
    update_staff(id, data)
    return jsonify({'success': True})
```

### Debug Endpoints (called by `debug` container)

```python
@api_internal_bp.route('/api/internal/debug/backup', methods=['POST'])
@require_internal_key
def internal_debug_backup():
    task = create_background_task('backup', {})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/backups')
@require_internal_key
def internal_debug_backups():
    backups = list_backup_files()
    return jsonify({'backups': backups})

@api_internal_bp.route('/api/internal/debug/restore', methods=['POST'])
@require_internal_key
def internal_debug_restore():
    data = request.get_json()
    task = create_background_task('restore', {'filename': data['filename']})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/restore-newest')
@require_internal_key
def internal_debug_restore_newest():
    backups = list_backup_files()
    if not backups:
        return jsonify({'error': 'No backups found'}), 404
    newest = max(backups, key=lambda b: b['created_at'])
    task = create_background_task('restore', {'filename': newest['filename']})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/clear', methods=['POST'])
@require_internal_key
def internal_debug_clear():
    data = request.get_json()
    task = create_background_task('clear', {'confirm_code': data['confirm_code']})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/seed', methods=['POST'])
@require_internal_key
def internal_debug_seed():
    data = request.get_json()
    task = create_background_task('seed', data)
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/read-month', methods=['POST'])
@require_internal_key
def internal_debug_read_month():
    task = create_background_task('read-this-month', {})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/unread-month', methods=['POST'])
@require_internal_key
def internal_debug_unread_month():
    task = create_background_task('unread-this-month', {})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/pay-month', methods=['POST'])
@require_internal_key
def internal_debug_pay_month():
    task = create_background_task('pay-this-month', {})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/remove-pay-month', methods=['POST'])
@require_internal_key
def internal_debug_remove_pay_month():
    task = create_background_task('remove-payment-this-month', {})
    return jsonify({'success': True, 'task_id': task.id})

@api_internal_bp.route('/api/internal/debug/tasks')
@require_internal_key
def internal_debug_tasks():
    tasks = BackgroundTask.query.order_by(BackgroundTask.created_at.desc()).limit(50).all()
    return jsonify({'tasks': [t.to_dict() for t in tasks]})

@api_internal_bp.route('/api/internal/debug/tasks/<int:task_id>')
@require_internal_key
def internal_debug_task(task_id):
    task = BackgroundTask.query.get_or_404(task_id)
    return jsonify({'task': task.to_dict()})
```

## App Factory (`apps/api/app.py`)

```python
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
cache = Cache()
csrf = CSRFProtect()

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY',
                'DB_ENGINE', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USERNAME', 'DB_PASS',
                'NFC_PWD_SECRET', 'XENDIT_API_KEY', 'XENDIT_WEBHOOK_TOKEN',
                'CACHE_TYPE', 'PYTHON_GIL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__)
    app.config.from_object('apps.config.ProductionConfig')

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 30,
        'max_overflow': 30,
        'pool_recycle': 3600,
    }

    db.init_app(app)
    cache.init_app(app, config={'CACHE_TYPE': os.environ['CACHE_TYPE']})

    # External API blueprints — CSRF exempt for MeterReadingApp POSTs
    from apps.api.routes import api_blueprint
    from apps.api.customer import api_blueprint as customer_bp
    from apps.api.readings import api_blueprint as readings_bp
    from apps.api.nfc import api_blueprint as nfc_bp

    csrf.exempt(api_blueprint)
    csrf.exempt(customer_bp)
    csrf.exempt(readings_bp)
    csrf.exempt(nfc_bp)

    app.register_blueprint(api_blueprint)
    app.register_blueprint(customer_bp)
    app.register_blueprint(readings_bp)
    app.register_blueprint(nfc_bp)

    # Internal API blueprint (for customer-portal, staff-portal, debug)
    from apps.api.internal import api_internal_bp
    app.register_blueprint(api_internal_bp)

    # Xendit webhook handler (moved from billing blueprint)
    from apps.api.webhooks import xendit_webhook_bp
    csrf.exempt(xendit_webhook_bp)
    app.register_blueprint(xendit_webhook_bp)

    # Database initialization — ensure tables exist
    with app.app_context():
        db.create_all()

    # No Flask-Login. No landing/billing/staff blueprints.

    @app.route('/health')
    def health():
        """Health check that verifies DB connectivity."""
        try:
            db.session.execute(db.text('SELECT 1'))
            return {'status': 'ok', 'db': 'connected'}
        except Exception as e:
            return {'status': 'degraded', 'db': str(e)}, 503

    return app
```

## Dependencies

| Dependency | Source |
|-----------|--------|
| ALL `apps/models.py` | From `billserver-base` |
| ALL `apps/services/` | From `billserver-base` |
| `apps/pricing.py` | From `billserver-base` |
| `apps/config.py` | From `billserver-base` |
| MySQL | Via `net-data` |
| Called by `nginx-gateway` | net-api-ext (webhook, reading/*, key/*) |
| Called by `customer-portal` | net-api-cust |
| Called by `staff-portal` | net-api-staff |
| Called by `debug` | net-api-debug |

## Environment Variables

All required at startup — container fails immediately if any are missing:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session/cookie signing (must match all containers) |
| `INTERNAL_API_KEY` | Shared secret for `/api/internal/*` authentication |
| `DB_ENGINE` | MySQL driver (e.g. `mysql+pymysql`) |
| `DB_HOST` | MySQL hostname |
| `DB_PORT` | MySQL port |
| `DB_NAME` | Database name |
| `DB_USERNAME` | Database user |
| `DB_PASS` | Database password |
| `NFC_PWD_SECRET` | NFC password derivation |
| `XENDIT_API_KEY` | Xendit API key |
| `XENDIT_WEBHOOK_TOKEN` | Xendit webhook verification token |
| `CACHE_TYPE` | Flask-Cache backend (e.g. `SimpleCache`) |
| `PYTHON_GIL` | Free-threading mode (`0`) |
| `DEPLOYMENT_TYPE` | Must be set in .env |

## Dockerfile

```dockerfile
FROM billserver-base:latest

COPY BillServer/apps/api/ /app/apps/api/
COPY BillServer/apps/api/app.py /app/apps/api/app.py

EXPOSE 8008

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8008", \
     "--worker-class", "gthread", \
     "--workers", "4", \
     "--threads", "8", \
     "--access-logfile", "-", \
     "apps.api.app:create_app"]
```

## Docker Compose Service

```yaml
api:
  build:
    context: .
    dockerfile: Dockerfile.api
  container_name: waterbillingsystem_api
  restart: unless-stopped
  networks:
    - net-api-ext      # External API (webhook, reading, key) from nginx
    - net-api-cust     # Customer portal internal API calls
    - net-api-staff    # Staff portal internal API calls
    - net-api-debug    # Debug internal API calls
    - net-data         # MySQL database access
  volumes:
    - db_backups:/app/db_backups
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    DB_ENGINE: ${DB_ENGINE}
    DB_HOST: ${DB_HOST}
    DB_PORT: ${DB_PORT}
    DB_NAME: ${DB_NAME}
    DB_USERNAME: ${DB_USERNAME}
    DB_PASS: ${DB_PASS}
    SECRET_KEY: ${SECRET_KEY}
    INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    NFC_PWD_SECRET: ${NFC_PWD_SECRET}
    XENDIT_API_KEY: ${XENDIT_API_KEY}
    XENDIT_WEBHOOK_TOKEN: ${XENDIT_WEBHOOK_TOKEN}
    CACHE_TYPE: ${CACHE_TYPE}
    PYTHON_GIL: ${PYTHON_GIL}
  depends_on:
    mysql-db:
      condition: service_healthy
  deploy:
    replicas: 2
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8008/api/health')"]
    interval: 10s
    timeout: 5s
    retries: 3
```

## Networks

The API is on all per-consumer API networks plus the data network:

| Network | Purpose |
|---------|---------|
| `net-api-ext` | External API & MeterReadingApp API through nginx |
| `net-api-cust` | Customer portal internal calls |
| `net-api-staff` | Staff portal internal calls |
| `net-api-debug` | Debug internal calls |
| `net-data` | MySQL database connection |

**Each API consumer has its own dedicated network.** This ensures no two consumers can reach each other's API endpoints.

**Not on `net-landing`, `net-customer`, `net-staff`, or `net-debug`.** The API is only reachable through nginx (which bridges those networks) or directly from consumer containers via their dedicated `net-api-*` networks.

## Internal API Security

Internal endpoints (`/api/internal/*`) require the `X-Internal-Key` header:
- All consumer containers (`customer-portal`, `staff-portal`, `debug`) must present this key via their respective `net-api-*` networks.
- The key is a shared secret defined in `.env`.
- Missing or wrong key = 403 Forbidden.
- `/api/internal/*` is NEVER proxied through nginx.

## Scaling

| Setting | Value | Rationale |
|---------|-------|-----------|
| Gunicorn workers | 4–8 | Highest load container. All DB queries come through here. |
| Threads | 8 | Concurrent I/O (DB queries, Xendit API calls) |
| DB pool per replica | 30 + 30 | Largest pool. Services all containers' data needs. |
| Docker replicas | 2 (start), 4 (scale) | Horizontally scalable. Stateless. |

## Migration Notes

1. External API routes — no changes. MeterReadingApp works identically.
2. Internal API routes — new additions. Implement as a separate Flask blueprint (`apps/api/internal.py`).
3. Xendit webhook handler — moved from `apps/billing/api.py` to `apps/api/webhooks.py`.
4. CSRF exempt on all external API blueprints — MeterReadingApp POSTs must work.
5. All DB models available since base image includes `apps/models.py`.
6. All services available since base image includes `apps/services/`.
7. Ensure `SECRET_KEY` matches across `customer-portal`, `staff-portal`, and `debug` containers.
8. Ensure `INTERNAL_API_KEY` matches across `api`, `customer-portal`, `staff-portal`, and `debug`.
