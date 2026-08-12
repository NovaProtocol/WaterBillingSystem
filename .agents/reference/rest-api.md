# REST API

**Blueprint**: `api/blueprint.py` — `api_blueprint` at `/api`

> **Mobile contract under rework.** The MeterReadingApp calls
> `/api/key/info`, `/api/nfc/*` (`config|sync|tags`), and
> `/api/readings/bulk|sync` — none of these routes exist in `api/routes/*`.
> The mobile sync/auth contract is being reworked; do not implement against
> these endpoints until the new contract lands.

All endpoints under `/api/*`. Three auth methods:
1. **API key**: Bearer header or `?api_key=` query param. Permission flags determine access.
2. **Internal API key**: `X-Internal-API-Key` header (portal-to-API). `require_staff()` returns `True` instead of ApiKey object.
3. **No auth**: `/api/health`, `/api/customer/login`, `/api/webhook/xendit-payment` (X-Callback-Token)

---

## Endpoints

### Health
| | |
|---|---|
| **GET** `/api/health` | Auth: None |
| **Response** | `{"status": "ok", "db": true}` — verifies DB connectivity |

---

### Customer — Info (4)

**GET** `/api/customer/count`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | — |
| Response | `{"count": 42}` |

**GET** `/api/customer/all`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | `page` (int, default 1), `size` (int, default 50, max 200), `q` (str, optional — prefix search: digit-only uses BETWEEN ranges on indexed integer column, name uses LIKE prefix), `sort_by` (str: `customer_number`, `name`, `phase`, `block`, `street`, `total_due`), `sort_dir` (str: `asc`, `desc`) |
| Response | `{data: [{id, customer_number, name, address, meter_serial_number, contact_number, email, phase, block, street, x_coordinate, y_coordinate, cumulative_balance, max_meter_value, total_due, is_active, nfc_uid}], meta: {current_page, page_size, total_items, total_pages}}` |

**GET** `/api/customer/<int:customer_number>`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | `staff_id` (int, optional — filter readings by staff), `token_id` (int, optional — filter readings by API key) |
| Response | Full billing profile: `{customer_number, name, address, meter_serial_number, contact_number, email, phase, block, street, max_meter_value, latest_reading, last_reading, consumption, bill_breakdown, pricing_tiers, water_bill, carryover, cumulative_balance, penalty, total_due, latest_unpaid, unpaid_bills, total_unpaid, total_penalties, due_date, days_remaining, billing_items, recent_payments (last 10), payment_methods}` |

**GET** `/api/customer/<int:customer_number>/details`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | `history` (int, default 5 — number of recent readings to return) |
| Response | `{customer: {customer_number, name, address, meter_serial_number, contact_number, email, phase, block, street, x_coordinate, y_coordinate, cumulative_balance, max_meter_value}, readings: [{id, reading_value, reader, timestamp}]}` |

**REMOVED** — `/api/customer/<int:customer_number>/profile` was an alias for `/<int:customer_number>`. Deleted in favor of the canonical endpoint.

---

### Customer — CRUD (3)

**POST** `/api/customer/new`
| | |
|---|---|
| Auth | `can_enroll_customer` |
| Body | `customer_number` (int, **required**), `name` (str), `address` (str), `contact_number` (str), `email` (str), `phase` (str), `block` (str), `street` (str), `x_coordinate` (float), `y_coordinate` (float), `max_meter_value` (float, default 99999) |
| Response | `{message: "Customer created", customer_number}` (201) or `{error}` (400/409) |

**PUT** `/api/customer/update/<int:customer_number>`
| | |
|---|---|
| Auth | `can_enroll_customer` |
| Body | Same fields as create (partial update — only provided fields changed) |
| Response | `{message: "Customer updated"}` |

**DELETE** `/api/customer/delete/<int:customer_number>`
| | |
|---|---|
| Auth | `can_enroll_customer` |
| Body | — (toggles `is_active` — second call reactivates) |
| Response | `{message: "Customer deactivated/reactivated", is_active}` |

---

### Customer — Login & Invoicing (2)

**POST** `/api/customer/login`
| | |
|---|---|
| Auth | None |
| Body | `account_number` (int, **required**), `registered_name` (str, optional), `last_receipt` (str, optional — not currently validated) |
| Response | `{customer_number, customer: {customer_number, name, address, contact_number, email, meter_serial_number, x_coordinate, y_coordinate}}` |

