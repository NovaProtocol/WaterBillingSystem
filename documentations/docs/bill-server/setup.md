# Setup & Configuration

## Quick Start

1. Start MySQL: `cd /path/to/Docker && docker compose -f MySQL-compose.yml up -d`
2. Create `.env` at the project root directory (one level above `BillServer/`) with required variables.
3. Set up the Python environment:

```bash
cd BillServer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Start the server:

```bash
# Debug mode (Flask dev server)
python run.py --deployment_type DEBUG

# Production mode (embedded gunicorn)
python run.py --deployment_type PRODUCTION
```

The server starts on **`http://localhost:5005`**.

## Environment Variables

Configuration is loaded from `.env` at the **project root** (parent of `BillServer/`) and read by `python-dotenv` in `run.py:13-14`. All variables are consumed by `apps/config.py`.

### Required (no defaults — must be set)

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session signing key. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `NFC_PWD_SECRET` | Secret for deriving NFC tag passwords. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DB_ENGINE` | Database driver. Typically `mysql+pymysql` |
| `DB_NAME` | Database name (e.g., `BillServerDB`) |
| `DB_HOST` | Database hostname (Docker: `db`, local: `localhost`) |
| `DB_PORT` | Database port (default `3306`) |
| `DB_USERNAME` | Database user (e.g., `root`) |
| `DB_PASS` | Database password |

### Optional

| Variable | Default | Options | Description |
|---|---|---|---|
| `DEPLOYMENT_TYPE` | `PRODUCTION` | `DEBUG` / `PRODUCTION` | Run mode. `DEBUG` enables Flask debug mode and dev server; `PRODUCTION` uses embedded gunicorn with `ProductionConfig` |
| `REVERSE_PROXY_PREFIX` | `""` (root) | Any path like `/water-billing-system`, or `True` | URL prefix when behind a reverse proxy. Path mode: app auto-prefixes all URLs. Boolean mode (`True`): requires nginx to send `X-Forwarded-Prefix` header |
| `SESSION_COOKIE_SECURE` | `true` | `true` / `false` | Whether to mark session cookies as Secure (HTTPS only). Set to `false` for local HTTP-only deployments |
| `SSL_CERTFILE` | (none) | Path to PEM file | SSL certificate path for development HTTPS |
| `SSL_KEYFILE` | (none) | Path to PEM file | SSL private key path for development HTTPS |
| `DEBUG` | `false` | `true` / `false` | Enable superuser-only DEBUG dashboard in the staff portal sidebar |
| `XENDIT_API_KEY` | (none) | string | Xendit secret API key for payment processing |
| `XENDIT_WEBHOOK_TOKEN` | (none) | string | Xendit webhook verification token for callback authentication |

Also `RUN_SELENIUM_TESTS` — set to run Selenium browser tests (skipped by default).

## App Factory

The application is created by `apps/__init__.py:create_app(config)`. During initialization:

1. Config class is selected (`DebugConfig` or `ProductionConfig`)
2. Config is validated (SECRET_KEY, NFC_PWD_SECRET, SQLALCHEMY_DATABASE_URI must be non-null)
3. SQLAlchemy (`db`) is initialized
4. Flask-Login is initialized with the `Staff` model as user loader
5. Flask-Caching is initialized (SimpleCache for dev, FileSystemCache for prod)
6. CSRFProtect is initialized; API blueprint is exempted from CSRF
7. All blueprints are registered (authentication, staff, landing, billing, api)
8. Error handlers are registered for 403, 404, 500
9. `PrefixMiddleware` or `ProxyFix` is applied based on `REVERSE_PROXY_PREFIX`
10. Template filters (`timestamp_to_date`, `datetimeformat`) are registered
11. Before-request handler adds `X-Request-Id` to `g`
12. A "xendit" system user is auto-created at startup (if not present) with `can_accept_payment` permission for automated Xendit payment processing
13. APScheduler starts in the background to reconcile pending Xendit transactions every 5 minutes

## Database Migrations

```bash
# Create a new migration
flask db migrate -m "description of changes"

# Apply pending migrations
flask db upgrade

# Rollback one migration
flask db downgrade

# View migration history
flask db history
```

Migrations are stored in `migrations/versions/`. The startup pre-flight (`run.py`) runs `db.create_all()` automatically, but schema changes via Alembic still require `flask db upgrade`.

## Running in Production

### Gunicorn (via `run.py`)

In `PRODUCTION` mode, `run.py` embeds gunicorn directly via `StandaloneApplication`:

```python
bind = "0.0.0.0:5005"
workers = 3
accesslog = "-"
loglevel = "info"
```

SSL can be enabled by setting `SSL_CERTFILE` and `SSL_KEYFILE` env vars.

### Docker

The Dockerfile at the project root:
1. Multi-stage build from `python:3.14-slim`
2. Compiles bytecode for faster startup
3. Runs `gunicorn --bind 0.0.0.0:5005 --workers 3 wsgi:app`

The `wsgi.py` entry point sets `DEPLOYMENT_TYPE=PRODUCTION`, compiles SCSS, and runs pre-flight checks (DB connectivity, table verification, superuser seeding).

Docker Compose is at `Docker/docker-compose.yml` and runs:
- MySQL 8.4 (`waterbillingsystem_db` container)
- BillServer (app container on port 7000)
- phpMyAdmin (on port 7002)
- Docs server (mkdocs on port 7001)

The compose.yaml passes `XENDIT_API_KEY`, `XENDIT_WEBHOOK_TOKEN`, and `SESSION_COOKIE_SECURE` from `.env` to the BillServer container. See [Deployment](deployment.md) for the full compose.yaml listing.

## Testing

```bash
# Lint only (ruff)
./run_tests.sh lint

# Server-side tests (pytest)
./run_tests.sh server

# Full suite (lint + server + browser tests)
./run_tests.sh all

# Direct pytest
pytest -v
```

The test suite uses an in-memory SQLite database. Fixtures in `tests/conftest.py` provide:
- Authenticated Flask test client
- Staff users with various permission profiles
- Sample customers, readings, billing records, and API keys

## Seeding Test Data

```bash
python seed_test_data.py --customers 20 --months 24
```

Generates realistic data: 20 customers with coordinates, phases/blocks/streets, 24 months of readings, and randomized payment patterns. Requires a running MySQL instance.

---

## Development

### DEBUG Menu

When `DEBUG=true` is set in `.env` and the logged-in user is `superuser`, a **DEBUG** section appears in the staff portal sidebar with the following tools:

| Tool | Description |
|---|---|
| **Backup Database** | Exports all tables to a JSON file stored in the `db_backups` Docker volume |
| **Restore from Backup** | Lists available backups and restores from one (destructive — replaces all data) |
| **Seed Test Data** | Generates realistic test data with configurable customer count (1–10000) and months (1–240). Clears existing data first. |
| **Clear Database** | Truncates all tables (irreversible) |

All destructive actions (restore, seed, clear) require a confirmation flow: a random 8-digit number is displayed and must be typed exactly before execution.

The `db_backups` volume is declared in `compose.yaml` and mounted at `/app/db_backups` in the BillServer container.

The `DEBUG` variable is read via `os.environ.get("DEBUG")` in `apps/__init__.py` and exposed to templates as `config.DEBUG_ENABLED`.
