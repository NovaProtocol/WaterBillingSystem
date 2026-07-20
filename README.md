# Cotta Realty Water Billing System

A water billing management system for Cotta Realty & Development Corporation. Three components work together:

| Component | What it does | Stack |
|-----------|-------------|-------|
| [BillServer](./BillServer/) | Web server — staff portal, customer billing, REST API | Flask 3.1 + MySQL + Gunicorn |
| [MeterReadingApp](./MeterReadingApp/) | Mobile app for field meter readers | React Native / Expo |
| [Docker](./Docker/) | Full deployment — MySQL, BillServer, phpMyAdmin, docs | Docker Compose |

## Quick Start (Development)

```bash
# 1. Start MySQL
cd Docker && docker compose -f MySQL-compose.yml up -d

# 2. Start BillServer
cd BillServer && ./launch.sh DEBUG

# 3. (Optional) Start mobile app
cd MeterReadingApp && npx expo start
```

## Deploy (Production)

```bash
git clone https://github.com/NovaProtocol/WaterBillingSystem.git
cd WaterBillingSystem/Docker
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| BillServer | `http://host:7000` |
| Documentation | `http://host:7001` |
| phpMyAdmin | `http://host:7002` |

Update: `git pull && docker compose restart billserver docs`

Full docs at [documentation/](./documentation/).
