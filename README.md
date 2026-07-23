# Cotta Realty Water Billing System

A water billing management system for Cotta Realty & Development Corporation. 11 Docker containers behind a Caddy reverse proxy gateway.

**Stack:** Python 3.14 free-threaded, Flask 3.1, SQLAlchemy 2.0, MySQL 8.4  
**Mobile:** React Native / Expo MeterReadingApp for field staff  
**Docs:** MkDocs documentation site at `documentation/`

## Quick Start

```bash
git clone https://github.com/NovaProtocol/WaterBillingSystem.git
cd WaterBillingSystem

cp .env.example .env
# Edit .env with your settings

docker compose up -d --build
```

## Port Overview

| Service | URL |
|---------|-----|
| Landing Page | `http://host:7020` |
| Customer Portal | `http://host:7020/customer/` |
| Staff Portal | `http://host:7021/staff/` |
| Documentation | `http://host:7021/documentation/` |
| phpMyAdmin | `http://host:7021/phpmyadmin/` |

## Development

Use `docker compose up -d --build` for the full stack. No need to run individual services manually.

Full documentation at `documentation/`.
