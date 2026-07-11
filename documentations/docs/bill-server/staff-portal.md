# Staff Portal

Base URL: `/staff/*`

The staff portal is a web dashboard for water billing administration. It uses the Black Dashboard theme (AppSeed) with a sidebar navigation, top navbar, and content area.

## Authentication

### Login

**`GET /staff/login`** — Login page  
**`POST /staff/login`** — Submit credentials

Rate limited to **10 requests per 60 seconds** per IP.

Default superuser: `superuser` / `superuser` (seeded on first startup).

### Logout

**`GET /staff/logout`** — Clear session, redirect to login.

## Dashboard

**`GET /staff/dashboard`** — Main dashboard page. Accessible to all authenticated staff.

---

## Customer Management

### Customer Enrollment

**`GET /staff/customers`** — List of enrollable customers  
**`POST /staff/customers/create`** — Create a new customer

Permission: `can_enroll_customer`

Customer creation fields:
| Field | Required | Description |
|---|---|---|
| `customer_number` | Yes | Unique identifier (e.g., `C-001`) |
| `name` | Yes | Full name |
| `address` | No | Property address |
| `contact_number` | No | Phone number |
| `email` | No | Email address |
| `phase` | Yes | Subdivision phase |
| `block` | Yes | Block within phase |
| `street` | Yes | Street name |
| `x_coordinate` | No | Latitude (for map pin) |
| `y_coordinate` | No | Longitude (for map pin) |

### Customer Management

**`GET /staff/manage-customers`** — Searchable, sortable, paginated customer list

Features:
- Search by name, address, customer number
- Filter by phase, block, street
- Sortable columns (name, cumulative balance, date created)
- Paginated (10–200 per page)

**`POST /staff/manage-customers/<id>/edit`** — Edit customer details  
**`POST /staff/manage-customers/<id>/toggle-active`** — Soft-delete/restore customer

Permission: `can_enroll_customer`

---

## Meter Reading

### API Key Management

**`GET /staff/meter-reading`** — View and manage API keys

**`POST /staff/meter-reading/generate`** — Generate a new API key (`CRDC-<32hex>`)  
**`POST /staff/meter-reading/revoke/<id>`** — Deactivate an API key

Permission: `can_read_meters`

- Staff with `can_drop_reading` see ALL keys; others see only their own.
- Keys are associated with the creating staff member.
- Revoked keys cannot be re-activated.

### Reading Management

**`GET /staff/manage-reading`** — View recent readings with audit logs

**`POST /staff/manage-reading/drop-reading/<id>`** — Delete a reading (audit logged)  
**`POST /staff/manage-reading/edit-reading/<id>`** — Change a reading value (audit logged)

Permission: `can_drop_reading` or `can_manage_billing` (view), `can_drop_reading` (drop/edit)

---

## Payments

### Payment Collection

**`GET /staff/payments`** — Payment collection page  
**`POST /staff/payments/submit`** — Submit a payment

Permission: `can_accept_payment`

Payment submission includes:
- Customer lookup (autocomplete)
- Amount entry
- Receipt number generation
- Automatic billing recalculation

### Cashier Tally

**`GET /staff/cashier-tally`** — Daily cashier report

Shows:
- Payments collected today (or custom date range)
- Payment breakdown by cashier
- Navigation dates (previous/next day)

Permission: `can_accept_payment`

---

## Billing Management

**`GET /staff/manage-billing`** — View billing audit logs (last 50 entries)

**`POST /staff/manage-billing/drop-payment/<id>`** — Delete a payment (audit logged)  
**`POST /staff/manage-billing/edit-payment/<id>`** — Change a payment amount (audit logged)

Permission: `can_manage_billing` (view and manage) or `can_drop_payment`

---

## Staff Management

**`GET /staff/staff`** — List all staff accounts  
**`POST /staff/staff/create`** — Create a new staff account  
**`GET/POST /staff/staff/<id>`** — Edit a staff account

Permission: `can_enroll_staff`

Staff account fields:
| Field | Required | Description |
|---|---|---|
| `username` | Yes | Login username (unique) |
| `name` | Yes | Display name |
| `password` | Yes | Login password |
| `email` | No | Email address |
| `contact_number` | No | Phone number |
| 7 boolean permissions | No | Granular access control (see below) |

## Permission Reference

