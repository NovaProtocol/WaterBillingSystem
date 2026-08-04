# System Architecture

## High-Level Container Diagram

```mermaid
graph TB
    subgraph "Public Zone :7020"
        LAND["Landing Page<br/>Flask :8001"]
        CP["Customer Portal<br/>Flask :8002"]
        WH["Webhook<br/>Flask :8009"]
    end

    subgraph "Private Zone :7021"
        SP["Staff Portal<br/>Flask :8003"]
        DP["Developer Portal<br/>Flask :8004"]
        DOC["Documentation<br/>MkDocs :8005"]
        PMA["phpMyAdmin<br/>:80"]
    end

    subgraph "Internal API"
        API["API Container<br/>Flask :8008"]
    end

    subgraph "Data Layer"
        DB[("MySQL 8.4<br/>:3306")]
        WORKER["Background Worker"]
    end

    subgraph "Infrastructure"
        CAD["Caddy Gateway<br/>:7020 :7021"]
        GK["Gatekeeper<br/>:7000"]
    end

    subgraph "External"
        MOB["MeterReadingApp<br/>React Native/Expo"]
        XENDIT["Xendit<br/>Payment Gateway"]
    end

    CAD --> LAND
    CAD --> CP
    CAD --> WH
    CAD --> SP
    CAD --> DP
    CAD --> DOC
    CAD --> PMA

    CP -->|"internal API"| API
    SP -->|"internal API"| API
    DP -->|"internal API"| API
    WH -->|"internal API"| API

    API --> DB
    WORKER --> DB
    PMA --> DB

    CAD -->|"forward_auth"| GK

    MOB -->|"Bearer Auth<br/>/api/*"| CAD
    XENDIT -->|"webhook"| CAD
```

---

## Network Topology

```mermaid
graph TB
    subgraph "net-public (bridge)"
        LAND[landing-page :8001]
        CP[customer-portal :8002]
        WH[webhook-container :8009]
        API[api :8008]
    end

    subgraph "net-private (bridge)"
        SP[staff-portal :8003]
        DP[developer-portal :8004]
        DOC[documentation :8005]
        PMA[phpMyAdmin :80]
    end

    subgraph "net-api (internal)"
        CP
        SP
        DP
        WH
        API
    end

    subgraph "net-data (internal)"
        DB[(mysql-db :3306)]
        WORKER[background-worker]
    end

    subgraph "net-gk (external)"
        GK[gatekeeper :7000]
    end

    subgraph "cloudflared-tunnel (external)"
        TUN[Cloudflare Tunnel]
    end

    CAD[caddy-gateway] --> net-public
    CAD --> net-private
    CAD --> net-gk
    CAD --> cloudflared-tunnel

    CP --> net-api
    SP --> net-api
    DP --> net-api
    WH --> net-api

    API --> net-data
    WORKER --> net-data
    PMA --> net-data

```

---

## Data Flow: Reading Sync

```mermaid
sequenceDiagram
    participant App as MeterReadingApp
    participant NFC as NFC Tag
    participant API as API Container
    participant DB as MySQL Database

    Note over App,DB: Background sync every 10s

    App->>API: POST /api/readings/sync {readings: [...]}
    API->>DB: INSERT with monthly duplicate check
    API-->>App: {results, errors}
    App->>App: markReadingSynced(localId, serverId)

    App->>API: GET /api/customers/changed?since=<ts>
    API->>DB: SELECT updated customer numbers
    API-->>App: {customer_numbers, server_time}

    loop Batches of 500
        App->>API: GET /api/readings/bulk?customer_numbers=...
        API->>DB: SELECT customers + readings
        API-->>App: {customers, readings}
        App->>App: replaceCustomerBatch() in transaction
    end

    Note over App: Meter reader scans NFC tag

    NFC->>App: tag discovered (customer_number)
    App->>App: getCustomer(customer_number)
    App->>App: getReadingThisMonth(customer_number)
    Note over App: Reject if duplicate month

    App->>API: POST /api/readings/upload (or next sync)
    API->>DB: INSERT + monthly check
    API-->>App: {status: "ok" | "duplicate"}
```

---

## Staff Permission Matrix

Seven boolean permissions control access to Staff Portal pages:

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

---

## API Authentication Methods

| Method | Header / Parameter | Used By |
|---|---|---|---|
| **Bearer Token** | `Authorization: Bearer CRDC-<32hex>` | MeterReadingApp sync, mobile API calls |
| **Query Parameter** | `?api_key=CRDC-<32hex>` | Browser fallback for API key auth |
| **Internal API Key** | `X-Internal-API-Key` header | Container-to-container API calls |
| **Flask-Login Session** | Cookie-based | Staff portal pages |
| **Billing Cookie** | Signed cookie (receipt + name) | Customer billing portal `/billing/*` |
| **GateKeeper forward-auth** | `gatekeeper_token` cookie or `?access_code=` checked by the Caddy gate | All web surfaces (landing, portals, documentation, phpMyAdmin) |

---

## Background Worker

The background worker polls the database for pending tasks (using the `BackgroundTask` model):

- **Database backup** — scheduled MySQL dumps stored in the `db_backups` volume
- **Database restore** — restore from a previous backup
- **Database seed** — populate test data
- **Xendit payment reconciliation** — verify Xendit payment status and sync