**POST** `/api/customer/<int:customer_number>/invoice`
| | |
|---|---|
| Auth | None |
| Body | `amount` (float, **required**, > 0), `payment_method` (str, **required** — e.g. `"gcash"`, `"maya"`), `success_url` (str, optional), `cancel_url` (str, optional) |
| Response | `{redirect_url, external_id, id (session_id), base_amount, fee_amount, fee_rate}` — creates Xendit v2 payment session. The `xendit_fee` from the selected PaymentMethod is added to the `total_amount` sent to Xendit. `success_url` and `cancel_url` are forwarded through to the Xendit API. |

---

### Customer — Readings (4)

**GET** `/api/customer/<int:customer_number>/reading`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | `page` (int, default 1), `size` (int, default 50) |
| Response | `{data: [{id, reading_value, reader, timestamp}], meta: {current_page, page_size, total_items, total_pages}}` |

**POST** `/api/customer/<int:customer_number>/reading/new`
| | |
|---|---|
| Auth | `can_read_meters` |
| Body | `reading_value` (float, **required**), `timestamp` (float, Unix epoch — optional, defaults to now), `staff_id` (int — internal key only), `staff_name` (str — internal key only) |
| Response | `{success, reading_id, customer_number, reading_value, timestamp, reader}` (201). Auto-creates Billing record from previous reading. Returns 409 on duplicate-month. |

**POST** `/api/customer/<int:customer_number>/reading/drop`
| | |
|---|---|
| Auth | `can_drop_reading` |
| Body | `reading_id` (int, **required**), `reason` (str, **required**), `staff_id` (int — internal key only) |
| Response | `{message: "Reading dropped"}` (only if current month + unpaid). Returns 409 on validation failure. |

**POST** `/api/customer/<int:customer_number>/reading/edit`
| | |
|---|---|
| Auth | `can_manage_billing` |
| Body | `reading_id` (int, **required**), `reading_value` (float, **required**), `staff_id` (int — internal key only) |
| Response | `{message: "Reading updated"}` — recomputes associated billing |

---

### Customer — Billing (3)

**GET** `/api/customer/<int:customer_number>/billing`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | `page` (int, default 1), `size` (int, default 50) |
| Response | `{data: [{id, reading_id, month, previous_reading, current_reading, consumption, billed_amount, penalty, paid_amount, is_paid, receipt_number, cashier_id, payment_timestamp, date_paid, created_at}], meta}` |

**POST** `/api/customer/<int:customer_number>/billing/new`
| | |
|---|---|
| Auth | `can_accept_payment` |
| Body | `amount` (float, **required**, > 0), `staff_id` (int — internal key only) |
| Response | `{message, receipt_number, paid_bills, carryover_amount, total_applied, ...}` — waterfall payment model |

**POST** `/api/customer/<int:customer_number>/billing/drop`
| | |
|---|---|
| Auth | `can_drop_payment` |
| Body | `billing_id` (int, **required**), `reason` (str, **required**), `staff_id` (int — internal key only) |
| Response | `{message: "Payment dropped"}` — reverts entire receipt group |

---

### Customer — NFC (4)

**GET** `/api/customer/<int:customer_number>/nfc`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | — |
| Response | `{nfc_uid, customer_number}` or `{nfc_uid: null}` |

**GET** `/api/customer/all/nfc`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | — |
| Response | `{tags: [{uid, customer_number}]}` — ordered by date_created desc |

**POST** `/api/customer/<int:customer_number>/nfc/create`
| | |
|---|---|
| Auth | `can_enroll_customer` |
| Body | `uid` (str, **required** — tag UID hex string) |
| Response | `{message: "Tag assigned", uid, customer_number}` (201). Returns 409 if UID already assigned. |

**POST** `/api/customer/<int:customer_number>/nfc/delete`
| | |
|---|---|
| Auth | `can_enroll_customer` |
| Body | — (deletes by customer_number, not by uid) |
| Response | `{message: "Tag deleted", uid}`. Increments `nfc_generation` config key. |

---

### Change Detection (1)

**GET** `/api/customers/changed`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | `since` (int, Unix timestamp, **required**) |
| Response | `{customer_numbers: [...], server_time, total_customers}`. Detects: modified customers, new readings, dropped/edited readings (via ManagementLog). |

---

### Config (2)

**GET** `/api/config/nfc_secret`
| | |
|---|---|
| Auth | API key (can_read_meters OR can_enroll_customer) |
| Params | — |
| Response | `{nfc_pwd_secret, nfc_generation}` |

**GET** `/api/config/pricing`
| | |
|---|---|
| Auth | `can_read_meters` |
| Params | — (cached 3600s) |
| Response | `{tiers, late_penalty, due_days}` |

---

### Staff (12)

