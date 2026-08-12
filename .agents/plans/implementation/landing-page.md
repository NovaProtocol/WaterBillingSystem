# landing-page — Implementation Plan

## Purpose

Public-facing company landing page and house model offering listings. Entirely static — no database, no API calls, no user data. The simplest container in the system.

**Critical constraint**: This container MUST NOT be able to reach the API container or the database. It is on `net-landing` ONLY.

## Current Code Mapping

| Current | New | Changes |
|---------|-----|---------|
| `apps/landing/routes.py` | Identical | No changes |
| `apps/landing/templates/` | Identical | No changes |
| `static/assets/` | Copied into this container | Only the assets landing needs |

## Routes

| Method | Path | Template |
|--------|------|----------|
| GET | `/` | `landing/index.html` |
| GET | `/offerings` | `landing/offerings.html` |
| GET | `/offerings/<slug>` | `landing/model_detail.html` |

The landing page links to `/customer/check` for billing access — this URL is handled by nginx routing to the `customer-portal` container.

## App Factory (`apps/landing/app.py`)

```python
from flask import Flask

def create_app():
    app = Flask(__name__)
    # No SECRET_KEY needed — no sessions
    # No SQLAlchemy — no DB
    # No Flask-Login — no auth
    # No CSRF — no forms
    # No ProxyFix — no sessions to protect

    from apps.landing.routes import landing_blueprint
    app.register_blueprint(landing_blueprint)

    # Template filters
    from apps.landing.routes import timestamp_to_date, datetimeformat
    app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date
    app.jinja_env.filters['datetimeformat'] = datetimeformat

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
```

## Key Property: Zero Backend Access

```python
# These would all FAIL at the network level:
# requests.get('http://api:8008/api/health')      # Not on any net-api-* network
# requests.get('http://mysql-db:3306')              # Not on net-data
# import sqlalchemy; sqlalchemy.create_engine(...)  # No DB credentials in env
```

Even if an attacker gains RCE in this container, they cannot:
- Query customer data (no API access)
- Access billing records (no API access)
- Connect to MySQL (not on net-data, no credentials)
- Reach the staff portal (not on net-staff)

## Dependencies

| Dependency | Source |
|-----------|--------|
| Flask, Jinja2 | From `billserver-base` |
| Static assets | Copied during build |
| API container | **BLOCKED** — not on any net-api-* network |
| MySQL | **BLOCKED** — not on net-data |

## Environment Variables

| Variable | Value |
|----------|-------|
| `DEPLOYMENT_TYPE` | Must be set in .env |

No `SECRET_KEY`. No `DB_*`. No `API_BASE_URL`. No `XENDIT_*`.

## Dockerfile

```dockerfile
FROM billserver-base:latest

COPY BillServer/apps/landing/ /app/apps/landing/
COPY BillServer/static/ /app/static/

EXPOSE 8001

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8001", \
     "--worker-class", "gthread", \
     "--workers", "1", \
     "--threads", "2", \
     "--access-logfile", "-", \
     "apps.landing.app:create_app"]
```

## Docker Compose Service

```yaml
landing-page:
  build:
    context: .
    dockerfile: Dockerfile.landing
  container_name: waterbillingsystem_landing
  restart: unless-stopped
  networks:
    - net-landing
    # NOT on any net-api-* network — cannot reach API
    # NOT on net-data — cannot reach DB
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
    interval: 15s
    timeout: 5s
    retries: 3
```

## Nginx Routing (Public Block Only)

```nginx
location / {
    limit_req zone=landing burst=20 nodelay;
    proxy_pass http://landing:8001;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /static/ {
    proxy_pass http://landing:8001;
}
```

## Security Considerations

1. **Single network isolation.** Only on `net-landing`. No path to API or DB.
2. **No credentials.** No DB password, no API keys, no SECRET_KEY.
3. **No forms.** No POST endpoints. No user input processing.
4. **Only GET routes.** Three routes total. Minimal attack surface.
5. **Template rendering only.** Jinja2 auto-escaping prevents XSS.

## Scaling

| Setting | Value |
|---------|-------|
| Gunicorn workers | 1 |
| Threads | 2 |
| Docker replicas | 1 (scale horizontally if needed) |

## Migration Notes

1. `apps/landing/routes.py` — No changes.
2. `apps/landing/templates/` — No changes. Links to `/customer/check` resolve via nginx.
3. Remove `landing_blueprint` from old `apps/__init__.py`.
4. This container has the fewest environment variables of any container.
