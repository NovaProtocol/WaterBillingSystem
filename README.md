# Water Billing System

<div align="center">

![WaterBillingSystem](https://github.projectnova.download/public/project/water-billing-system.svg)

</div>

A complete billing system for a small water utility, from the meter to the receipt.

A reader walks up to a meter with a phone, taps it against an NFC tag, and the reading is recorded.
From there the system computes the bill, applies the tariff, tracks who has paid, and lets the
customer check their own account.

It replaces months of hand-written ledger work with something a clerk can actually run, and it keeps
the kind of records a dispute needs.

## What it does

**Readings without a network.** The meter-reading app derives its password on the device itself, so
a reading can be taken in a place with no signal and uploaded whenever a connection appears. This
matters more than it sounds: the meters are outdoors, the readers are on motorcycles, and mobile data
is unreliable. Readings are never lost because a connection was not there at the moment.

**Progressive tariff billing.** Consumption is priced in tiers, so the rate rises as more water is
used, the way a real utility charges. Bills that go unpaid accrue a penalty automatically after a
grace period, without anyone having to notice and apply it by hand.

**Payments that behave like a ledger.** A payment is applied to the oldest unpaid bill first, and any
excess becomes credit on the account rather than disappearing. Partial payments are handled the same
way, so a customer paying half now and half later ends up in the same place as one paying once.

**Every role sees only what it should.** Customers see their own account and nothing else. Staff see
the routes they are responsible for. The customer-facing site cannot read another customer's data,
and that rule is enforced by the API rather than by the page not linking to it.

**A paper trail.** Every edit to a reading or a payment is recorded with who made it and when. A
disputed bill can be resolved from the record instead of from someone's memory.

**Reports and a dashboard.** Collections, arrears, and consumption over a period, for the people who
have to explain the numbers to a board or a cooperative meeting.

## Running it

```bash
cp .env.example .env
# .env.example documents every variable the stack reads; fill it in, then start
docker compose up -d
```

The customer portal is at `/customer/`, the staff panel at `/staff/`, and the admin panel at
`/developer/`.

## Documentation

Full documentation is served by the stack at `/documentation/`, and the sources are in
[`documentation/docs`](documentation/docs).

It covers the API contract, the tariff and penalty rules, the payment waterfall, the NFC
provisioning model, and the database schema.


## License

BSD 3-Clause. See [LICENSE](LICENSE).
