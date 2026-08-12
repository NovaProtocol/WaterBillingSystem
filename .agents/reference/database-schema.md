# Database Schema

**11 models** in `shared/models.py`. MySQL 8.4 via PyMySQL. Flask-SQLAlchemy.

## Staff (`staff`)

Inherits `UserMixin` for Flask-Login. `staff_loader` callback registered in models.py.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `username` | String(64) | unique, not null |
| `name` | String(128) | not null, default "" |
| `password` | LargeBinary | Werkzeug PBKDF2:sha256 or legacy PBKDF2-SHA512 |
| `email` | String(128) | nullable |
| `contact_number` | String(32) | nullable |
| `can_read_meters` | Boolean | default False |
| `can_accept_payment` | Boolean | default False |
| `can_enroll_customer` | Boolean | default False |
| `can_drop_reading` | Boolean | default False |
| `can_drop_payment` | Boolean | default False |
| `can_enroll_staff` | Boolean | default False |
| `can_manage_billing` | Boolean | default False |
| `is_active` | Boolean | default True |
| `date_created` | DateTime | |
| `last_modified` | DateTime | onupdate |

## Customer (`customers`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `customer_number` | Integer | unique, indexed |
| `name` | String(128) | nullable |
| `address` | Text | nullable |
| `contact_number` | String(32) | nullable |
| `email` | String(128) | nullable |
| `x_coordinate` | Float | nullable (map) |
| `y_coordinate` | Float | nullable (map) |
| `phase` | String(64) | nullable |
| `block` | String(64) | nullable |
| `street` | String(128) | nullable |
| `meter_serial_number` | String(64) | nullable, indexed |
| `cumulative_balance` | Numeric(10,2) | carryover credit |
| `max_meter_value` | Numeric(10,2) | default 99999.00 |
| `total_due` | Numeric(10,2) | default 0.00, auto-recalculated on payment/reading changes |
| `is_active` | Boolean | default True |
| `deleted_at` | DateTime | nullable (soft delete) |
| `date_created` | DateTime | |
| `date_modified` | DateTime | onupdate |

## MeterReading (`meter_readings`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `customer_number` | Integer | FK -> customers, indexed |
| `reading_value` | Numeric(10,2) | |
| `token_id` | Integer | FK -> api_keys, indexed, not null |
| `timestamp` | DateTime | indexed, not null |
| `date_created` | DateTime | |
| `date_modified` | DateTime | |

Relationships: `customer` -> Customer, `token` -> ApiKey

## Billing (`billings`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `customer_number` | Integer | FK -> customers, indexed |
| `reading_id` | Integer | FK -> meter_readings, nullable |
| `previous_reading_value` | Numeric(10,2) | nullable |
| `current_reading_value` | Numeric(10,2) | nullable |
| `consumption` | Numeric(10,2) | nullable |
| `billed_amount` | Numeric(10,2) | frozen at reading time |
| `penalty` | Numeric(10,2) | PHP 15 after 7 days |
| `paid_amount` | Numeric(10,2) | |
| `carryover_offset` | Numeric(10,2) | over/under payment |
| `is_paid` | Boolean | default False |
| `receipt_number` | String(64) | nullable |
| `cashier_id` | Integer | FK -> staff, nullable, indexed |
| `payment_timestamp` | DateTime | nullable |
| `date_paid` | DateTime | nullable |
| `date_created` | DateTime | |
| `date_modified` | DateTime | |

Relationships: `customer` -> Customer, `reading` -> MeterReading, `cashier` -> Staff

## ApiKey (`api_keys`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `key` | String(128) | unique |
| `label` | String(128) | nullable |
| `staff_id` | Integer | FK -> staff |
| `is_active` | Boolean | default True |
| `date_created` | DateTime | |
| `last_modified` | DateTime | |

Relationship: `staff` -> Staff. Format: `CRDC-` + 32 hex chars.

## NfcTag (`nfc_tags`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `uid` | String(64) | unique, tag identifier |
| `customer_number` | Integer | FK -> customers, indexed |
| `enrolled_by_id` | Integer | FK -> staff |
| `date_created` | DateTime | |
| `last_modified` | DateTime | |

Relationships: `customer` -> Customer, `enrolled_by` -> Staff. UIDs stored without colons, uppercase hex.

## ManagementLog (`management_logs`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `staff_id` | Integer | FK -> staff |
| `action_type` | String(64) | ActionType enum |
| `target_type` | String(64) | "reading" or "billing" |
| `target_id` | Integer | |
| `customer_number` | Integer | nullable, FK -> customers, indexed |
| `details` | Text | free-text description |
| `timestamp` | DateTime | indexed |
| `date_created` | DateTime | |
| `date_modified` | DateTime | |

ActionType enum: `DUPLICATE`, `DROP_PAYMENT`, `EDIT_PAYMENT`, `DROP_READING`, `EDIT_READING`. Primary writer: `log_action()` in `audit_service.py`.

## Config (`app_config`)

Key-value store:

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `key` | String(128) | unique |
| `value` | Text | nullable |
| `date_created` | DateTime | |
| `date_modified` | DateTime | |

Used for `nfc_generation` (NFC secret rotation counter).

## PaymentMethod (`payment_methods`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `code` | String(64) | unique, indexed (e.g. "gcash_ewallet") |
| `label` | String(128) | display name |
| `provider` | String(32) | nullable, "xendit" |
| `channel_code` | String(64) | nullable (Xendit channel code) |
| `fee_percent` | Numeric(5,2) | nullable |
| `fee_flat` | Numeric(10,2) | nullable |
| `fee_minimum` | Numeric(10,2) | nullable |
| `xendit_fee` | Numeric(10,2) | nullable |
| `is_active` | Boolean | default True |
| `sort_order` | Integer | default 0 |
| `date_created` | DateTime | |

Method `fee_for(amount)` computes total fee from percent + flat + minimum logic. 22 payment methods seeded via `fee_service.seed_payment_methods()`.

## XenditTransaction (`xendit_transactions`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `customer_number` | Integer | FK -> customers, indexed |
| `xendit_pr_id` | String(128) | unique, indexed (payment session ID) |
| `external_id` | String(256) | unique |
| `amount` | Numeric(10,2) | total charged |
| `base_amount` | Numeric(10,2) | nullable (before fees) |
| `fee_amount` | Numeric(10,2) | nullable |
| `fee_rate` | Numeric(5,2) | nullable |
| `payment_method` | String(32) | "gcash_ewallet", etc. |
| `status` | String(32) | default "PENDING" |
| `receipt_number` | String(64) | nullable |
| `billing_receipt` | String(64) | nullable |
| `error_message` | Text | nullable |
| `reversed_at` | DateTime | nullable |
| `xendit_payment_id` | String(128) | nullable |
| `date_created` | DateTime | |
| `date_modified` | DateTime | |

## BackgroundTask (`background_tasks`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `task_type` | String(64) | indexed |
| `params` | JSON | nullable |
| `status` | String(16) | queued/running/completed/failed, indexed |
| `progress` | Float | 0-100 |
| `messages` | JSON | progress log |
| `result` | JSON | nullable |
| `title` | String(256) | nullable |
| `scheduled_at` | DateTime | nullable (future scheduling) |
| `started_at` | DateTime | nullable |
| `finished_at` | DateTime | nullable |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

Class methods:
- `enqueue(task_type, params, title, scheduled_at)` — creates queued task
- `enqueue_unique(task_type, ...)` — creates only if no queued/running task of same type exists
