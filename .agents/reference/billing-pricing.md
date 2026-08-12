# Billing & Pricing

## Pricing Tiers

**File**: `shared/pricing.py`

5 progressive tiers:

| Tier | Range | Rate | Type |
|------|-------|------|------|
| First 10 m³ | 0–10 m³ | PHP 150.00 | Flat fee |
| 11 m³ to 20 m³ | 10–20 m³ | PHP 25.00/m³ | Per unit |
| 21 m³ to 30 m³ | 20–30 m³ | PHP 30.00/m³ | Per unit |
| 31 m³ to 40 m³ | 30–40 m³ | PHP 35.00/m³ | Per unit |
| 41 m³ and above | 40+ m³ | PHP 40.00/m³ | Per unit |

`compute_water_bill(consumption)` returns `(total, breakdown_list)`.

Penalty: PHP 15.00 flat (`LATE_PENALTY`), applied if unpaid 7 days (`DUE_DAYS`) past reading timestamp.

`compute_penalty(reading_timestamp, billing_record=None)` — checks due date vs payment timestamp. Uses `payment_timestamp` or `date_paid` if billing_record provided; otherwise checks current time.

## Billing Lifecycle

### Reading Creation

Every meter reading creates a `Billing` record automatically:
- Looks up most recent previous reading (timestamp < new reading.timestamp)
- `consumption` = current_reading - previous_reading
- `billed_amount` = computed from pricing tiers (frozen at creation)
- `is_paid = False`
- `previous_reading_value`, `current_reading_value` stored directly
- If no previous reading exists, reading is created WITHOUT a billing record (first reading)

**File**: `api/reading_service.py` — `_create_billing_for_reading()`, called by `sync_readings()` and `upload_reading()`

### Penalty Application

**File**: `api/billing_service.py` — `ensure_penalty()`

When any billing view loads, checks if a bill is overdue (7 days past reading timestamp). If overdue and penalty hasn't been applied (penalty == 0), writes PHP 15.00 to `penalty` column permanently via `db.session.flush()`.

### Waterfall Payment Model

**File**: `shared/services/payment_service.py` — `submit_payment()`

When a payment is made, the waterfall model applies:

1. Locks customer and all unpaid bills via `SELECT ... FOR UPDATE`
2. Calculates total carryover offset across all customer bills
3. Pays bills **oldest first**:
   - Deducts `billed_amount + penalty - paid_amount` from available funds (`cash_remaining + carryover`)
   - If fully covered: marks bill `is_paid = True`, generates receipt number (`RCP-<timestamp>-<hex>`)
   - Overpayment remains as `cash_remaining`, used for next bill
   - If carryover is consumed, tracked via `carryover_used`
4. If cash_remaining > 0 after all bills: adds to last paid bill's `carryover_offset` (or directly to `customer.cumulative_balance` if no bill was paid)
5. `recalc_cumulative_balance()` sums all `carryover_offset` values to verify/update `customer.cumulative_balance`

`submit_payment()` calls `db.session.flush()` — the **caller must commit**. This allows the payment flow to control the transaction boundary.

### Payment Reversal

**File**: `shared/services/payment_service.py` — `drop_payment()`

Undoes a payment by billing ID. Uses `FOR UPDATE` lock. Finds all bills sharing the receipt number (payment group), reverts all (`is_paid=False`, clears receipt/cashier/payment fields, resets carryover_offset). Logs action via `log_action()`. Recalls `recalc_cumulative_balance()`.

## Xendit Integration

### Payment Flow (Xendit v2 Sessions API)
1. Customer initiates payment on billing portal → `POST /customer/billing/<num>/invoice`
2. Portal calls `POST /api/customer/<n>/invoice` (API endpoint)
3. API validates amount, computes fees via `fee_service.calculate_fee()`
4. Creates Xendit v2 payment session via `https://api.xendit.co/sessions` (basic auth)
5. Creates `XenditTransaction` with status `PENDING`
6. Customer redirected to payment page (GCash, Maya, card, OTC, etc.)
7. Xendit sends webhook → `POST /api/webhook/xendit` (via webhook-container) → proxied to `POST /api/webhook/xendit-payment` (API)
8. Webhook handler verifies `X-Callback-Token`, updates status, calls `submit_payment()` if PAID

### Invoice Creation (API)

**File**: `api/routes/customer.py` — `customer_invoice()`
- Accepts `{amount, payment_method, success_url, cancel_url}`
- Computes fee via `fee_service.calculate_fee()` (checks `PaymentMethod` model)
- Creates Xendit session with `allowed_payment_channels` matching the method's channel_code
- Saves `XenditTransaction` with PENDING status
- Returns `{redirect_url, external_id, id, base_amount, fee_amount, fee_rate}`

### Webhook Proxy

**File**: `webhook-container/routes.py`

A standalone Flask service (port 8009) that proxies Xendit webhooks to the internal API:
- Receives `POST /webhook/xendit` from Caddy
- Forwards as `POST /api/webhook/xendit-payment` to API with `X-Callback-Token` header
- Returns the API response

This avoids exposing the API directly to the internet.

### Reconciliation

Two mechanisms reconcile stuck transactions:
1. **Background worker**: `handle_xendit_reconcile()` runs every 5 minutes, checks PENDING transactions older than 5 minutes against Xendit API
2. Per-transaction: checks status and processes SUCCEEDED/PAID/SETTLED or FAILED/EXPIRED/REVERSED

### Payment Method Fees

**File**: `api/fee_service.py` — 22 payment methods seeded:

| Category | Methods | Fee Structure |
|----------|---------|--------------|
| E-Wallets | GCash (3%), Maya (2%), GrabPay (2%), ShopeePay (2.5%) | Percent + PHP 11 xendit fee |
| Cards | Domestic (3.5%), International (4.5% + PHP 10) | Percent + flat + PHP 11 |
| Direct Debit | BPI, UBP, RCBC (1.3%, min PHP 15) | Percent + minimum + PHP 11 |
| Online Banking | (1.5%, min PHP 15) | Percent + minimum + PHP 11 |
| OTC | 7-Eleven, Cebuana, ECPay, LBC, M Lhuillier, Palawan, Robinsons, SM, USSC | Flat PHP 20-25 or percent + minimum, + PHP 11 |
| QR/BNPL/VA | QRPh (1.5%, min PHP 15), BillEase (1.5%), Virtual Account (1%, min PHP 15) | Percent + minimum + PHP 11 |

All methods use `fee_for(amount)` on `PaymentMethod` model: `fee = (amount * fee_percent / 100) + fee_flat; if fee_minimum and fee < fee_minimum: fee = fee_minimum`.
