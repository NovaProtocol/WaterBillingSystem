# Setup & Configuration

## Quick Start

```bash
cd BillServer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask db upgrade
python run.py
```

The server starts on **`http://localhost:5005`**.

## Environment Variables

Configuration is loaded from `.env` (in the project root) and `apps/config.py`:

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `True` | Enable Flask debug mode |
| `FLASK_APP` | `run.py` | Flask entry point |
| `FLASK_DEBUG` | `1` | Debug mode flag |
| `DB_ENGINE` | `mysql+pymysql` | Database driver |
| `DB_NAME` | `BillServerDB` | Database name |
| `DB_HOST` | `localhost` | Database hostname |
| `DB_PORT` | `3306` | Database port |
| `DB_USERNAME` | `root` | Database user |
| `DB_PASS` | `BillServerDB` | Database password |
| `SECRET_KEY` | (random) | Flask session signing key |
| `NFC_PWD_SECRET` | (random) | Secret for deriving NFC tag passwords |

## App Factory

The application is created by `apps/__init__.py:create_app(config)`. During initialization:

1. Config class is selected (`DebugConfig` or `ProductionConfig`)
2. SQLAlchemy (`db`) is initialized with the DB URI
3. Flask-Migrate is initialized for schema migrations
4. Flask-Login is initialized with the `Staff` model as user loader
5. Flask-Caching is initialized for pricing tier caching (1-hour TTL)
6. All blueprints are registered (API, Staff, Landing, Billing, Authentication, Template)
7. Context processors add `current_year`, `pricing_url`, `app_config` to templates
8. Error handlers are registered for 403, 404, 500, and 503
9. Jinja2 template filters (`zip`, `is_list`, `get_class`) are registered

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

Migrations are stored in `migrations/versions/` and applied automatically when using `launch.sh` or the Dockerfile's `CMD`.

## Running in Production

### Gunicorn

Configured in `gunicorn-cfg.py`:

```python
bind = '0.0.0.0:5005'
workers = multiprocessing.cpu_count() * 2 + 1
accesslog = '-'
loglevel = 'debug'
```

Start manually:

```bash
gunicorn --config gunicorn-cfg.py run:app
```

### Docker

```bash
docker-compose up --build
```

The Dockerfile:
1. Starts from `python:3.10`
2. Installs Python dependencies
3. Runs `flask db upgrade`
4. Starts Gunicorn with the gunicorn-cfg config

The docker-compose.yml also starts an **nginx** reverse proxy on port `5085`.

## Testing

```bash
# Lint only (ruff)
./run_tests.sh lint

# Server-side tests (pytest, safe over SSH)
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
