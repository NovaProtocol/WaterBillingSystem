# BillServer -- Cotta Realty Water Billing Management System

A **water billing management system** built on **Python Flask 3.1 + SQLAlchemy 2.0 + MySQL**. Manages customer enrollment, meter reading ingestion (manual + API sync), water bill computation, payment processing, cashier tallies, and staff administration.

**Brand**: Cotta Realty & Development Corporation
**License**: MIT

---

## Quick Start

```bash
# 1. Prerequisites: Python 3.10+, MySQL running on localhost:3306
# 2. Create database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS BillServerDB"

# 3. Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Configure environment
# Edit .env with your DB credentials

# 5. Apply migration
flask db upgrade

# 6. Launch
./launch.sh            # default port 5005
# or: python run.py    # binds 0.0.0.0:5005
```

After first launch, a superuser account is auto-created: **username: superuser / password: superuser**

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Flask 3.1.3, Werkzeug 3.1.8, Jinja2 3.1.6 |
| ORM | SQLAlchemy 2.0.51 + Flask-SQLAlchemy 3.1.1 |
| Migrations | Alembic via Flask-Migrate 4.1.0 |
| Database | MySQL 8+ (production), SQLite (testing) |
| Auth | Flask-Login 0.6.3 + Werkzeug PBKDF2 hashing |
| Forms | WTForms 3.2.2 + Flask-WTF 1.3.0 |
| Frontend | Bootstrap 4.6, jQuery, Leaflet.js maps, Font Awesome 6 |
| CSS Build | libsass + rcssmin (compiled at startup) |
| Deployment | Gunicorn 26 |
| CI/CD | GitHub Actions (`.github/workflows/ci.yml`) |

---

## Features

### Staff Portal (`/staff`)
- Dashboard -- central hub for authorized staff
- Meter Reading -- generate/revoke API keys for external meter readers
- Payments -- AJAX customer lookup, payment submission with auto-linking
- Customer Management -- enroll new customers with map coordinates
- Staff Management -- create staff accounts with granular permissions
- Cashier Tally -- daily payment aggregation per cashier
- Management -- drop/edit payments and readings with audit logging

### Customer Portal (`/billing/<customer_number>`)
- Public-facing billing page (cookie verification required)
- Current consumption and water bill breakdown by tier
- 7-day payment due date with late penalty calculation ($15.00)
- Paginated reading history and payment history
- Interactive Leaflet map showing customer location
- Running cumulative balance tracking

### Landing Page (`/`)
- Public entry point with hero section
- Customer lookup by number + last receipt verification

### REST API (`/api`)
See [API.md](API.md) for full reference.

---

## Database Schema (9 Tables)

| Table | Purpose |
|-------|---------|
| `staff` | Staff accounts with 7 permission booleans |
| `customers` | Water service customers with cumulative balance |
| `meter_readings` | Monthly water meter readings |
| `billings` | Payment records with receipt numbers |
| `nfc_tags` | NFC tag to customer mappings |
| `api_keys` | API keys for external meter readers |
| `management_logs` | Audit trail for drops/edits |
| `app_config` | Key-value application configuration |
| `xendit_transactions` | Online payment lifecycle tracking |

---

## Xendit Online Payment Integration

BillServer integrates **Xendit** for online payments via GCash, Maya, and credit/debit cards.

| Feature | Detail |
|---------|--------|
| Webhook endpoint | `/billing/api/xendit-webhook` |
| DB model | `XenditTransaction` tracks payment lifecycle (pending, completed, failed, expired) |
| System user | A "xendit" staff user is auto-created at startup for automated payment processing |
| Background reconciliation | APScheduler reconciles pending transactions every 5 minutes |
| Env vars required | `XENDIT_API_KEY`, `XENDIT_WEBHOOK_TOKEN` |

---

## Staff Permissions

| Permission | Grants access to |
|-----------|-----------------|
| `can_read_meters` | Meter reading page, API key management |
| `can_accept_payment` | Payment submission |
| `can_enroll_customer` | Customer list and enrollment |
| `can_drop_reading` | Dropping meter readings |
| `can_drop_payment` | Dropping payment records |
| `can_enroll_staff` | Staff list and creation |
| `can_manage_billing` | Editing payments/readings, all cashier tallies |

---

## Pricing Tiers

| Range (m\u00b3) | Rate | Type |
|-----------|------|------|
| 0 - 10 | $150.00 flat | Flat fee |
| 11 - 20 | $25.00 / m\u00b3 | Per unit |
| 21 - 30 | $30.00 / m\u00b3 | Per unit |
| 31 - 40 | $35.00 / m\u00b3 | Per unit |
| 41+ | $40.00 / m\u00b3 | Per unit |

Late payment penalty: **$15.00** (assessed 7 days after reading date)

---

## Testing

```bash
# Server-side tests (fast, no browser needed)
./run_tests.sh server

# Full suite including browser tests
./run_tests.sh all

# Browser tests only (requires Playwright)
./run_tests.sh browser
```

Tests use an in-memory SQLite database -- no MySQL required.

---

## Deployment

```bash
# Development
./launch.sh

# Production
./launch.sh PRODUCTION
# Or:
gunicorn --config gunicorn-cfg.py run:app
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_SECRET_KEY` | Yes | — | Flask session signing key |
| `MYSQL_USER` | Yes | `root` | MySQL username |
| `MYSQL_PASSWORD` | Yes | — | MySQL password |
| `MYSQL_HOST` | No | `localhost` | MySQL host |
| `MYSQL_PORT` | No | `3306` | MySQL port |
| `MYSQL_DB` | No | `BillServerDB` | Database name |
| `XENDIT_API_KEY` | For online payments | — | Xendit secret API key |
| `XENDIT_WEBHOOK_TOKEN` | For online payments | — | Xendit webhook verification token |
| `SESSION_COOKIE_SECURE` | No | `False` | Set to `True` in production for HTTPS-only session cookies |

---

## Project Structure

```
BillServer/
  run.py                    # Entry point + pre-flight checks
  apps/
    __init__.py             # Flask app factory, blueprints, error handlers
    config.py               # Config classes (Debug/Production)
    pricing.py              # Shared pricing logic (centralized)
    models.py               # All SQLAlchemy models
    api/                    # REST API blueprint (/api)
    authentication/         # Auth blueprint
    billing/                # Customer billing blueprint (/billing)
    landing/                # Public landing page blueprint (/)
    staff/                  # Staff portal blueprint (/staff)

  migrations/               # Alembic migrations
  tests/                    # Pytest test suite
  static/                   # Compiled CSS, JS, vendor assets
  db_backups/               # JSON dumps
  seed_test_data.py         # Standalone MySQL seeder
  requirements.txt          # Python dependencies
  package.json              # Frontend build tools
```
