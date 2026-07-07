# Billing Blueprint

Public-facing customer billing lookup at `/billing/<customer_number>`.

Requires cookie-based verification. Shows:

- Current consumption and bill breakdown by pricing tier
- Reading and payment history (paginated)
- Running cumulative balance
- Late penalty status
- Interactive map of customer location
