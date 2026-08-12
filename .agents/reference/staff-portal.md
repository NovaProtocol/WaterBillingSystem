# Staff Portal

**Service**: `staff-portal/` — Flask app serving HTML at `/staff/*`. Pure frontend: all data fetched from API via `api_client.py` using `X-Internal-API-Key`.

Staff must be logged in via Flask-Login. Permission checks via `@permission_required(*perms)` decorator that checks `session['staff_data']`.

## Routes (28+)

### Dashboard & Auth
| Route | Method | Access | Purpose |
|-------|--------|--------|---------|
| `/staff/` | GET | Public | Redirects to login or dashboard |
| `/staff/login` | GET/POST | Public | Login form (rate-limited 10/60s) |
| `/staff/logout` | GET | Authenticated | Logout |
| `/staff/dashboard` | GET | Authenticated | Central hub with counts |

### Customer Search (JSON API endpoints for browser)
| Route | Method | Access | Purpose |
|-------|--------|--------|---------|
| `/staff/customer-lookup` | GET | Authenticated | Customer search — validates mixed input client-side, proxies to `/api/customer/all?q=...` |
| `/staff/api/customer/<n>` | GET | Authenticated | Proxy: fetch single customer JSON from API |
| `/staff/api/customers/search-sort` | GET | Authenticated | Proxies to `/api/customer/all` with `q`, `sort_by`, `sort_dir`, `page`, `size` params |

### Customers
| Route | Method | Permission | Purpose |
|-------|--------|------------|---------|
| `/staff/customers` | GET | `can_enroll_customer` | Customer list with pagination |
| `/staff/customers/create` | POST | `can_enroll_customer` | Create customer |
| `/staff/manage-customers` | GET | `can_enroll_customer` | Edit customer list page |
| `/staff/manage-customers/<id>/edit` | POST | `can_enroll_customer` | Update customer fields |
| `/staff/manage-customers/<id>/toggle-active` | POST | `can_enroll_customer` | Soft-delete/reactivate |
| `/staff/manage-customers/<id>/clear-nfc` | POST | `can_enroll_customer` | Remove NFC tag assignment |

### Meter Readings
| Route | Method | Permission | Purpose |
|-------|--------|------------|---------|
| `/staff/meter-reading` | GET | `can_read_meters` | Reading page (shows API keys) |
| `/staff/meter-reading/generate` | POST | Authenticated | Generate API key |
| `/staff/meter-reading/revoke/<id>` | POST | Authenticated | Revoke API key |
| `/staff/manage-reading` | GET | `can_drop_reading` or `can_manage_billing` | Manage/drop/edit readings with logs |
| `/staff/manage-reading/drop-reading/<id>` | POST | `can_drop_reading` | Drop reading (current month only) |
| `/staff/manage-reading/edit-reading/<id>` | POST | `can_drop_reading` | Edit reading value |

### Payments
| Route | Method | Permission | Purpose |
|-------|--------|------------|---------|
| `/staff/payments` | GET | `can_accept_payment` | Payment submission page |
| `/staff/payments/submit` | POST | `can_accept_payment` | Submit payment |
| `/staff/cashier-tally` | GET | `can_accept_payment` | Cashier payment summary (daily/weekly/monthly/yearly) |

### Billing
| Route | Method | Permission | Purpose |
|-------|--------|------------|---------|
| `/staff/manage-billing` | GET | `can_drop_payment`, `can_manage_billing`, or `can_drop_reading` | Billing management page |
| `/staff/manage-billing/undo-payment/<id>` | POST | `can_drop_payment` | Reverse a payment |

### Staff Management
| Route | Method | Permission | Purpose |
|-------|--------|------------|---------|
| `/staff/staff` | GET | `can_enroll_staff` | Staff list |
| `/staff/staff/create` | POST | `can_enroll_staff` | Create staff |
| `/staff/staff/<id>` | GET/POST | `can_enroll_staff` | Edit staff |

## API Client Functions

**File**: `staff-portal/api_client.py` — 20+ functions. All search/sort/page requests proxy directly to the API — no local customer cache.

| Function | API Call |
|----------|----------|
| `staff_login()` | `POST /api/staff/login` |
| `get_dashboard_data()` | `GET /api/customer/count` + `GET /api/staff/all` |
| `get_customer(n, params)` | `GET /api/customer/<n>` |
| `get_customers(page, size)` | `GET /api/customer/all` |
| `customer_search(q)` | `GET /api/customer/all?q=<q>` — validates mixed input client-side before proxying |
| `customer_search_sort(q, sort_by, sort_dir, page, size)` | `GET /api/customer/all` with query params — proxies directly, no local cache |
| `create_customer(data)` | `POST /api/customer/new` |
| `edit_customer(id, data)` | `PUT /api/customer/update/<n>` |
| `toggle_customer_active(n)` | `DELETE /api/customer/delete/<n>` |
| `clear_customer_nfc(n)` | `POST /api/customer/<n>/nfc/delete` |
| `get_cashier_tally(period, staff_id)` | `GET /api/staff/<id>/cashier-tally` |
| `drop_reading(id, data)` | `POST /api/customer/<n>/reading/drop` — uses `data.get('customer_number', 0)` to prevent `None` in URL |
| `edit_reading(id, data)` | `POST /api/customer/<n>/reading/edit` — uses `data.get('customer_number', 0)` to prevent `None` in URL |
| `submit_payment(data)` | `POST /api/customer/<n>/billing/new` — uses `data.get('customer_number', 0)` to prevent `None` in URL |
| `undo_payment(billing_id, reason)` | `POST /api/customer/<n>/billing/drop` — forwards `reason` from request |
| `generate_api_key(staff_id, data)` | `POST /api/staff/<id>/api-key/generate` |
| `revoke_api_key(staff_id, key_id)` | `POST /api/staff/<id>/api-key/<keyid>/revoke` |
| `list_api_keys(staff_id)` | `GET /api/staff/<id>/api-keys` |
| `get_reading_logs(staff_id)` | `GET /api/staff/<id>/reading-logs` |
| `list_staff()` | `GET /api/staff/all` |
| `get_staff(id)` | `GET /api/staff/<id>` |
| `create_staff(data)` | `POST /api/staff/new` |
| `edit_staff(id, data)` | `POST /api/staff/<id>/edit` |

## Key Files

| File | Purpose |
|------|---------|
| `staff-portal/app.py` | Flask app factory, Flask-Login init, CSRFProtect |
| `staff-portal/routes.py` | All 28+ route handlers |
| `staff-portal/api_client.py` | HTTP client (no local cache — proxies directly to API) |
| `staff-portal/forms.py` | Login form (Flask-WTF) |
| `staff-portal/templates/` | Jinja2 templates |
| `staff-portal/__init__.py` | Blueprint (`staff_bp`, prefix `/staff`) |
