# Getting Started

## Project Structure

```
WaterBillingSystem/
├── BillServer/          # Python Flask backend (port 5005)
├── MeterReadingApp/     # React Native / Expo mobile app
├── Docker/              # Docker service files (MySQL compose)
├── documentations/      # MkDocs documentation site
├── compose.yaml         # Multi-service Docker Compose
└── .env                 # Environment variables (create from .env.example)
```

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | >= 3.10 | BillServer runtime |
| Node.js | >= 18 | MeterReadingApp development |
| Docker & Docker Compose | Latest | MySQL database service |
| Expo CLI | Latest | Mobile app development |
| npm / npx | >= 9 | Package management |

---

## 1. Start MySQL Database

The database is required by BillServer and must be running before startup.

```bash
cd Docker
docker compose -f MySQL-compose.yml up -d
```

This starts:

- **MySQL 8.4** on `localhost:3306` (database: `BillServerDB`, user: `root`, pass: `BillServerDB`)
- **phpMyAdmin** on `http://localhost:5002`

Persistent data is stored in the Docker named volume `mysql_data`.

---

## 2. Configure Environment

Copy the example environment file to the project root and fill in all required values:

```bash
cp .env.example .env
```

### Required Variables (no defaults — you must provide values)

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session signing. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `NFC_PWD_SECRET` | NFC tag password derivation. Generate same way as SECRET_KEY. |
| `DB_ENGINE` | Database driver (e.g., `mysql+pymysql`) |
| `DB_NAME` | Database name (e.g., `BillServerDB`) |
| `DB_HOST` | Database host |
| `DB_PORT` | Database port |
| `DB_USERNAME` | Database user |
| `DB_PASS` | Database password |
| `XENDIT_API_KEY` | Xendit API key for payment processing |
| `XENDIT_WEBHOOK_TOKEN` | Xendit webhook verification token (callback auth) |

### Optional Variables

| Variable | Default | Description |
|---|---|---|
| `DEPLOYMENT_TYPE` | `PRODUCTION` | `DEBUG` or `PRODUCTION` |
| `REVERSE_PROXY_PREFIX` | (empty = root) | Path like `/water-billing-system` or `True` for automatic prefix detection via `X-Forwarded-Prefix` header |
| `SESSION_COOKIE_SECURE` | `true` | Restrict session cookies to HTTPS only |
| `SSL_CERTFILE` | — | Path to SSL cert PEM for dev HTTPS |
| `SSL_KEYFILE` | — | Path to SSL key PEM for dev HTTPS |
| `DEBUG` | `false` | Enable superuser DEBUG dashboard in staff portal |

---

## 3. Start BillServer

```bash
cd BillServer

# Create and activate virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start development server
python run.py
```

BillServer will be available at **`http://localhost:5005`**.

### Pre-built Superuser

On first startup, BillServer automatically seeds a superuser account:

| Field | Value |
|---|---|
| Username | `superuser` |
| Password | `superuser` |
| Permissions | All 7 permissions granted |

### Seed Test Data (Optional)

```bash
python seed_test_data.py --customers 20 --months 24
```

Generates 20 realistic customers with 24 months of meter readings and randomized payment patterns.

---

## 4. Start MeterReadingApp

```bash
cd MeterReadingApp
npm install
npx expo start
```

Scan the QR code with the Expo Go app, or press `a` for Android emulator / `i` for iOS simulator.

### Initial Setup (within the app)

1. Open **Settings** (gear icon on Home screen)
2. Enter the **Server IP** (e.g., `http://192.168.1.100:5005`)
3. Enter or scan an **API Key** (generate one from the Staff Portal → Meter Reading page)
4. The app will sync customer data automatically from BillServer

---

## BillServer URLs

| Endpoint | URL |
|---|---|
| Landing page | `http://localhost:5005/` |
| Staff portal | `http://localhost:5005/staff/login` |
| REST API | `http://localhost:5005/api/` |
| With Docker Compose | `http://localhost:7000/` |

---

## Quick Reference: Startup Commands

```bash
# Terminal 1 — Database
cd Docker && docker compose -f MySQL-compose.yml up -d

# Terminal 2 — BillServer
cd BillServer && source .venv/bin/activate && python run.py

# Terminal 3 — Mobile App
cd MeterReadingApp && npx expo start
```

---

## Test & Verify

```bash
# BillServer — server tests
cd BillServer && ./run_tests.sh server

# BillServer — verbose pytest
cd BillServer && python -m pytest tests/ -v

# BillServer — lint
cd BillServer && python -m ruff check apps/ tests/
```
