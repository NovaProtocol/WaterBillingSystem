# Data Inventory — What Each Container Needs

This documents every piece of data each container uses, grouped by domain area, not by API endpoint.

---

## 1. Landing Page

No dynamic data. Pure static HTML. No account info, no customer data, no API calls.

---

## 2. Customer Portal

### 2.1 Identity Verification

| Data | Purpose | Source |
|------|---------|--------|
| Account number | Look up the customer | User input |
| Registered name | Verify identity against DB record | User input |
| Last receipt number | Secondary verification (optional via DEBUG) | User input |

### 2.2 Customer Profile (Billing Page Header)

| Data | Example |
|------|---------|
| Customer number | `"001"` |
| Full name | `"Domingo Gonzales"` |
| Address | `"9 St. Peregrine St, Brgy. X"` |
| Contact number | `"09181960013"` |
| Email | `"c1domingo@gmail.com"` |
| Map coordinates | `13.9363, 121.642` |

### 2.3 Meter Readings

**Current reading (most recent):**
| Data | Example |
|------|---------|
| Reading value | `4109.1` |
| Timestamp | `2026-07-11` |
| Reader name | `"Admin"` |

**Previous reading (second most recent):**
| Data | Example |
|------|---------|
| Reading value | `4082.9` |
| Timestamp | `2026-06-11` |
| Reader name | `"Admin"` |

### 2.4 Billing Computation

| Data | Example | How It's Calculated |
|------|---------|---------------------|
| Consumption | `26.20 m³` | latest − previous reading |
| Pricing tiers | 6 tiers from 0-10 up to 41+ | Defined in `pricing.py` |
| Per-tier charges | `[{label: "0-10 m³", units: 10, charge: 150}, ...]` | Tier logic × consumption |
| Total water bill | `₱655.00` | Sum of all tier charges |
| Unpaid bills | `[{month: "July 2026", amount: 655.00, penalty: 15.00, timestamp: ...}]` | DB query filtered unpaid |
| Late penalties | `₱15.00` per overdue billing | Added after 7 days |
| Carryover balance | `₱50.00` | Previous billing surplus/deficit |
| Total due | `₱720.00` | unpaid + penalties − carryover |
| Due date | `"07-22-2026"` | 7 days after oldest unpaid bill |
| Days remaining | `7` | Days until due date |
| Pending Xendit payment | `{status: "PENDING", amount: 720.00}` | Any active Xendit session |
| Payment methods | `[{code: "gcash", label: "GCash", fee: 2%, ...}]` | Active methods from DB |

### 2.5 Recent Activity

**Recent payments (last 10):**
| Data | Example |
|------|---------|
| Receipt number | `"RCP-2026-001"` |
| Amount paid | `₱500.00` |
| Payment timestamp | `2026-07-01 14:30` |

**Recent readings (last 5):**
| Data | Example |
|------|---------|
| Reading value | `4082.9` |
| Timestamp | `2026-06-11` |
| Reader name | `"Admin"` |

### 2.6 Payment History (AJAX)

| Data | Type |
|------|------|
| Per item: receipt number, amount paid, payment timestamp | Same as above, paginated |

### 2.7 Reading History (AJAX)

| Data | Type |
|------|------|
| Per item: reading value, timestamp, reader name | Same as above, paginated |

### 2.8 Invoice Creation

The portal sends to the API:
- Amount to charge
- Selected payment method code

The API returns: Xendit checkout URL (customer gets redirected there)

---

## 3. Staff Portal

### 3.1 Authentication

| Data | Purpose |
|------|---------|
| Username | Staff login |
| Password | Staff login |
| Session data (7 permission flags) | Used throughout for authorization |

### 3.2 Dashboard Summary

| Data | Purpose |
|------|---------|
| Total active customers | Display on dashboard |
| Count of unpaid bills | Display on dashboard |

### 3.3 Customer List

