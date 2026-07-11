# Services — Business Logic Layer

| Module | Responsibility |
|--------|---------------|
| `reading_service.py` | Reading sync, upload, drop, edit + bill creation at reading time |
| `payment_service.py` | Waterfall payment (oldest unpaid bills first, cash + carryover), cashier tally |
| `customer_service.py` | Customer CRUD, due computation |
| `billing_service.py` | Penalty assessment, balance adjustments |
| `audit_service.py` | Management log creation for drops/edits |
| `task_handlers.py` | Task handler functions used by the background worker (backup, restore, seed, Xendit reconciliation, etc.) |
