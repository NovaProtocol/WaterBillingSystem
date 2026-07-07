# Docker — Infrastructure

Contains the shared database service used by BillServer.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| MySQL 8.4 | `3306` | Primary database |
| phpMyAdmin | `5002` | Web-based database admin |

## Usage

```bash
docker compose -f MySQL-compose.yml up -d
```

Database credentials: `root` / `BillServerDB` (database: `BillServerDB`).

Data persists in the Docker named volume `mysql_data`.
