# Cotta Water Billing System

Water billing platform for **Cotta Realty**: meter reading collection, billing computation, payment processing, customer management. 11 Docker services behind a Caddy reverse proxy.

## Services Overview

| Service | Container | Internal Port | Caddy Route | Network |
|---|---|---|---|---|
| **Caddy Gateway** | `caddy-gateway` | 7020 | — | `gatekeeper_dynamic`, cloudflared |
| **Landing Page** | `landing-page` | 8001 | `/*` (7020) | net-public |
| **Customer Portal** | `customer-portal` | 8002 | `/customer/*` (7020) | public, api |
| **Staff Portal** | `staff-portal` | 8003 | `/staff/*` (7020) | net-private, net-api |
| **Developer Portal** | `developer-portal` | 8004 | `/developer/*` (7020) | net-private, net-api |
| **Documentation** | `documentation` | 8005 | `/documentation/*` (7020) | net-private |
| **API Container** | `api` | 8008 | — | api, data, public |
| **Webhook Container** | `webhook-container` | 8009 | `/webhook/*` (7020) | public, api |
| **Background Worker** | `background-worker` | 8006 (EXPOSE, internal) | — | data |
| **phpMyAdmin** | `phpmyadmin` | 80 | `/phpmyadmin/*` (7020) | net-private, net-data |
| **MySQL 8.4** | `mysql-db` | 3306 | — | data |

- Live Caddy is single-port **7020** on `gatekeeper_dynamic` (wildcard gate `gatekeeper_caddy:7000` → `gatekeeper_auth:8001`); `caddy-gateway/Caddyfile` live has 0 `forward_auth` per-app — see `compose.yaml` `127.0.0.1:7020:7020` + `Caddyfile`.
- Every Python service — API, all portals, the webhook proxy, the documentation site, and the background worker — is a **FastAPI app run by granian** (ASGI, 1 worker each). The legacy WSGI stack is fully replaced.

## Architecture Diagram

```mermaid
graph TB
    subgraph "net-public"
        LAND["Landing Page<br/>FastAPI/granian :8001"]
        CP["Customer Portal<br/>FastAPI/granian :8002"]
        WH["Webhook Container<br/>FastAPI/granian :8009"]
    end

    subgraph "net-private"
        SP["Staff Portal<br/>FastAPI/granian :8003"]
        DP["Developer Portal<br/>FastAPI/granian :8004"]
        DOC["Documentation<br/>FastAPI/granian :8005"]
        PMA["phpMyAdmin<br/>:80"]
    end

    subgraph "net-data internal"
        DB[("MySQL 8.4<br/>:3306")]
        WORKER["Background Worker<br/>FastAPI/granian :8006"]
        API["API Container<br/>FastAPI/granian :8008"]
    end

    subgraph "gatekeeper_dynamic (external wildcard)"
        GK["GateKeeper wildcard<br/>gatekeeper_caddy:7000 → gatekeeper_auth:8001"]
    end

    subgraph "cloudflared-tunnel (external)"
        TUN["Cloudflare Tunnel"]
    end

    subgraph "Caddy Gateway :7020 (single-port, wildcard)"
        CAD["Caddy<br/>:7020 wildcard"]
    end

    CAD -->|"/ /*"| LAND
    CAD -->|"/customer/*"| CP
    CAD -->|"/webhook/*"| WH
    CAD -->|"/staff/*"| SP
    CAD -->|"/developer/*"| DP
    CAD -->|"/documentation/*"| DOC
    CAD -->|"/phpmyadmin/*"| PMA

    CP -->|"internal API"| API
    SP -->|"internal API"| API
    DP -->|"internal API"| API
    WH -->|"internal API"| API

    API --> DB
    WORKER --> DB
    PMA --> DB

    CAD -->|"forward_auth"| GK
    TUN --> CAD
```

## Relationship Overview

```mermaid
graph LR
    subgraph "Field Operations"
        MN["Meter Reader<br/>with Phone"]
    end
    subgraph "Office Operations"
        SP_USER["Staff User<br/>at Desk"]
        CUST_USER["Customer<br/>Portal User"]
    end

    subgraph "MeterReadingApp"
        MOB["Mobile App<br/>React Native / Expo"]
    end

    MN -->|"NFC Scan / Manual"| MOB
    MOB -->|"Bearer Auth<br/>CRDC-API Key"| API
    SP_USER --> SP
    CUST_USER --> CP
    PUBLIC["Public Visitor"] --> LAND
    XENDIT["Xendit<br/>Payment Gateway"] -->|"webhook callback"| WH
```

## Quick Links

| Link | Description |
|---|---|
| [Getting Started](getting-started.md) | Prerequisites, setup, and startup instructions |
| [Architecture](architecture.md) | System architecture diagrams, network topology, data flow |
| [BillServer API Reference](bill-server/api-reference.md) | Complete REST API endpoint documentation |
| [Staff Portal](bill-server/staff-portal.md) | Staff portal routes, permissions, and workflows |
| [Database Models](bill-server/models.md) | All 11 SQLAlchemy models |
| [MeterReadingApp Screens](meter-reading-app/screens.md) | All screens, components, and navigation flow |
| [MeterReadingApp Sync](meter-reading-app/sync.md) | Offline sync architecture, polling, and conflict resolution |
| [Docker Setup](docker/index.md) | Docker Compose deployment |
| [API Contract](api-contract/index.md) | Full API contract with auth details |

**Models**: Staff, Customer, MeterReading, Billing, ApiKey, NfcTag, ManagementLog, Config, PaymentMethod, XenditTransaction, BackgroundTask

**Networks**: `net-public` (bridge), `net-private` (bridge), `net-api` (internal), `net-data` (internal), `net-gk` (external `gatekeeper_default`), `cloudflared-tunnel` (external)
