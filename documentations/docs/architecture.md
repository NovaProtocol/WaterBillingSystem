# System Architecture

## High-Level Container Diagram

```mermaid
graph TB
    subgraph "MeterReadingApp (React Native / Expo)"
        APP["App.tsx"]
        NAV["NativeStackNavigator"]
        HOME["HomeScreen"]
        READ["ReadingScreen"]
        CUST["CustomerDetailScreen"]
        MAP["MapScreen<br/>Leaflet WebView"]
        SETT["SettingsScreen"]
        SYNC["useSync() Hook"]
        SQLITE["op-sqlite<br/>meterreading.db"]
        NFC["NfcScanner"]
        QR["QrScanner"]
    end

    subgraph "BillServer (Flask 3.1 / Gunicorn)"
        WSGI["Gunicorn<br/>0.0.0.0:5005"]
        FACTORY["create_app()"]
        API["/api Blueprint<br/>REST Endpoints"]
        STAFF["/staff Blueprint<br/>Staff Portal"]
        LAND["/ Blueprint<br/>Landing Page"]
        BILL["/billing Blueprint<br/>Customer Portal"]
        AUTH["/login, /logout"]
        SVC_READ["reading_service"]
        SVC_BILL["billing_service"]
        SVC_CUST["customer_service"]
        SVC_PAY["payment_service"]
        SVC_AUDIT["audit_service"]
        MODELS["models.py"]
        PRICING["pricing.py"]
    end

    subgraph "Docker Infrastructure"
        MYSQL[("MySQL 8.4<br/>:3306")]
        PHPMYADMIN["phpMyAdmin<br/>:5002"]
        VOLUME[("mysql_data<br/>Named Volume")]
    end

    subgraph "Nginx (Production)"
        NGINX["nginx<br/>:5085 → :5005"]
    end

    NFC -->|"onTag(number)"| READ
    QR -->|"onScan(key)"| SETT
    READ --> SQLITE
    SETT --> SQLITE
    SYNC --> SQLITE
    SYNC -->|"HTTP Bearer"| API
    APP --> NAV
    NAV --> HOME & READ & CUST & MAP & SETT

    WSGI --> NGINX
    WSGI --> FACTORY
    FACTORY --> API & STAFF & LAND & BILL & AUTH

    API --> SVC_READ & SVC_CUST
    STAFF --> SVC_READ & SVC_CUST & SVC_PAY & SVC_BILL & SVC_AUDIT
    BILL --> SVC_CUST & SVC_PAY
    SVC_PAY --> SVC_BILL
    SVC_READ & SVC_PAY --> SVC_AUDIT
    SVC_READ & SVC_BILL & SVC_CUST & SVC_PAY --> MODELS
    SVC_BILL --> PRICING

    MODELS --> MYSQL
    MYSQL --> VOLUME
    PHPMYADMIN --> MYSQL
```

---

## Data Flow: Reading Sync

```mermaid
sequenceDiagram
    participant App as MeterReadingApp
    participant NFC as NFC Tag
    participant DB as Local SQLite
    participant API as BillServer API
    participant SDB as MySQL Database

    Note over App: Background sync every 10s

    App->>API: POST /api/readings/sync {readings: [...]}
    API->>SDB: INSERT with monthly duplicate check
    API-->>App: {results, errors}
    App->>DB: markReadingSynced(localId, serverId)

    App->>API: GET /api/customers/changed?since=<ts>
    API->>SDB: SELECT updated customer numbers
    API-->>App: {customer_numbers, server_time}

    loop Batches of 500
        App->>API: GET /api/readings/bulk?customer_numbers=...
        API->>SDB: SELECT customers + readings
        API-->>App: {customers, readings}
        App->>DB: replaceCustomerBatch() in transaction
    end

    Note over App: Meter reader scans NFC tag

    NFC->>App: tag discovered (customer_number)
    App->>DB: getCustomer(customer_number)
    App->>DB: getReadingThisMonth(customer_number)
    Note over App: Reject if duplicate month

    App->>DB: saveReading({customer_number, reading_value, timestamp})
    App->>API: POST /api/readings/upload (or next sync)
    API->>SDB: INSERT + monthly check
    API-->>App: {status: "ok" | "duplicate"}
```

---

## Staff Portal Permission Matrix

```mermaid
graph TB
    subgraph "Staff Permissions (7 Booleans)"
        RM["can_read_meters"]
        AP["can_accept_payment"]
        EC["can_enroll_customer"]
        DR["can_drop_reading"]
        DP["can_drop_payment"]
        ES["can_enroll_staff"]
        MB["can_manage_billing"]
    end

    subgraph "Staff Portal Pages"
        DASH["/staff/dashboard"]
        CUST_PAGE["/staff/customers"]
        MGT_CUST["/staff/manage-customers"]
        READ_PAGE["/staff/meter-reading<br/>API Key Management"]
        MGT_READ["/staff/manage-reading"]
        PAY_PAGE["/staff/payments"]
        TALLY["/staff/cashier-tally"]
        MGT_BILL["/staff/manage-billing"]
        STAFF_LIST["/staff/staff"]
    end

    RM --> READ_PAGE & MGT_READ
    AP --> PAY_PAGE & TALLY
    EC --> CUST_PAGE & MGT_CUST
    DR --> MGT_READ
    DP --> MGT_BILL
    ES --> STAFF_LIST
    MB --> MGT_BILL
    DASH -->|"All authenticated staff"| DASH
```

---

## API Authentication Methods

| Method | Header / Parameter | Used By |
|---|---|---|
| **Bearer Token** | `Authorization: Bearer CRDC-<32hex>` | MeterReadingApp sync, mobile API calls |
| **Query Parameter** | `?api_key=CRDC-<32hex>` | Alternative to Bearer token |
| **Flask-Login Session** | Cookie-based | Staff portal, `/api/customer/:num` |
| **Billing Cookie** | Signed cookie (receipt + name) | Customer billing portal `/billing/*` |

---

## Pricing Engine

```mermaid
graph LR
    T1["0–10 m³<br/>$150.00 flat"]
    T2["11–20 m³<br/>$25.00/m³"]
    T3["21–30 m³<br/>$30.00/m³"]
    T4["31–40 m³<br/>$35.00/m³"]
    T5["41+ m³<br/>$40.00/m³"]
    PEN["Late Penalty<br/>$15.00 after 7 days"]

    compute_water_bill --> T1 & T2 & T3 & T4 & T5
    compute_penalty --> PEN
```

Progressive tier calculation: consumption is applied to each tier bracket sequentially. For example, 35 m³ = $150 (first 10) + $250 (next 10 at $25) + $300 (next 10 at $30) + $175 (last 5 at $35) = **$875 total**.
