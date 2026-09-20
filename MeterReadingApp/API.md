# BillServer API Documentation

Base URL: `/api`

> **Note:** The `reader` field in all responses returns the staff member's name (resolved via `token.staff.name`), not the API key or raw ID.

---

## Authentication

All endpoints (except `/customer/<customer_number>` which also accepts session auth) require an API key. Provide it via:

**Header (preferred):**
```
Authorization: Bearer <api_key>
```

**Query parameter (fallback):**
```
/api/endpoint?api_key=<api_key>
```

API keys are generated and revoked from the staff dashboard (`/staff/meter-reading`). Format: `CRDC-` + 32 uppercase hex characters. A deactivated (`is_active=false`) key is rejected.

---

## Endpoints

### 1. API Key Info

```
GET /api/key/info
```

**Auth:** API key, `Authorization: Bearer <key>` header or `?api_key=<key>` query param

**Response** `200`, valid key:
```json
{
  "api_key": {
    "id": 1,
    "label": "Meter Reader A",
    "is_active": true,
    "date_created": "2026-06-20T10:32:04"
  },
  "staff": {
    "id": 1,
    "username": "juan",
    "name": "Juan Dela Cruz",
    "can_read_meters": true,
    "can_accept_payment": false,
    "can_enroll_customer": false,
    "can_drop_reading": false,
    "can_drop_payment": false,
    "can_enroll_staff": false,
    "can_manage_billing": false
  }
}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

**Response** `403`, revoked key:
```json
{"error": "API key has been revoked"}
```

---

### 2. Customer: Full Billing Details

```
GET /api/customer/<customer_number>
```

**Auth:** API key (`Authorization: Bearer <key>` header or `?api_key=<key>` query param) **or** staff session (Flask-Login cookie)

**Response** `200`, found:
```json
{
  "customer_number": "C1",
  "name": "Juan Dela Cruz",
  "address": "123 Rizal St., Brgy. San Jose",
  "contact_number": "09123456789",
  "email": "juan.delacruz1@email.com",
  "phase": "Phase 1",
  "block": "Block A",
  "street": "Rose St",
  "latest_reading": {
    "id": 480,
    "reading_value": 250.6,
    "reader": "Juan Dela Cruz",
    "timestamp": 1778968800
  },
  "last_reading": {
    "id": 479,
    "reading_value": 220.3,
    "reader": "Juan Dela Cruz",
    "timestamp": 1776376800
  },
  "consumption": 30.3,
  "bill_breakdown": [
    {"label": "First 10 m³", "units": 10, "charge": 150.0},
    {"label": "11 m³ to 20 m³", "units": 10, "charge": 250.0},
    {"label": "21 m³ to 30 m³", "units": 10.3, "charge": 309.0},
    {"label": "31 m³ to 40 m³", "units": 0, "charge": 0},
    {"label": "41 m³ and above", "units": 0, "charge": 0}
  ],
  "pricing_tiers": [
    {"label": "First 10 m³", "from_unit": 0, "to_unit": 10, "rate": 150.0, "unit": "flat"},
    {"label": "11 m³ to 20 m³", "from_unit": 10, "to_unit": 20, "rate": 25.0, "unit": "m³"},
    {"label": "21 m³ to 30 m³", "from_unit": 20, "to_unit": 30, "rate": 30.0, "unit": "m³"},
    {"label": "31 m³ to 40 m³", "from_unit": 30, "to_unit": 40, "rate": 35.0, "unit": "m³"},
    {"label": "41 m³ and above", "from_unit": 40, "to_unit": 999999, "rate": 40.0, "unit": "m³"}
  ],
  "water_bill": 709.0,
  "original_water_bill": 709.0,
  "carryover": 0.0,
  "cumulative_balance": 0.0,
  "penalty": 15.0,
  "total_due": 724.0,
  "latest_unpaid": true,
  "unpaid_bills": [
    {"month": "June 2026", "amount": 709.0, "penalty": 15.0, "timestamp": 1778968800}
  ],
  "total_unpaid": 709.0,
  "total_penalties": 15.0,
  "due_date": "07-01-2026",
  "days_remaining": 9,
  "billing_items": [
    {
      "id": 480,
      "billing_id": null,
      "reading_value": 250.6,
      "consumption": 30.3,
      "water_bill": 709.0,
      "penalty": 15.0,
      "total_due": 724.0,
      "timestamp": 1778968800,
      "period": 1778968800,
      "paid_amount": 0,
      "receipt_number": null,
      "status": "Unpaid"
    }
  ],
  "recent_payments": [
    {
      "id": 1,
      "receipt_number": "RCP-1712345678-ABCD",
      "paid_amount": 500.0,
      "timestamp": 1712345678,
      "cashier_id": 1,
      "cashier": "superuser"
    }
  ]
}
```

**Response** `401`, missing or invalid auth:
```json
{"error": "Authentication required"}
```

**Response** `404`, customer not found:
```json
{"error": "Customer CUST-999 not found"}
```

---

### 3. Customer: Profile with Reading History

```
GET /api/customer/<customer_number>/details?history=N
```

**Auth:** API key, `Authorization: Bearer <key>` header or `?api_key=<key>` query param (session auth NOT accepted)

**Query params:** `history` (int, default `5`, number of recent readings)

**Response** `200`, success:
```json
{
  "customer": {
    "customer_number": "C1",
    "name": "Juan Dela Cruz",
    "address": "123 Rizal St., Brgy. San Jose",
    "contact_number": "09123456789",
    "email": "juan.delacruz1@email.com",
    "phase": "Phase 1",
    "block": "Block A",
    "street": "Rose St",
    "x_coordinate": 14.6,
    "y_coordinate": 120.95,
    "cumulative_balance": 0.0
  },
  "readings": [
    {"id": 480, "reading_value": 250.6, "reader": "Juan Dela Cruz", "timestamp": 1778968800},
    {"id": 479, "reading_value": 220.3, "reader": "Juan Dela Cruz", "timestamp": 1776376800}
  ]
}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

