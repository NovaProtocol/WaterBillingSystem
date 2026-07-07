# Cotta Realty Water Billing System

A water billing management system for Cotta Realty & Development Corporation. Three components work together:

| Component | What it does | Stack |
|-----------|-------------|-------|
| [BillServer](./BillServer/) | Web server — staff portal, customer billing, REST API | Flask 3.1 + MySQL + Gunicorn |
| [MeterReadingApp](./MeterReadingApp/) | Mobile app for field meter readers | React Native / Expo |
| [Docker](./Docker/) | MySQL database + phpMyAdmin | Docker Compose |

## Quick Start

```bash
# 1. Start MySQL
cd Docker && docker compose -f MySQL-compose.yml up -d

# 2. Start BillServer
cd BillServer && ./launch.sh

# 3. (Optional) Start mobile app
cd MeterReadingApp && npx expo start
```

Full docs at [documentations/](./documentations/).
