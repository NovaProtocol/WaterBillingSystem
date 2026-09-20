# Cotta Realty Water Billing System

A complete billing system for a small water utility, from the meter to the receipt.

A reader walks up to a meter with a phone, taps it against an NFC tag, and the reading is recorded.
From there the system computes the bill, applies the tariff, tracks who has paid, and lets the
customer check their own account. It replaces months of hand-written ledger work with something a
clerk can actually run.

## What it does

- **Readings without a network.** The meter-reading app computes its password on the device, so a
  reading can be taken in a place with no signal and uploaded later. Readings are never lost because
  a connection was not there.
- **Progressive tariff billing.** Consumption is priced in tiers, so the rate rises the more water is
  used, the way a real utility charges. Late bills accrue a penalty automatically.
- **Payments that behave like a ledger.** A payment is applied to the oldest unpaid bill first, and
  any excess becomes credit on the account instead of disappearing.
- **Every role sees only what it should.** Customers see their own account. Staff see the routes
  they are responsible for. The customer-facing site cannot read another customer's data.
- **A paper trail.** Every edit to a reading or a payment is recorded with who made it and when, so a
  dispute can be resolved from the record rather than from memory.
- **Reports and a dashboard.** Collections, arrears, and consumption over a period, for the people
  who have to explain the numbers.

## Running it

```bash
cp .env.example .env
# .env.example documents every variable the stack reads; fill it in, then start
docker compose up -d
```

`.env.example` lists every variable the stack reads. The customer portal is at `/customer/`, the
staff panel at `/staff/`, and the admin panel at `/developer/`.

## Documentation

Full documentation is served by the stack at `/documentation/`, and the sources are in
[`documentation/docs`](documentation/docs).