**Per customer (for table display):**
| Data | Example |
|------|---------|
| Customer number | `"001"` |
| Name | `"Domingo Gonzales"` |
| Address | `"9 St. Peregrine St"` |
| Contact number | `"09181960013"` |
| Email | `"c1domingo@gmail.com"` |
| Cumulative balance | `₱150.00` |
| Active status | `true/false` |
| Pagination info | page, per_page, total, pages |

### 3.4 Customer Search (AJAX)

| Data | Query / Result |
|------|----------------|
| Search query | Partial match on number or name |
| Results | List of matching customers (number, name) |

### 3.5 Customer Management (Manage Customers Page)

**Per customer (for edit form + table):**
| Data | Example |
|------|---------|
| All customer list fields (above) | — |
| Phase | `"Phase 1"` |
| Block | `"Block A"` |
| Street | `"St. Peregrine"` |
| Total due (computed) | `₱720.00` |
| Is active | `true/false` |
| NFC tag | Tag UID if assigned |
| Pagination, sorting, search query | For filtered list |

**Create/Edit form fields:**
Customer number, name, address, contact number, email, phase, block, street, x/y coordinates

### 3.6 API Keys (Meter Reading Page)

| Data | Example |
|------|---------|
| Key string | `"CRDC-abc123..."` |
| Label | `"Terminal 1"` |
| Created date | `2026-07-01` |
| Active status | `true/false` |
| Associated staff name | `"Admin"` |

### 3.7 Reading Management (Manage Reading Page)

**Management logs (reading changes):**
| Data | Example |
|------|---------|
| Timestamp | `2026-07-15 10:30` |
| Staff name | `"Juan"` |
| Action type | `"drop"`, `"edit"` |
| Details | `"Dropped reading #123 — reason: meter error"` |

**Staff list (filter dropdown):**
| Data | Example |
|------|---------|
| Staff ID | `1` |
| Name | `"Juan Dela Cruz"` |

**API keys (filter dropdown):**
| Data | Example |
|------|---------|
| Key ID | `1` |
| Key text | `"CRDC-abc..."` |
| Staff name | `"Juan"` |

### 3.8 Payment Submission

| Data | Source |
|------|--------|
| Customer number | Staff lookup/input |
| Amount paid | Staff input |
| Cashier ID | From session |

### 3.9 Cashier Tally

| Data | Example |
|------|---------|
| Period filter | daily/weekly/monthly/yearly |
| Navigation dates | prev_date, next_date for period |
| Group by days | For display formatting |
| Aggregated payment data | Summed per period |

### 3.10 Billing Management

| Data | Purpose |
|------|---------|
| Payment ID | To undo a payment |
| Reason for undo | Required text input |

### 3.11 Staff Management

**Staff list (table):**
| Data | Example |
|------|---------|
| Name | `"Juan Dela Cruz"` |
| Username | `"juancruz"` |
| Email | `"juan@cotta.com"` |
| Contact number | `"09171234567"` |
| Is active | `true/false` |
| Permission flags | 7 boolean permissions |

**Create/Edit form fields:**
Name, username, password, email, contact number, active status, all 7 permission booleans

### 3.12 Authorization Data (per request)

The portal checks these before allowing any action:
- Login session exists
- Permission flags: can_read_meters, can_accept_payment, can_enroll_customer, can_drop_reading, can_drop_payment, can_enroll_staff, can_manage_billing

---

## 4. Developer Portal

### 4.1 Authentication

| Data | Purpose |
|------|---------|
| Staff login session | Must be logged in |
| is_superuser flag | Must be true |
| Confirmation code | Generated for destructive operations |

### 4.2 Backup Operations

| Data | Purpose |
|------|---------|
| Backup file list | Display available backups |
| Backup filename | To select which to restore |
| Generate confirmation code | Confirm before destructive actions |

### 4.3 Seed Data

| Data | Purpose |
|------|---------|
| Number of customers to seed | User input |
| Number of months of history | User input |

### 4.4 Task Management

| Data | Purpose |
|------|---------|
| Task ID | Track individual task |
| Task type | backup, restore, seed, etc. |
| Task status | pending, running, completed, failed |
| Progress percentage | For progress display |

