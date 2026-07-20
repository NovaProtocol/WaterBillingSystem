# Getting Started

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Docker & Docker Compose | Latest | All services (recommended) |
| Python | >= 3.10 | Individual service development |
| Node.js | >= 18 | MeterReadingApp development |
| Expo CLI | Latest | Mobile app development |

---

## 1. Clone & Configure

```bash
git clone <repo-url> WaterBillingSystem
cd WaterBillingSystem
cp .env.example .env
```

Edit `.env` with your preferred editor. Key variables:

| Variable | Default | Description |
|---|---|---|
| `DEPLOYMENT_TYPE` | `PRODUCTION` | `DEBUG` or `PRODUCTION` |
| `SECRET_KEY` | — | Flask session signing. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `NFC_PWD_SECRET` | — | NFC tag password derivation |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, `DB_PASS` | — | MySQL connection |
| `INTERNAL_API_KEY` | — | API-to-API auth between containers |
| `API_BASE_URL` | `http://api:8008` | Internal API endpoint |
| `GATEKEEPER_INTERNAL` | `http://gatekeeper:7000` | Gatekeeper auth service |
| `XENDIT_API_KEY` | — | Xendit payment gateway API key |
| `XENDIT_WEBHOOK_TOKEN` | — | Xendit webhook verification token |
| `CACHE_TYPE` | `FileSystemCache` | Cache backend for portal services |

---

## 2. Start All Services

```bash
docker compose up -d
```

This builds and starts all 11 containers. First-time build takes several minutes.

---

## 3. Access the System

### Public Routes (port 7020)

| URL | Service |
|---|---|
| `http://localhost:7020/` | Landing page (house models) |
| `http://localhost:7020/customer/` | Customer portal (bill lookup) |
| `http://localhost:7020/webhook/` | Xendit webhook proxy |

### Private Routes (port 7021 — requires Gatekeeper login)

| URL | Service |
|---|---|
| `http://localhost:7021/staff/` | Staff portal (management dashboard) |
| `http://localhost:7021/developer/` | Developer portal (debug panel) |
| `http://localhost:7021/documentation/` | MkDocs documentation site |
| `http://localhost:7021/phpmyadmin/` | phpMyAdmin database admin |

### Default Superuser

On first database seed, a superuser account is created:

| Field | Value |
|---|---|
| Username | `superuser` |
| Password | `superuser` |
| Permissions | All 7 granted |

---

## 4. Seed Test Data (Optional)

Access the **Developer Portal** (`http://localhost:7021/developer/`) and use the Database Tools panel to seed test data (choose customer count and months of history).

---

## 5. Development Workflow

Each service has a `launch.sh` script for standalone development outside Docker:

```bash
# Example: run the API container standalone
cd api
./launch.sh
```

`launch.sh` typically:
1. Creates a Python venv (first run)
2. Installs dependencies
3. Starts a Gunicorn dev server with hot-reload

The shared library lives at `shared/` and is mounted via `PYTHONPATH=/app/shared`.

### Quick Reference

```bash
# Start everything
docker compose up -d

# View logs for a specific service
docker compose logs -f api

# Rebuild a single service after code changes
docker compose up -d --build api

# Run database migrations
docker compose exec api python manage.py migrate

# Run tests
docker compose exec api python -m pytest tests/ -v

# Stop everything
docker compose down
```

---

## 6. Mobile App (MeterReadingApp)

```bash
cd MeterReadingApp
npm install
npx expo start
```

### Initial Setup

1. Open **Settings** (gear icon on Home screen)
2. Enter the **Server IP** (e.g., `http://192.168.1.100:7020`)
3. Enter or scan an **API Key** (generate from Staff Portal → Meter Reading page)
4. The app syncs customer data automatically
