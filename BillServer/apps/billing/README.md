# Billing Blueprint

Public-facing customer billing lookup at `/billing/<customer_number>`.

Requires cookie-based verification. Shows:

- Current consumption and bill breakdown by pricing tier
- Reading and payment history (paginated)
- Running cumulative balance
- Late penalty status
- Interactive map of customer location

## Xendit Online Payment Integration

Xendit provides online payment via GCash, Maya, card, and other payment methods.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/billing/api/xendit-webhook` | Xendit webhook receiver — processes payment.succeeded, payment.failed, invoice.paid, payment.reversed, payment.chargeback callbacks; verifies via X-Callback-Token header |
| POST | `/billing/api/<customer_number>/create-invoice` | Creates a Xendit invoice/payment request; requires `billing_session` cookie; returns redirect URL, external ID, and Xendit invoice ID |

### `XenditTransaction` Model

Tracks all Xendit payment attempts and their statuses. Used to reconcile pending transactions and update billing records on callback.

### Template

`_pay_online_modal.html` — Payment modal template used in the billing page for online payment initiation.
