# Database Models

All models are defined in `apps/models.py`. BillServer uses 8 tables managed by SQLAlchemy.

## Entity Relationship Diagram

```mermaid
erDiagram
    staff ||--o{ api_keys : "creates"
    staff ||--o{ billings : "processes"
    staff ||--o{ management_logs : "performs"
    staff ||--o{ nfc_tags : "enrolls"
    customers ||--o{ meter_readings : "has"
    customers ||--o{ billings : "has"
    customers ||--o{ management_logs : "references"
    customers ||--o{ nfc_tags : "has"
    api_keys ||--o{ meter_readings : "authorizes"

    staff {
        int id PK
        string username UK
        string name
        binary password
        string email
        string contact_number
        bool can_read_meters
        bool can_accept_payment
        bool can_enroll_customer
        bool can_drop_reading
        bool can_drop_payment
        bool can_enroll_staff
        bool can_manage_billing
        bool is_active
        datetime date_created
        datetime last_modified
    }

    customers {
        int id PK
        string customer_number UK
        string name
        text address
        string contact_number
        string email
        float x_coordinate
        float y_coordinate
        string phase
        string block
        string street
        numeric cumulative_balance
        bool is_active
        datetime deleted_at
        datetime date_created
        datetime date_modified
    }

    meter_readings {
        int id PK
        string customer_number FK
        numeric reading_value
        int token_id FK
        datetime timestamp
        datetime date_created
        datetime date_modified
    }

    billings {
        int id PK
        string customer_number FK
        string receipt_number UK
        numeric paid_amount
        int cashier_id FK
        int reading_id FK
        datetime timestamp
        datetime date_created
        datetime date_modified
    }

    api_keys {
        int id PK
        string key UK
        string label
        int staff_id FK
        bool is_active
        datetime date_created
        datetime last_modified
    }

    management_logs {
        int id PK
        int staff_id FK
        string action_type
        string target_type
        int target_id
        string customer_number FK
        text details
        datetime timestamp
        datetime date_created
        datetime date_modified
    }

    nfc_tags {
        int id PK
        string uid UK
        string customer_number FK
        int enrolled_by_id FK
        datetime date_created
        datetime last_modified
    }

    app_config {
        int id PK
        string key UK
        text value
        datetime date_created
        datetime date_modified
    }
```

---

## Model Details

### Staff

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `username` | String(64) | UNIQUE, NOT NULL |
| `name` | String(128) | NOT NULL, default "" |
| `password` | LargeBinary | NOT NULL (Werkzeug PBKDF2 hash) |
| `email` | String(128) | nullable |
| `contact_number` | String(32) | nullable |
| `can_read_meters` | Boolean | default False |
| `can_accept_payment` | Boolean | default False |
| `can_enroll_customer` | Boolean | default False |
| `can_drop_reading` | Boolean | default False |
| `can_drop_payment` | Boolean | default False |
| `can_enroll_staff` | Boolean | default False |
| `can_manage_billing` | Boolean | default False |
| `is_active` | Boolean | default True |
| `date_created` | DateTime | default utcnow |
| `last_modified` | DateTime | default utcnow, onupdate utcnow |

Inherits `UserMixin` from Flask-Login.

### Customer

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `customer_number` | String(64) | UNIQUE, NOT NULL, INDEX |
| `name` | String(128) | nullable |
| `address` | Text | nullable |
| `contact_number` | String(32) | nullable |
| `email` | String(128) | nullable |
| `x_coordinate` | Float | nullable (latitude) |
| `y_coordinate` | Float | nullable (longitude) |
| `phase` | String(64) | nullable |
| `block` | String(64) | nullable |
| `street` | String(128) | nullable |
| `cumulative_balance` | Numeric(10,2) | default 0.00 |
| `is_active` | Boolean | default True |
| `deleted_at` | DateTime | nullable |
| `date_created` | DateTime | default utcnow |
| `date_modified` | DateTime | default utcnow, onupdate utcnow |

Relationships: `meter_readings` (backref), `billings` (backref), `nfc_tags` (backref)

### MeterReading

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `customer_number` | String(64) | FK → customers.customer_number, NOT NULL, INDEX |
| `reading_value` | Numeric(10,2) | NOT NULL |
| `token_id` | Integer | FK → api_keys.id, NOT NULL, INDEX |
| `timestamp` | DateTime | NOT NULL, INDEX |
| `date_created` | DateTime | default utcnow |
| `date_modified` | DateTime | default utcnow, onupdate utcnow |

Relationships: `customer` → Customer, `token` → ApiKey, `billings` → Billing

### Billing

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `customer_number` | String(64) | FK → customers.customer_number, NOT NULL, INDEX |
| `receipt_number` | String(64) | UNIQUE, NOT NULL |
| `paid_amount` | Numeric(10,2) | NOT NULL |
| `cashier_id` | Integer | FK → staff.id, NOT NULL, INDEX |
| `reading_id` | Integer | FK → meter_readings.id, nullable |
| `timestamp` | DateTime | NOT NULL, INDEX |
| `date_created` | DateTime | default utcnow |
| `date_modified` | DateTime | default utcnow, onupdate utcnow |

Relationships: `customer` → Customer, `reading` → MeterReading, `cashier` → Staff

### ApiKey

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `key` | String(128) | UNIQUE, NOT NULL |
| `label` | String(128) | nullable |
| `staff_id` | Integer | FK → staff.id, NOT NULL |
| `is_active` | Boolean | default True |
| `date_created` | DateTime | default utcnow |
| `last_modified` | DateTime | default utcnow, onupdate utcnow |

Relationships: `staff` → Staff, `meter_readings` → MeterReading

### ManagementLog

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `staff_id` | Integer | FK → staff.id, NOT NULL |
| `action_type` | String(64) | NOT NULL (enum value) |
| `target_type` | String(64) | NOT NULL |
| `target_id` | Integer | NOT NULL |
| `customer_number` | String(64) | FK → customers.customer_number, nullable, INDEX |
| `details` | Text | nullable |
| `timestamp` | DateTime | NOT NULL, INDEX |
| `date_created` | DateTime | default utcnow |
| `date_modified` | DateTime | default utcnow, onupdate utcnow |

### NfcTag

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `uid` | String(64) | UNIQUE, NOT NULL |
| `customer_number` | String(64) | FK → customers.customer_number, NOT NULL, INDEX |
| `enrolled_by_id` | Integer | FK → staff.id, NOT NULL |
| `date_created` | DateTime | default utcnow |
| `last_modified` | DateTime | default utcnow, onupdate utcnow |

Relationships: `customer` → Customer, `enrolled_by` → Staff

### Config

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK |
| `key` | String(128) | UNIQUE, NOT NULL |
| `value` | Text | nullable |
| `date_created` | DateTime | default utcnow |
| `date_modified` | DateTime | default utcnow, onupdate utcnow |

### ActionType Enum

| Value | Description |
|---|---|
| `duplicate` | Duplicate reading detected |
| `drop_payment` | Payment deleted |
| `edit_payment` | Payment amount changed |
| `drop_reading` | Reading deleted |
| `edit_reading` | Reading value changed |
