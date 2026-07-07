# Staff Portal Blueprint

Authenticated admin interface at `/staff`.

## Pages

| Route | Feature |
|-------|---------|
| `/staff/dashboard` | Central hub |
| `/staff/customers` | Customer list, enrollment, edit |
| `/staff/readings` | Meter reading page, manage/drop/edit |
| `/staff/payments` | Payment collection, cashier tally |
| `/staff/bills` | Billing management |
| `/staff/staff` | Staff list, create, edit |
| `/staff/api` | API key generation/revocation |

## Permissions

7 granular permissions control access: can_read_meters, can_accept_payment, can_enroll_customer, can_drop_reading, can_drop_payment, can_enroll_staff, can_manage_billing.
