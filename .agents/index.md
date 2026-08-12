# Agent Reference Index

Read this to find the reference file you need.

| File | Covers |
|------|--------|
| [project-overview.md](reference/project-overview.md) | High-level architecture, component relationships, tech stack, directory structure |
| [authentication.md](reference/authentication.md) | Staff login, API key auth, billing cookie auth, password hashing, permissions, rate limiting (staff portal) — CSRF protection is **planned**, not yet wired |
| [database-schema.md](reference/database-schema.md) | All 11 models (Staff, Customer, MeterReading, Billing, XenditTransaction, etc.), relationships, indexes |
| [billing-pricing.md](reference/billing-pricing.md) | Pricing tiers, water bill calculation, waterfall payment model, penalty, Xendit integration, carryover |
| [staff-portal.md](reference/staff-portal.md) | All staff routes, permission checks, debug dashboard, customer/reading/payment management |
| [rest-api.md](reference/rest-api.md) | REST API contract: customer/staff/billing endpoints, auth, webhooks — mobile sync/bulk/NFC endpoints are **under rework** (see note at top) |
| [meter-reading-app.md](reference/meter-reading-app.md) | React Native Expo app: screens, navigation, SQLite schema, background sync, offline flow |
| [nfc-security.md](reference/nfc-security.md) | NFC tag reading flow, enrollment wizard, disenrollment, password derivation, NTAG215 protection |
| [background-worker.md](reference/background-worker.md) | Task queue via DB, Xendit reconciliation, backup/restore/seed handlers, self-scheduling |
| [docker-deployment.md](reference/docker-deployment.md) | Compose services, Dockerfile, Caddy gateway, environment variables, reverse proxy, deployment |
| [testing.md](reference/testing.md) | Test structure, conftest fixtures, running tests, Playwright browser tests |
