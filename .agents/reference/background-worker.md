# Background Worker

**Files**: `worker/background_worker.py` (FastAPI app + claim loop) + `worker/task_handlers.py` (handlers)

A **FastAPI app run by granian `--workers 1`** (exactly one process, exactly one claim loop) on the `background-worker` container. Polls the `background_tasks` table for queued tasks. Port 8006 is EXPOSE-only (internal networks; no Caddy route).

## Architecture

- FastAPI app (`app = FastAPI(..., lifespan=lifespan)`), served by granian ASGI: `granian --interface asgi --host 0.0.0.0 --port 8006 --workers 1 app:app`
- On startup: `init_engine()` → `init_db()` → `BackgroundTask.enqueue_unique("xendit_reconcile", ...)`
- Lifespan spawns the async claim loop; cancelled cleanly on shutdown
- Container: `waterbillingsystem_worker`, network `net-data`, volumes `db_backups` + `app_logs`
- Async DB via `shared/db_async.py` (`session_factory`); sync shared services run in threads via `asyncio.to_thread(sync_session)`
- Strict env: `require_env('DEPLOYMENT_TYPE', 'DB_*', 'XENDIT_API_KEY')` at import — FATAL + exit on missing
- `WORKER_JOB_CONCURRENCY` env (default `8`) bounds in-job fan-out

## Task Lifecycle

1. **Enqueue**: API routes call `BackgroundTask.enqueue(task_type, params, title, scheduled_at)`; the worker uses `enqueue_unique` for the periodic reconcile (skips if a same-type task is already queued/running)
2. **Claim** (one job at a time): `SELECT ... WHERE status='queued' AND (scheduled_at IS NULL OR scheduled_at <= NOW) ORDER BY created_at ASC ... FOR UPDATE SKIP LOCKED LIMIT 1`
   - Each poll first marks stale tasks `running` >5 minutes as `failed` (abandoned-worker recovery)
3. **Execute**: sets `status='running'` + `started_at`, awaits the handler with `_report(pct, msg)` callback
4. **Progress**: `TaskState` holds progress/messages in memory; a background persister task flushes to the DB every 0.5s (`PROGRESS_PERSIST_INTERVAL`); handlers never touch the DB session for progress
5. **Complete**: `status='completed'`, `progress=100`, `finished_at`; `failed` on handler exception. (Restore may delete the row — handled gracefully)
6. **Health**: `GET /health` → `{status, mode: idle|working, current_task, progress, last_message}`

## Task Handlers

**File**: `worker/task_handlers.py` — registry `HANDLERS = {task_type: handler}`

| Task Type | Handler | Purpose |
|-----------|---------|---------|
| `xendit_reconcile` | `handle_xendit_reconcile` | Checks PENDING Xendit transactions older than 5 min against Xendit API (`httpx.AsyncClient`, concurrency `WORKER_JOB_CONCURRENCY`). Handles SUCCEEDED/PAID/SETTLED/FAILED/EXPIRED/REVERSED; payments via `submit_payment()` (xendit system user) in a thread. Self-enqueues every 5 min (`enqueue_unique`, `scheduled_at=now+5min`) |
| `backup` | `handle_backup` | Runs `mysqldump` via `asyncio.create_subprocess_exec` (single-transaction, ignores background_tasks table), saves to `db_backups/` |
| `restore` | `handle_restore` | Runs `mysql` (subprocess) to restore from a `.sql` backup file. Calls `ensure_prereq_staff()` afterward (in a thread) |
| `clear` | `handle_clear` | Truncates all tables (SET FOREIGN_KEY_CHECKS=0), preserves system users |
| `seed` | `handle_seed` | Generates test data: staff (6 accounts), API keys, N customers with realistic Filipino names/addresses/coordinates (7 subdivisions), seasonal consumption patterns, N months of reading+billing history with carryover tracking |
| `read-this-month` | `handle_read_this_month` | Auto-generates current-month readings + bills for customers without one; `asyncio.Semaphore(WORKER_JOB_CONCURRENCY)` fan-out |
| `unread-this-month` | `handle_unread_this_month` | Removes current-month readings and unpaid bills (skips paid); semaphore-bounded |
| `pay-this-month` | `handle_pay_this_month` | Auto-pays all unpaid current-month bills (receipt prefix `MONTHLY-`); semaphore-bounded |
| `remove-payment-this-month` | `handle_remove_payment_this_month` | Reverses all current-month payments, recalculates cumulative balances via `_recalc_cumulative_balance()` and `_recalc_total_due()`; semaphore-bounded |

## Xendit Reconciliation Flow

On worker startup, enqueues initial `xendit_reconcile` task (unique). After each run, re-enqueues itself 5 minutes later.

The reconciliation:
1. Fetches all PENDING `XenditTransaction` records older than 5 minutes
2. For each, calls Xendit API (`/v2/sessions/{id}` or `/v2/payment_requests/{id}`) via `httpx.AsyncClient` (concurrent, bounded by `WORKER_JOB_CONCURRENCY`)
3. SUCCEEDED/PAID/SETTLED → processes payment via `submit_payment()` from shared services (credits to xendit system user) in a thread with a sync session
4. FAILED/EXPIRED → marks as failed
5. REVERSED → reverses payment

## Seeding Test Data

`handle_seed` generates:
- `customer_number` is `int` (incremented from 1: `cnum = ci + 1`)
- Staff accounts: admin, cashier1, cashier2, reader1, manager, enroller (with appropriate permissions)
- API keys for admin, reader1
- N customers with realistic Filipino names, addresses (7 phases: L-1, L-2A, L-2C, L-3D, P-1, S-1, C-1), coordinates within ~1.5km radius of base location
- Seasonal consumption: dry season 10-30% higher, wet season 5-10% lower
- N months of reading history with auto-generated Billings and carryover tracking
- Receipt numbers and realistic payment dates for historical bills

## Stale Task Detection

Each poll cycle checks for tasks with status='running' that started >5 minutes ago. These are considered abandoned (worker crash) and marked as 'failed'. Prevents tasks from getting stuck forever.