**Response** `404`, customer not found:
```json
{"error": "Customer CUST-999 not found"}
```

---

### 4. Customer: Reference (Single + Latest Reading)

```
GET /api/readings/customer/<customer_number>
```

**Auth:** API key + `can_read_meters` permission

**Response** `200`, success:
```json
{
  "customer_number": "C1",
  "name": "Juan Dela Cruz",
  "address": "123 Rizal St., Brgy. San Jose",
  "contact_number": "09123456789",
  "phase": "Phase 1",
  "block": "Block A",
  "street": "Rose St",
  "x_coordinate": 14.6,
  "y_coordinate": 120.95,
  "last_reading_value": 250.6,
  "last_reading_timestamp": 1778968800,
  "last_reading_reader": "Juan Dela Cruz"
}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

**Response** `403`, missing `can_read_meters` permission:
```json
{"error": "Forbidden"}
```

**Response** `404`, customer not found:
```json
{"error": "Customer CUST-999 not found"}
```

---

### 5. Readings: Bulk Sync

```
POST /api/readings/sync
```

**Auth:** API key + `can_read_meters` permission
**Content-Type:** `application/json`

**Request body:**
```json
{
  "readings": [
    {"customer_number": "C1", "reading_value": 280.5, "timestamp": 1779000000},
    {"customer_number": "C2", "reading_value": 150.2}
  ]
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_number` | string | yes | n/a | Must exist in DB |
| `reading_value` | number | yes | n/a | Meter reading in m³ |
| `timestamp` | int | no | current time | Unix timestamp |

The reader is automatically set to the staff member associated with the API key.

**Monthly duplicate check:** If a reading already exists for the same customer in the same calendar month, it is rejected and logged to `ManagementLog`.

**Response** `200`, partial success (some accepted, some rejected):
```json
{
  "synced": 1,
  "total": 2,
  "results": [
    {"index": 0, "reading_id": 42, "customer_number": "C1"}
  ],
  "errors": [
    {"index": 1, "error": "This meter has already been read this month"}
  ]
}
```

**Response** `200`, all accepted:
```json
{
  "synced": 2,
  "total": 2,
  "results": [
    {"index": 0, "reading_id": 42, "customer_number": "C1"},
    {"index": 1, "reading_id": 43, "customer_number": "C2"}
  ],
  "errors": []
}
```

**Response** `400`, missing required field:
```json
{"error": "readings field is required"}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

---

### 6. Readings: Upload Single

```
POST /api/readings/upload
```

**Auth:** API key + `can_read_meters` permission
**Content-Type:** `application/json`

**Request body:**
```json
{
  "customer_number": "C1",
  "reading_value": 310.2,
  "timestamp": 1779100000
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_number` | string | yes | n/a | Must exist in DB |
| `reading_value` | number | yes | n/a | Meter reading in m³ |
| `timestamp` | int | no | current time | Unix timestamp |

**Response** `201`, created:
```json
{
  "success": true,
  "reading_id": 481,
  "customer_number": "C1",
  "reading_value": 310.2,
  "timestamp": 1779100000,
  "reader": "Superuser"
}
```

**Response** `400`, missing required field:
```json
{"error": "customer_number is required"}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

**Response** `404`, customer not found:
```json
{"error": "Customer C1 not found"}
```

**Response** `409`, duplicate month:
```json
{"error": "This meter has already been read this month"}
```

---

### 7. API: Change Detection

```
GET /api/customers/changed?since=<timestamp>
```

**Auth:** API key + `can_read_meters` permission

**Query params:** `since` (int, required), Unix timestamp

Detects: customer profile edits, new/edited readings, dropped readings (via ManagementLog).

**Response** `200`, changes found:
```json
{
  "customer_numbers": ["C1", "C5"],
  "server_time": 1779000000,
  "total_customers": 20
}
```

**Response** `200`, no changes:
```json
{
  "customer_numbers": [],
  "server_time": 1779000000,
  "total_customers": 20
}
```

**Response** `400`, missing `since` parameter:
```json
{"error": "since parameter is required"}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

---

### 8. API: Bulk Customer + Readings Data

```
GET /api/readings/bulk?customer_numbers=C1,C2&limit=5
```

**Auth:** API key + `can_read_meters` permission

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `customer_numbers` | string | required | Comma-separated list of customer numbers |
| `limit` | int | `0` (no limit) | Max readings per customer |

**Response** `200`, success:
```json
{
  "customers": {
    "C1": {
      "customer": {
        "customer_number": "C1",
        "name": "Juan Dela Cruz",
        "address": "123 Rizal St., Brgy. San Jose",
        "contact_number": "09123456789",
        "phase": "Phase 1",
        "block": "Block A",
        "street": "Rose St",
        "x_coordinate": 14.6,
        "y_coordinate": 120.95,
        "nfc_uid": "045A6BC2DEF180"
      },
      "readings": [
        {"id": 480, "reading_value": 250.6, "reader": "Juan Dela Cruz", "timestamp": 1778968800}
      ]
    }
  }
}
```

**Response** `400`, missing `customer_numbers` parameter:
```json
{"error": "customer_numbers parameter is required"}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

---

### 9. Pricing Tiers

```
GET /api/pricing
```

**Auth:** API key + `can_read_meters` permission

**Response** `200`, success:
```json
{
  "tiers": [
    {"label": "First 10 m³", "from_unit": 0, "to_unit": 10, "rate": 150.0, "unit": "flat"},
    {"label": "11 m³ to 20 m³", "from_unit": 10, "to_unit": 20, "rate": 25.0, "unit": "m³"},
    {"label": "21 m³ to 30 m³", "from_unit": 20, "to_unit": 30, "rate": 30.0, "unit": "m³"},
    {"label": "31 m³ to 40 m³", "from_unit": 30, "to_unit": 40, "rate": 35.0, "unit": "m³"},
    {"label": "41 m³ and above", "from_unit": 40, "to_unit": 999999, "rate": 40.0, "unit": "m³"}
  ],
  "late_penalty": 15.0,
  "due_days": 7
}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

---

### 10. NFC Config

```
GET /api/nfc/config
```

**Auth:** API key + `can_read_meters` permission

**Response** `200`, success:
```json
{
  "nfc_pwd_secret": "REDACTED_SET_VIA_NFC_PWD_SECRET_ENV",
  "nfc_generation": 2
}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

---

### 11. NFC: Download Tags

```
GET /api/nfc/tags
```

**Auth:** API key + `can_read_meters` permission

**Response** `200`, success:
```json
{
  "tags": [
    {"uid": "045A6BC2DEF180", "customer_number": "C1"},
    {"uid": "04B9D1E3F5A720", "customer_number": "C2"}
  ]
}
```

**Response** `200`, no tags enrolled:
```json
{
  "tags": []
}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

---

### 12. NFC: Sync Enrollments

```
POST /api/nfc/sync
```

**Auth:** API key + `can_enroll_customer` permission
**Content-Type:** `application/json`

**Request body:**
```json
{
  "enrollments": [
    {"uid": "045A6BC2DEF180", "customer_number": "C1"},
    {"uid": "04B9D1E3F5A720", "customer_number": "C2"}
  ]
}
```

**Response** `200`, all synced:
```json
{
  "synced": 2,
  "results": [
    {"uid": "045A6BC2DEF180", "customer_number": "C1"},
    {"uid": "04B9D1E3F5A720", "customer_number": "C2"}
  ]
}
```

**Response** `400`, missing `enrollments` field:
```json
{"error": "enrollments field is required"}
```

**Response** `401`, missing or invalid API key:
```json
{"error": "Authentication required"}
```

**Response** `403`, missing `can_enroll_customer` permission:
```json
{"error": "Forbidden"}
```

---

## Sync Endpoints Summary (Used by MeterReadingApp)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/readings/sync` | Upload unsynced readings |
| GET | `/api/customers/changed?since=<ts>` | Combined customer + reading change detection |
| GET | `/api/readings/bulk?customer_numbers=...&limit=N` | Full customer data + reading history for a list |
| GET | `/api/readings/customer/<num>` | Single customer lookup (NFC scan) |
| GET | `/api/pricing` | Pricing tiers |
| GET | `/api/key/info` | API key validation + staff permissions |
| GET | `/api/nfc/config` | nfc_pwd_secret for offline password computation |
| POST | `/api/nfc/sync` | Upload NFC tag enrollments |
| GET | `/api/nfc/tags` | Download all registered NFC tag mappings |

---

## Error Responses

All endpoints return errors in the same format:
```json
{"error": "Description of what went wrong"}
```

| Status | Meaning |
|---|---|
| `200` | Success |
| `201` | Created |
| `400` | Bad request (missing/invalid parameters) |
| `401` | Authentication required / invalid API key |
| `403` | Permission denied / inactive key |
| `404` | Resource not found |
| `409` | Conflict (duplicate resource) |
| `500` | Internal server error |

---

## Pricing Tiers Reference

| Tier | Range | Rate | Unit |
|---|---|---|---|
| First 10 m³ | 0–10 m³ | $150.00 | flat |
| 11 m³ to 20 m³ | 10–20 m³ | $25.00 | per m³ |
| 21 m³ to 30 m³ | 20–30 m³ | $30.00 | per m³ |
| 31 m³ to 40 m³ | 30–40 m³ | $35.00 | per m³ |
| 41 m³ and above | 40+ m³ | $40.00 | per m³ |

Late penalty: $15.00 if unpaid after 7 days from reading date.