**POST** `/api/staff/login`
| | |
|---|---|
| Auth | None |
| Body | `username` (str, **required**), `password` (str, **required**) |
| Response | `{id, username, name, email, contact_number, is_active, can_read_meters, can_accept_payment, can_enroll_customer, can_drop_reading, can_drop_payment, can_enroll_staff, can_manage_billing}`. Supports Werkzeug bcrypt-like hashes and legacy PBKDF2-HMAC-SHA512 fallback. |

**GET** `/api/staff/info`
| | |
|---|---|
| Auth | API key or internal key |
| Params | Header: `X-Staff-ID` (int — required when using internal key) |
| Response | `{staff: {id, username, name, email, contact_number, is_active, ...7 permissions}, auth_type, api_key}` |

**GET** `/api/staff/all`
| | |
|---|---|
| Auth | `can_enroll_staff` |
| Params | — |
| Response | `{staff: [{id, username, name, email, contact_number, is_active, ...7 permissions}]}` |

**GET** `/api/staff/<id>`
| | |
|---|---|
| Auth | `can_enroll_staff` |
| Params | — |
| Response | `{id, username, name, email, contact_number, is_active, ...7 permissions}` |

**POST** `/api/staff/new`
| | |
|---|---|
| Auth | `can_enroll_staff` |
| Body | `username` (str, **required**), `password` (str, **required**), `name` (str), `email` (str), `contact_number` (str), `can_read_meters` (bool), `can_accept_payment` (bool), `can_enroll_customer` (bool), `can_drop_reading` (bool), `can_drop_payment` (bool), `can_enroll_staff` (bool), `can_manage_billing` (bool) |
| Response | `{message: "Staff created", username, name}` (201) |

**POST** `/api/staff/<id>/edit`
| | |
|---|---|
| Auth | `can_enroll_staff` |
| Body | `username` (str, **required**), `password` (str — only set if provided), `name` (str), `email` (str), `contact_number` (str), `can_read_meters` (bool), `can_accept_payment` (bool), `can_enroll_customer` (bool), `can_drop_reading` (bool), `can_drop_payment` (bool), `can_enroll_staff` (bool), `can_manage_billing` (bool), `is_active` (bool) |
| Response | `{message: "Staff updated", username, name}` |

**GET** `/api/staff/<id>/cashier-tally`
| | |
|---|---|
| Auth | `can_accept_payment` |
| Params | `period` (str: `daily`/`weekly`/`monthly`/`yearly`/`custom`, default `daily`), `start_date` (str, YYYY-MM-DD), `end_date` (str, YYYY-MM-DD), `date` (str, YYYY-MM-DD — alias for start_date), `group_days` (int, default 1 — matrix view) |
| Response | `{tally, use_matrix, nav_date, group_days, start_date, end_date, display, prev_date, next_date, is_today, period}` |

**GET** `/api/staff/<id>/reading-logs`
| | |
|---|---|
| Auth | `can_drop_reading` |
| Params | — |
| Response | `{logs: [{id, staff_id, staff_name, action_type, target_id, customer_number, details, timestamp}]}` — last 50 entries |

**GET** `/api/staff/<id>/api-keys`
| | |
|---|---|
| Auth | API key or internal key |
| Params | — |
| Response | `{keys: [{id, key, label, is_active, staff_id, staff_name, staff: {name, username}, date_created}]}` — returns ALL keys, not just staff's own |

**POST** `/api/staff/<id>/api-key/generate`
| | |
|---|---|
| Auth | `can_read_meters` |
| Body | `label` (str, optional) |
| Response | `{key: "CRDC-<32hex>", label, id}` (201) |

**POST** `/api/staff/<id>/api-key/<key_id>/revoke`
| | |
|---|---|
| Auth | `can_read_meters` |
| Body | — |
| Response | `{message: "Key revoked"}` — sets `is_active = False` |

**POST** `/api/staff/<staff_id>/api-key/verify`
| | |
|---|---|
| Auth | API key (from request auth, not from body) |
| Body | `api_key` (str, **required** — key to verify) |
| Response | `{valid, api_key: {id, label, staff_id, is_active}, staff: {id, username, name, ...7 permissions}}` |

---

### Webhooks (1)

**POST** `/api/webhook/xendit-payment`
| | |
|---|---|
| Auth | `X-Callback-Token` header (matched against `XENDIT_WEBHOOK_TOKEN` env var) |
| Blueprint | `xendit_webhook` (separate from api_blueprint, but served under same `/api` prefix) |
| Body | `external_id` (str — format: `wbs-<customer_number>-<timestamp>-<hex>`), `status` (str — `PAID`, `COMPLETED`, `SUCCEEDED`, `FAILED`, etc.) |
| Response | `{received: true}`. On `PAID`/`COMPLETED`/`SUCCEEDED`: auto-submits payment using `tx.base_amount` (not `tx.amount`) to avoid overpayment carryover. Detailed logging of callback data and transaction lookup. |

