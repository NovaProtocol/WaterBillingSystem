# Target Architecture — Detailed Specifications

> **Status**: Planning phase.  
> **Reference**: `target-architecture.md` for the Mermaid flowchart.

---

## 1. Architectural Philosophy

### 1.1 Core Principles

| Principle | Rationale |
|-----------|-----------|
| **API as sole data access layer** | Only the API container and phpMyAdmin have database credentials. Every other container calls the API for data. |
| **Per-consumer API networks** | Each container that calls the API gets its own dedicated Docker network with the API. No two API consumers share a network. |
| **Defense in depth** | No single breach grants access to everything. Layers of auth at network, transport, and application levels. |
| **Independent scalability** | Each container has its own scaling profile. Landing page can be throttled. API can scale to N replicas. Debug is normally stopped. |
| **Server portability** | Any container can be relocated to a different physical server with zero code changes. |

### 1.2 What This Is NOT

- **Not a microservices architecture.** There is one database. The API container is the integration point.
- **Not zero-downtime deployment.** Brief downtime for deploys is acceptable.
- **Not multi-tenant.** Single organization (Cotta Realty).

---

## 2. Container Inventory

### 2.1 Summary (9 Containers)

| # | Container | Role | Networks | DB Access | Scaling |
|---|-----------|------|----------|-----------|---------|
| 1 | `nginx-gateway` | Edge reverse proxy, dual server blocks | net-landing, net-customer, net-staff, net-debug, net-api-ext | **No** | 1 instance |
| 2 | `landing-page` | Company landing page + offerings | net-landing | **No** | 1 worker, throttled |
| 3 | `customer-portal` | Customer identity + billing + Xendit | net-customer, net-api-cust | **No** (calls API) | 2–4 workers |
| 4 | `staff-portal` | Staff login + dashboard/management | net-staff, net-api-staff | **No** (calls API) | 1–2 workers |
| 5 | `debug` | Dev gate + debug + PMA proxy | net-debug, net-api-debug, net-data | **No direct** (calls API, proxies PMA) | 1 worker, normally STOPPED |
| 6 | `api` | Blanket /api/* + internal endpoints | net-api-ext, net-api-cust, net-api-staff, net-api-debug, net-data | **Yes** (rw all) | 2–8 workers |
| 7 | `background-worker` | Async task processor | net-data | **Yes** (rw all) | 1 instance |
| 8 | `phpmyadmin` | MySQL web administration | net-data | **Yes** (rw all) | 1 instance |
| 9 | `mysql-db` | MySQL 8.4 database | net-data | — | 1 instance |

---

## 3. Network Design — Per-Consumer API Networks

### 3.1 Network Topology

Each API consumer (customer-portal, staff-portal, debug) has its own dedicated network pair with the API. No two consumers ever share a network.

```
┌────────────────────────────────────────────────────────────────────────┐
│                           Docker Host                                  │
│                                                                        │
│  net-landing:  nginx ── landing-page                                   │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  landing ──► CANNOT reach any other container or the API     │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-customer:  nginx ── customer-portal                               │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  customer ──► CANNOT reach staff, debug, db                  │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-staff:  nginx ── staff-portal                                     │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  staff ──► CANNOT reach customer, debug, db                  │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-debug:  nginx ── debug                                            │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  debug ──► CANNOT reach customer or staff                     │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-api-ext:  nginx ── api (external API: webhook, reading, key)      │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  nginx routes /api/xendit-payment, /api/reading/*,           │      │
│  │  /api/key/* to api on this network                            │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-api-cust:  customer-portal ── api                                 │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  customer calls /api/internal/* endpoints here                │      │
│  │  NO other container on this network                           │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-api-staff:  staff-portal ── api                                   │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  staff calls /api/internal/* endpoints here                   │      │
│  │  NO other container on this network                           │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-api-debug:  debug ── api                                         │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  debug calls /api/internal/* endpoints here                   │      │
│  │  NO other container on this network                           │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                        │
│  net-data:  api ── worker ── phpmyadmin ── mysql-db ── debug          │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  api ──► mysql-db:3306   (sole app-level DB access)          │      │
│  │  worker ──► mysql-db:3306 (task processing)                  │      │
│  │  phpmyadmin ──► mysql-db:3306 (admin access)                 │      │
│  │  debug ──► phpmyadmin:80 (proxy for /developer/pma)          │      │
│  │  landing ──► NOT on this network                              │      │
│  │  customer-portal ──► NOT on this network                      │      │
│  │  staff-portal ──► NOT on this network                         │      │
│  └─────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Network Access Matrix

| Container | net-landing | net-customer | net-staff | net-debug | net-api-ext | net-api-cust | net-api-staff | net-api-debug | net-data |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| nginx-gateway | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| landing-page | ✓ | — | — | — | — | — | — | — | — |
| customer-portal | — | ✓ | — | — | — | ✓ | — | — | — |
| staff-portal | — | — | ✓ | — | — | — | ✓ | — | — |
| debug | — | — | — | ✓ | — | — | — | ✓ | ✓ |
| api | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| background-worker | — | — | — | — | — | — | — | — | ✓ |
| phpmyadmin | — | — | — | — | — | — | — | — | ✓ |
| mysql-db | — | — | — | — | — | — | — | — | ✓ |

### 3.3 Isolation Guarantees

| Path | Blocked? | Reason |
|------|:---:|--------|
| landing → api | ✓ | No shared network |
| landing → staff | ✓ | No shared network |
| landing → customer | ✓ | No shared network |
| landing → debug | ✓ | No shared network |
| landing → db | ✓ | No shared network |
| customer → staff | ✓ | No shared network |
| customer → debug | ✓ | No shared network |
| customer → db | ✓ | No shared network |
| staff → customer | ✓ | No shared network |
| staff → debug | ✓ | No shared network |
| staff → db | ✓ | No shared network |
| debug → customer | ✓ | No shared network |
| debug → staff | ✓ | No shared network |
| Internet → staff | ✓ | Not on port 443 (VPN + mTLS required) |
| Internet → debug | ✓ | Not on port 443 (normally stopped anyway) |

### 3.4 Communication Paths (Allowed)

| Caller | Target | Network |
|--------|--------|---------|
| nginx | landing | net-landing |
| nginx | customer-portal | net-customer |
| nginx | staff-portal | net-staff |
| nginx | debug | net-debug |
| nginx | api (webhook, reading, key) | net-api-ext |
| customer-portal | api (internal endpoints) | net-api-cust |
| staff-portal | api (internal endpoints) | net-api-staff |
| debug | api (internal endpoints) | net-api-debug |
| debug | phpmyadmin | net-data |
| api | mysql-db | net-data |
| worker | mysql-db | net-data |
| phpmyadmin | mysql-db | net-data |

---

## 4. compose.yaml Structure (Draft)

All environment variables use `${VAR}` syntax from `.env`. Every variable has a corresponding entry in `.env.example`. No hardcoded defaults. If a variable is missing from `.env`, the container will fail to start.

```yaml
services:
  nginx-gateway:
    image: nginx:alpine
    ports:
      - "443:443"
      - "${SECRET_PORT}:8443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    networks:
      - net-landing
      - net-customer
      - net-staff
      - net-debug
      - net-api-ext
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}

  landing-page:
    build: { dockerfile: Dockerfile.landing }
    networks: [net-landing]
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}

  customer-portal:
    build: { dockerfile: Dockerfile.customerportal }
    networks: [net-customer, net-api-cust]
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
      SECRET_KEY: ${SECRET_KEY}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
      API_BASE_URL: ${API_BASE_URL}

  staff-portal:
    build: { dockerfile: Dockerfile.staffportal }
    networks: [net-staff, net-api-staff]
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
      SECRET_KEY: ${SECRET_KEY}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
      API_BASE_URL: ${API_BASE_URL}

  debug:
    build: { dockerfile: Dockerfile.debug }
    networks: [net-debug, net-api-debug, net-data]
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
      SECRET_KEY: ${SECRET_KEY}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
      API_BASE_URL: ${API_BASE_URL}
      PMA_URL: ${PMA_URL}
    profiles: [debug]

  api:
    build: { dockerfile: Dockerfile.api }
    networks: [net-api-ext, net-api-cust, net-api-staff, net-api-debug, net-data]
    volumes: [db_backups:/app/db_backups]
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
      DB_ENGINE: ${DB_ENGINE}
      DB_HOST: ${DB_HOST}
      DB_PORT: ${DB_PORT}
      DB_NAME: ${DB_NAME}
      DB_USERNAME: ${DB_USERNAME}
      DB_PASS: ${DB_PASS}
      SECRET_KEY: ${SECRET_KEY}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
      NFC_PWD_SECRET: ${NFC_PWD_SECRET}
      XENDIT_API_KEY: ${XENDIT_API_KEY}
      XENDIT_WEBHOOK_TOKEN: ${XENDIT_WEBHOOK_TOKEN}
      CACHE_TYPE: ${CACHE_TYPE}
      PYTHON_GIL: ${PYTHON_GIL}
    depends_on: { mysql-db: { condition: service_healthy } }
    deploy: { replicas: 2 }

  background-worker:
    build: { dockerfile: Dockerfile.worker }
    networks: [net-data]
    volumes: [db_backups:/app/db_backups]
    environment:
      DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
      DB_ENGINE: ${DB_ENGINE}
      DB_HOST: ${DB_HOST}
      DB_PORT: ${DB_PORT}
      DB_NAME: ${DB_NAME}
      DB_USERNAME: ${DB_USERNAME}
      DB_PASS: ${DB_PASS}
      XENDIT_API_KEY: ${XENDIT_API_KEY}
    command: ["python", "apps/background_worker.py"]

  phpmyadmin:
    image: phpmyadmin:latest
    networks: [net-data]
    environment:
      PMA_HOST: ${PMA_HOST}

  mysql-db:
    image: mysql:8.4
    networks: [net-data]
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASS}
      MYSQL_DATABASE: ${DB_NAME}
    volumes: [mysql_data:/var/lib/mysql]
    command: --max_connections=200
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s

networks:
  net-landing:     { internal: true }
  net-customer:    { internal: true }
  net-staff:       { internal: true }
  net-debug:       { internal: true }
  net-api-ext:     { internal: true }
  net-api-cust:    { internal: true }
  net-api-staff:   { internal: true }
  net-api-debug:   { internal: true }
  net-data:        { internal: true }

volumes: { mysql_data:, db_backups: }
```

---

## 5. Security Model

### 5.1 Customer Access Chain (Public)

```
Internet → Port 443 → nginx (SSL)
    → / → landing
    → /customer/* → customer-portal
        → net-api-cust: /api/internal/* → api → mysql-db
```

### 5.2 Staff Access Chain (Private)

```
VPN → Secret Port → nginx (SSL + mTLS client cert)
    → /staff/* → staff-portal
        → net-api-staff: /api/internal/* → api → mysql-db
```

**Required**: VPN + company device cert (mTLS) + username/password + permission flags.

### 5.3 Developer Access Chain (Private + Normally Offline)

```
VPN → Secret Port → nginx (SSL + mTLS)
    → /developer/* → debug (must be running)
        → net-api-debug: /api/internal/* → api → mysql-db
        → net-data: phpmyadmin:80 → mysql-db
```

**Required**: VPN + device cert + staff login + superuser role + container running.

---

## 6. Environment Variables

All environment variables must be set in `.env`. Every container validates its required vars at startup — if any are missing, the container exits immediately with a fatal error. No defaults. No silent fallbacks.

### 6.1 Global (All Python Containers)

| Variable | Required By |
|----------|-------------|
| `DEPLOYMENT_TYPE` | All containers — set to `PRODUCTION` in .env |

### 6.2 Secrets

| Variable | Required By |
|----------|-------------|
| `SECRET_KEY` | customer-portal, staff-portal, debug, api |
| `INTERNAL_API_KEY` | customer-portal, staff-portal, debug, api |

### 6.3 Database Connection

| Variable | Required By |
|----------|-------------|
| `DB_ENGINE` | api, background-worker |
| `DB_HOST` | api, background-worker, mysql-db |
| `DB_PORT` | api, background-worker |
| `DB_NAME` | api, background-worker, mysql-db |
| `DB_USERNAME` | api, background-worker |
| `DB_PASS` | api, background-worker, mysql-db |

### 6.4 API Endpoints (for internal API consumers)

| Variable | Required By |
|----------|-------------|
| `API_BASE_URL` | customer-portal, staff-portal, debug |

### 6.5 API Container

| Variable | Required By |
|----------|-------------|
| `NFC_PWD_SECRET` | api |
| `XENDIT_API_KEY` | api, background-worker |
| `XENDIT_WEBHOOK_TOKEN` | api |
| `CACHE_TYPE` | api |
| `PYTHON_GIL` | api |

### 6.6 Nginx & Infra

| Variable | Required By |
|----------|-------------|
| `SECRET_PORT` | nginx-gateway |
| `PMA_HOST` | phpmyadmin (set to `mysql-db`) |
| `PMA_URL` | debug (set to `http://phpmyadmin:80`) |

### 6.7 Full .env.example Reference

See `.env.example` in the project root. Every variable listed above has an entry with a placeholder value.

---

## 7. Internal API Auth

All `/api/internal/*` endpoints require the `X-Internal-Key` header. Every container on `net-api-*` presents this key. Missing or wrong key = 403. The key is never routed through nginx.

---

## 8. Port Mapping

| Host Port | Container:Port | Network |
|-----------|---------------|---------|
| 443 | nginx:443 | net-landing, net-customer |
| `${SECRET_PORT}` | nginx:8443 | net-staff, net-debug, net-api-ext |
| — | api:8008 | net-api-ext, net-api-cust, net-api-staff, net-api-debug, net-data |
| — | landing:8001 | net-landing |
| — | customer-portal:8002 | net-customer |
| — | staff-portal:8003 | net-staff |
| — | debug:8004 | net-debug |
| — | phpmyadmin:80 | net-data |
| — | mysql-db:3306 | net-data |