### 4.5 phpMyAdmin Proxy

No data — just proxies HTTP requests to the phpMyAdmin container.

---

## 5. API Container

### 5.1 MeterReadingApp Data (External API)

**Customer billing profile** (`GET /api/customer/<num>`):
- Customer: number, name, address, contact, email, cumulative balance
- Latest reading: value, timestamp, reader
- Previous reading: value, timestamp, reader
- Consumption
- Water bill, penalty, total due, due date, days remaining
- Pricing tier breakdown
- Payment methods with fees
- Xendit pending transaction
- Recent readings (5), recent payments (10)
- Unpaid bills

**Customer details** (`GET /api/customer/<num>/details`):
- Customer profile
- Last N readings (configurable count)

**Reading operations** (`POST /api/readings/sync`, `/upload`):
- Customer number
- Reading value
- Timestamp
- API key (for auth + staff attribution)

**Sync data** (`GET /api/readings/bulk`):
- All active customers with their latest reading
- For offline meter reading app

**NFC operations**:
- Tag UID → customer number mapping
- Read/write/clear

### 5.2 Billing Data (Internal API)

**Full billing response** — contains ALL the data from section 2:
- Customer info (number, name, address, contact, email, coordinates)
- Latest/previous readings (value, timestamp, reader name)
- Consumption, water bill, bill breakdown by tier
- Unpaid bills (month, amount, penalty)
- Total unpaid, total penalties, carryover, balance, total due
- Due date, days remaining
- Payment methods with fee structures
- Recent payments (last 10)
- Recent readings (last 5)
- Pending Xendit transaction
- Pricing tiers

### 5.3 Staff Data (Internal API)

All the staff-facing data from section 3:
- Staff credentials + permission flags
- Customer list with pagination
- Customer full profile
- API keys with metadata
- Reading management logs
- Payment records
- Cashier tally (aggregated)
- Staff list with permissions
- Dashboard counts

### 5.4 System Data (Internal API)

- Backup file listings
- Background task queue + status
- Configuration values (app_config table)
- Database seed parameters

---

## 6. Background Worker

### 6.1 Reconciliation Data

| Data | Purpose |
|------|---------|
| Xendit transaction external_id | Look up pending payments |
| Transaction status | PAID, FAILED, EXPIRED |
| Customer number | Link payment to billing |
| Amount | Match against bill |

### 6.2 Task Execution

| Data | Purpose |
|------|---------|
| Task type | Which handler to run |
| Task params | Handler-specific config |
| Task status | Track progress |

### 6.3 Database Operations

| Data | Purpose |
|------|---------|
| mysqldump output | Backup files |
| Backup filenames | Restore operations |
| Seed config (count + months) | Generate test data |

---

## 7. Glossary of Domain Data

| Term | Meaning | Stored In |
|------|---------|-----------|
| Customer number | Unique account identifier | `customers.customer_number` |
| Registered name | Name on file (used for verification) | `customers.name` |
| Reading value | Meter reading in cubic meters | `meter_readings.reading_value` |
| Consumption | Difference between two readings | Computed |
| Tier | Water pricing bracket (0-10, 11-20, 21-30, 31-40, 41+) | `pricing.py` |
| Water bill | Amount due before penalty | Computed from tiers |
| Late penalty | ₱15 added after 7 days | `billings.penalty` |
| Carryover | Balance from previous billing cycle | `billings.carryover_offset` |
| Total due | Final amount after all adjustments | Computed |
| Receipt number | Payment tracking ID | `billings.receipt_number` |
| API key | Meter reading app authentication (`CRDC-xxx`) | `api_keys.key` |
| NFC tag UID | NTAG215 unique identifier | `nfc_tags.tag_uid` |
| External ID | Xendit payment session ID | `xendit_transactions.external_id` |
| Permission flag | One of 7 staff permissions | `staff.*` boolean columns |
| Payment method | GCash, Maya, card, OTC, etc. | `payment_methods` table |
