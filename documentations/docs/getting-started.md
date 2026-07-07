# Getting Started

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

## 2. Start BillServer

```bash
cd BillServer

# Activate virtual environment (create if needed)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run database migrations
flask db upgrade

# Start development server
python run.py
```

BillServer will be available at **`http://localhost:5005`**.

### Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `True` | Enable debug mode |
| `DB_ENGINE` | `mysql+pymysql` | Database driver |
| `DB_NAME` | `BillServerDB` | Database name |
| `DB_HOST` | `localhost` | Database host |
| `DB_PORT` | `3306` | Database port |
| `DB_USERNAME` | `root` | Database user |
| `DB_PASS` | `BillServerDB` | Database password |

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

## 3. Start MeterReadingApp

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
# BillServer — server-side tests (safe over SSH)
cd BillServer && ./run_tests.sh server

# BillServer — full suite (includes browser tests)
cd BillServer && ./run_tests.sh all

# MeterReadingApp — TypeScript check
cd MeterReadingApp && npx tsc --noEmit
```
