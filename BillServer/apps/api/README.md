# API Blueprint

REST API for mobile app integration. All endpoints are under `/api`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/customer/<num>` | Full billing profile for a customer |
| GET | `/api/health` | Health check |
| GET | `/api/key/info` | API key validation + permissions |
| POST | `/api/readings/sync` | Upload readings from mobile app |
| POST | `/api/readings/upload` | Upload a single meter reading |
| GET | `/api/customers/changed?since=<ts>` | Changed customers since timestamp |
| GET | `/api/readings/bulk?customer_numbers=...` | Full customer data + readings |
| GET | `/api/readings/customer/<num>` | Single customer lookup |
| GET | `/api/pricing` | Pricing tiers |
| GET | `/api/nfc/config` | NFC secret + generation |
| GET | `/api/nfc/tags` | All registered NFC tag mappings |
| POST | `/api/nfc/sync` | Upload NFC enrollments |
| POST | `/api/nfc/clear` | Clear all NFC tag mappings |

Xendit-related endpoints are in the billing blueprint, not this blueprint. See [API.md](../../API.md) for full details.