| Permission | Affects | Default Superuser |
|---|---|---|
| `can_read_meters` | Meter reading page, API key management, reading CRUD | ✓ |
| `can_accept_payment` | Payment collection, cashier tally | ✓ |
| `can_enroll_customer` | Customer enrollment, customer management | ✓ |
| `can_drop_reading` | Delete/edit readings | ✓ |
| `can_drop_payment` | Delete payments | ✓ |
| `can_enroll_staff` | Staff account CRUD | ✓ |
| `can_manage_billing` | Billing management, edit payments | ✓ |

---

## DEBUG Dashboard

When `DEBUG=true` is set in `.env` and the logged-in user is "superuser", a **DEBUG** section appears in the sidebar with development tools.

### Available Actions

| Tool | Description | Endpoint |
|---|---|---|
| **Backup Database** | Full DB snapshot via `mysqldump` — schema, data, triggers, routines, events | `POST /staff/debug/backup` |
| **Restore from Backup** | Restore from a `.sql` backup file — completely replaces the database | `POST /staff/debug/restore` |
| **Seed Test Data** | Generate realistic test customers, readings, and billing records | `POST /staff/debug/seed` |
| **Clear Database** | Truncates all tables — removes all data permanently | `POST /staff/debug/clear` |
| **Read This Month** | Create readings + unpaid bills for all customers without one | `POST /staff/debug/read-this-month` |
| **Unread This Month** | Remove this month's readings (unpaid only) | `POST /staff/debug/unread-this-month` |
| **Pay This Month** | Mark all unpaid this-month bills as paid | `POST /staff/debug/pay-this-month` |
| **Remove Payment This Month** | Revert all paid this-month bills to unpaid | `POST /staff/debug/remove-payment-this-month` |

All destructive actions (restore, seed, clear, and monthly mutations) require typing a randomly generated 8-digit confirmation code before execution.

### Task Queue System

Actions run in a **background worker process** (not in the HTTP request), so the page remains responsive. The system uses two files for cross-process communication:

| File | Purpose | Written by | Read by |
|------|---------|-----------|---------|
| `db_backups/to_bg.json` | Queue of pending job orders | Flask routes | Background worker |
| `db_backups/from_bg.json` | Current job state + completed history | Background worker | Flask routes |

All file access is protected by `fcntl.flock` to prevent corruption when multiple Gunicorn workers access the files concurrently.

#### How it works

1. **Submit**: Clicking an action generates an 8-digit confirmation code. After confirmation, the route writes a job order to `to_bg.json` (the queue).
2. **Process**: A dedicated subprocess (`background_worker.py`, launched from `run.py`) polls the `background_tasks` database table. It claims the oldest queued task and executes it — tasks run **sequentially** (one at a time).
3. **Progress**: The worker writes status updates (progress percentage, messages) to `from_bg.json` at least 2 times per second.
4. **Poll**: The frontend JavaScript polls `GET /staff/debug/tasks` every 2 seconds and renders the current job and completed history.

#### Queue behaviour

- Tasks run in order — a backup finishes before a seed starts.
- On server restart, both `to_bg.json` and `from_bg.json` are cleared. Any queued or running jobs are discarded.
- The worker runs independently of Gunicorn workers — if one worker crashes, the background worker continues unaffected.

#### Status display

The Task Queue card shows:
- **Current job** (if any): Progress bar, status badge, latest message, expandable message log
- **History**: Compeleted/interrupted/errored jobs with expandable logs
- **Queue depth badge**: Number of pending orders awaiting execution

### Task polling API

**`GET /staff/debug/tasks`** — Returns the full task queue status:

```json
{
  "current": {
    "id": "order_5",
    "title": "Seed: 5000c × 120m",
    "status": "running",
    "progress": 42.5,
    "started_at": 1783518484.42,
    "messages": [
      "Order Received: Seed 5000c × 120m",
      "Clearing existing data...",
      "Seeding customer 10/5000..."
    ]
  },
  "queue_depth": 2,
  "history": [
    {
      "id": "order_4",
      "title": "Clear Database",
      "status": "completed",
      "progress": 100,
      "started_at": 1783518459.51,
      "ended_at": 1783518460.21,
      "messages": ["Clearing tables...", "All tables cleared. Superuser preserved."]
    }
  ]
}
```

When idle: `current` is `null`. The history array holds up to 20 recent completed jobs.

**`GET /staff/debug/tasks/<order_id>`** — Returns a single task (current or in history).
