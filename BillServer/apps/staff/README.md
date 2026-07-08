# Staff Portal Blueprint

Authenticated admin interface at `/staff`.

## Pages

| Route | Feature |
|-------|---------|
| `/staff/dashboard` | Central hub |
| `/staff/customers` | Customer list, enrollment, edit |
| `/staff/readings` | Meter reading page, manage/drop/edit |
| `/staff/payments` | Payment collection, cashier tally |
| `/staff/bills` | Billing management |
| `/staff/staff` | Staff list, create, edit |
| `/staff/api` | API key generation/revocation |
| `/staff/debug/*` | Debug tools (backup, restore, seed, clear, monthly actions) — superuser only, `DEBUG=true` |

## Background Worker

Debug actions run in a **dedicated subprocess** (`debug_worker.py`, launched from `run.py`) to keep the page responsive. Tasks are processed sequentially through a file-based queue:

- `db_backups/to_bg.json` — queue of pending job orders (written by Flask routes, popped by worker)
- `db_backups/from_bg.json` — current job state + completed history (written by worker, read by routes)

All file access uses `fcntl.flock` for cross-process safety across Gunicorn workers. On server restart, both files are cleared.

## Permissions

7 granular permissions control access: can_read_meters, can_accept_payment, can_enroll_customer, can_drop_reading, can_drop_payment, can_enroll_staff, can_manage_billing.
