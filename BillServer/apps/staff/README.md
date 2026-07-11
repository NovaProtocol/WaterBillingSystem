# Staff Portal Blueprint

Authenticated admin interface at `/staff`.

## Pages

| Route | Feature |
|-------|---------|
| `/staff/dashboard` | Central hub |
| `/staff/customers` | Customer list, enrollment, edit |
| `/staff/manage-reading` | Meter reading page, manage/drop/edit |
| `/staff/payments` | Payment collection, cashier tally |
| `/staff/manage-billing` | Billing management |
| `/staff/staff` | Staff list, create, edit |
| `/staff/api` | API key generation/revocation |
| `/staff/debug/*` | Debug tools (backup, restore, seed, clear, monthly actions) — superuser only, `DEBUG=true` |

## Background Worker

Debug actions run in a **dedicated subprocess** (`background_worker.py`, launched from `run.py`) to keep the page responsive. Tasks are processed sequentially through the `background_tasks` database table:

## Permissions

7 granular permissions control access: can_read_meters, can_accept_payment, can_enroll_customer, can_drop_reading, can_drop_payment, can_enroll_staff, can_manage_billing.
