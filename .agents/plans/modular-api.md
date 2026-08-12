# API Endpoints — Master List

**Status**: ✅ = implemented, ❌ = to be removed, 🔲 = unimplemented (planned)

---

## Customer

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | GET | `/api/customer/count` | Total active customer count |
| ✅ | GET | `/api/customer/all` | Paginated list with `?q=`, `?fields=`, `?page=`, `?size=` |
| ✅ | GET | `/api/customer/<n>` | Single customer by number, optional `?fields=` |
| ✅ | GET | `/api/customer/<n>/details` | Profile + N most recent readings (`?history=5`) |
| ✅ | GET | `/api/customer/<n>/profile` | Full computed billing profile (dashboard) |
| ✅ | POST | `/api/customer/new` | Create new customer |
| ✅ | PUT | `/api/customer/update/<n>` | Update customer fields |
| ✅ | DELETE | `/api/customer/delete/<n>` | Soft-delete customer |
| ✅ | GET | `/api/customers/changed` | Change detection (`?since=<unix_ts>`) |

### Customer — Login & Invoicing

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | POST | `/api/customer/login` | Verify identity (number + name + optional receipt). Returns customer data or error code. |
| ✅ | POST | `/api/customer/<n>/invoice` | Create Xendit invoice. Request: `{amount, payment_method}` → `{redirect_url, external_id}` |

### Customer — Readings CRUD

| Status | Method | Path | Description |
|--------|----------|------|-------------|
| ✅ | GET | `/api/customer/<n>/reading` | Paginated readings (`?page=`, `?size=`) |
| ✅ | POST | `/api/customer/<n>/reading/new` | Create a reading + auto-bill (`{reading_value, timestamp}`) |
| ✅ | POST | `/api/customer/<n>/reading/edit` | Edit reading value (`{reading_id, reading_value}`) |
| ✅ | POST | `/api/customer/<n>/reading/drop` | Drop a reading (`{reading_id, reason}`) |

### Customer — Billing

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | GET | `/api/customer/<n>/billing` | Paginated billing records |
| ✅ | POST | `/api/customer/<n>/billing/new` | Record a payment |
| ✅ | POST | `/api/customer/<n>/billing/drop` | Drop/undo a payment |

### Utility Endpoints (MeterReadingApp)

| Status | Method | Path | Description |
|--------|--------|------|-------------|

### Customer — NFC

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | GET | `/api/nfc/config` | NFC password secret |
| ✅ | POST | `/api/nfc/clear` | Clear all tag mappings |
| ✅ | GET | `/api/nfc/tags` | All NFC tag → customer mappings |
| ✅ | POST | `/api/nfc/sync` | Upload NFC enrollments |
| ✅ | DELETE | `/api/nfc/tag/<uid>` | Remove single tag mapping |
| ✅ | POST | `/api/nfc/tag` | Assign tag to customer |

---

## Staff

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | POST | `/api/staff/login` | Verify credentials, return permission flags |
| ✅ | GET | `/api/staff/all` | List all staff |
| ✅ | GET | `/api/staff/<n>` | Single staff member |
| ✅ | POST | `/api/staff/new` | Create staff account |
| ✅ | POST | `/api/staff/<n>/edit` | Edit staff permissions |
| ✅ | GET | `/api/staff/<n>/cashier-tally` | Computed tally by period for a staff member (`?period=`) |
| ✅ | GET | `/api/staff/<n>/reading-logs` | Reading management audit logs for a staff member |
| ✅ | GET | `/api/staff/<n>/api-keys` | List API keys owned by a staff member |
| ✅ | POST | `/api/staff/<n>/api-key/generate` | Generate new API key for a staff member |
| ✅ | POST | `/api/staff/<n>/api-key/<keyid>/revoke` | Revoke an API key |
| ✅ | GET | `/api/staff/info` | Current staff info (auth via API key or internal key). Returns all permission flags. |
| ✅ | POST | `/api/staff/<n>/api-key/verify` | Validate an API key. Request: `{api_key}`. Returns key info + staff permissions. |

---

## Debug / Maintenance

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | POST | `/api/debug/backup` | Queue database backup |
| ✅ | GET | `/api/debug/backups` | List backup files |
| ✅ | POST | `/api/debug/restore` | Queue restore from backup |
| ✅ | GET | `/api/debug/restore-newest` | Restore newest backup |
| ✅ | POST | `/api/debug/clear` | Queue clear all data |
| ✅ | POST | `/api/debug/seed` | Queue seed test data |
| ✅ | POST | `/api/debug/read-month` | Batch read all customers |
| ✅ | POST | `/api/debug/unread-month` | Remove month readings |
| ✅ | POST | `/api/debug/pay-month` | Batch pay this month |
| ✅ | POST | `/api/debug/remove-pay-month` | Remove month payments |
| ✅ | GET | `/api/debug/tasks` | List background tasks |
| ✅ | GET | `/api/debug/tasks/<id>` | Single task status |

---

## System

| Status | Method | Path | Description |
|--------|--------|------|-------------|
| ✅ | GET | `/api/health` | Database connectivity check |
| ✅ | GET | `/api/pricing` | Pricing tiers + late penalty |
| ✅ | POST | `/api/webhook/xendit-payment` | Xendit webhook (X-Callback-Token auth) |

---

## Pagination

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `page` | int | 1 | Must be paired with `size` |
| `size` | int | 50 | Max 200. Must be paired with `page` |
| `fields` | string | — | Comma-separated. `id` + identifier always included |
| `q` | string | — | Search query |

```json
{
  "meta": {"current_page": 1, "page_size": 50, "total_items": 1250, "total_pages": 25},
  "data": [...],
  "links": {"first": "...", "last": "...", "prev": null, "next": "..."}
}
```