---

### Debug / Maintenance (13)

Accessible only if `/app/db_backups/` directory exists (checked via `_superuser_only()`). The Docker network configuration restricts access to internal containers.

**GET** `/api/debug/stats`
| | |
|---|---|
| Params | — |
| Response | `{customers, customers_total, readings, billings, unpaid_bills, paid_bills, staff, api_keys, nfc_tags, management_logs, xendit_transactions, payment_methods, background_tasks}` — counts for all tables |

**POST** `/api/debug/backup`
| | |
|---|---|
| Body | — |
| Response | `{ok, order_id, message: "Backup queued."}` |

**GET** `/api/debug/backups`
| | |
|---|---|
| Params | — |
| Response | `{backups: [{name, size, modified}]}` — sorted newest first |

**POST** `/api/debug/restore`
| | |
|---|---|
| Body | `filename` (str, **required** — must be `backup_*.sql` in backup dir) |
| Response | `{ok, order_id, message}` |

**GET** `/api/debug/restore-newest`
| | |
|---|---|
| Params | — (5s cooldown per IP, returns 429 if violated) |
| Response | `{ok, order_id, message}` |

**POST** `/api/debug/clear`
| | |
|---|---|
| Body | — (truncates 7 core tables, preserves superuser + xendit) |
| Response | `{ok, order_id, message}` |

**POST** `/api/debug/seed`
| | |
|---|---|
| Body | `customers` (int, **required**, 1-10000), `months` (int, **required**, 1-240) |
| Response | `{ok, order_id, message}` |

**POST** `/api/debug/read-month`
| | |
|---|---|
| Body | — |
| Response | `{ok, order_id, message}` |

**POST** `/api/debug/unread-month`
| | |
|---|---|
| Body | — |
| Response | `{ok, order_id, message}` |

**POST** `/api/debug/pay-month`
| | |
|---|---|
| Body | — |
| Response | `{ok, order_id, message}` |

**POST** `/api/debug/remove-pay-month`
| | |
|---|---|
| Body | — |
| Response | `{ok, order_id, message}` |

**GET** `/api/debug/tasks`
| | |
|---|---|
| Params | — |
| Response | `{current: {id, task_type, title, status, progress, messages, started_at, finished_at, created_at}, queue_depth, history: [...]}` (last 20 completed/failed) |

**GET** `/api/debug/tasks/<id>`
| | |
|---|---|
| Params | — |
| Response | `{task: {id, task_type, title, status, progress, messages, params, result, started_at, finished_at, created_at}}` |

---

## Request Conventions

- **GET** params are query string (`?key=value`)
- **POST/PUT/DELETE** params are JSON body (`Content-Type: application/json`)
- Dates/timestamps are Unix epoch (seconds) unless noted
- All IDs are integers
- Amounts are floats (PHP)
- Paginated responses use `{data: [...], meta: {current_page, page_size, total_items, total_pages}}`

## Key Implementation Notes

### Reading Creation Flow
`POST /api/customer/<n>/reading/new`:
1. Validates customer exists
2. Checks for duplicate in current calendar month → logs `ManagementLog` with `action_type="duplicate"`, returns 409
3. Creates `MeterReading` record
4. Auto-generates `Billing` record if a previous reading exists
5. Commits both

### Customer Search
`GET /api/customer/all?q=...` performs prefix matching:
- **Digit-only** `q`: uses `BETWEEN` ranges on the indexed integer `customer_number` column (no `CAST` / `LIKE`)
- **Non-digit** `q`: uses `LIKE 'prefix%'` on the `name` column — no suffix wildcard, prefix only
- `list_customers()` in `customer_service.py` handles this logic server-side

### Customer Profile Response (`GET /api/customer/<n>`)
Returns all readings (unlimited), all bills (unlimited), computes unpaid totals, applies penalties, computes carryover, returns last 10 paid payments, payment methods, and pricing tiers. Heavy endpoint — avoid calling frequently. Triggers `recalc_total_due()` and `recalc_cumulative_balance()` on access.

### Cashier Tally
`GET /api/staff/<id>/cashier-tally` supports periods: daily, weekly, monthly, yearly, custom. `group_days=N` for interval matrix view.

### Payment Waterfall Model
`POST /api/customer/<n>/billing/new` applies payment to oldest unpaid bills first. Any remainder becomes carryover on the next bill. Undoing a payment (`billing/drop`) reverses the entire receipt group. Both operations trigger `total_due` recalculation.
