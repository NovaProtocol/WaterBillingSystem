# database — Implementation Plan

## Purpose

Single unified MySQL 8.4 database. Only three containers have access:
- `api` — Sole application-level data access layer
- `background-worker` — Task processing
- `phpmyadmin` — Direct administration (via debug proxy only)

No other container has DB credentials. Debug is on `net-data` solely to proxy to phpmyadmin — it has no MySQL credentials.

## Access Model

```
customer-portal ────HTTP──► api ────MySQL──► mysql-db
staff-portal       ────HTTP──► api ────MySQL──► mysql-db
debug              ────HTTP──► api ────MySQL──► mysql-db
debug              ───proxy──► phpmyadmin ────MySQL──► mysql-db
background-worker  ────MySQL──► mysql-db
```

## Configuration

```yaml
mysql-db:
  image: mysql:8.4
  container_name: waterbillingsystem_db
  restart: unless-stopped
  networks:
    - net-data
    # NOT on net-landing, net-customer, net-staff, net-debug, net-api-ext, net-api-cust, net-api-staff, net-api-debug
    # No host port mapping
  environment:
    MYSQL_ROOT_PASSWORD: ${DB_PASS}
    MYSQL_DATABASE: ${DB_NAME}
  volumes:
    - mysql_data:/var/lib/mysql
  command: --max_connections=200
  healthcheck:
    test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
    interval: 5s
    timeout: 5s
    retries: 10
```

## Connection Pool Budget

Only 3 containers connect:

| Container | Base Pool | Overflow | Per Replica Max | Total (2 API replicas) |
|-----------|-----------|----------|-----------------|------------------------|
| api | 30 | 30 | 60 | 120 |
| background-worker | 5 | 5 | 10 | 10 |
| phpmyadmin | N/A | N/A | ~5 | 5 |
| **Total** | | | | **135** |

MySQL default: 151. Increased to 200. 65 connection headroom.

## Schema

**No changes.** Current 10-table schema unchanged:
- `staff`, `customers`, `meter_readings`, `billings`, `api_keys`, `nfc_tags`, `management_logs`, `app_config`, `payment_methods`, `xendit_transactions`, `background_tasks`

## Database Initialization

On first startup, the `api` container runs `db.create_all()` in its app factory. This creates all tables from SQLAlchemy models if they don't exist. The `staff_seeder.ensure_prereq_staff()` function ensures the superuser and xendit system users exist.

For production deployments with Alembic migrations, run `flask db upgrade` as a one-time init command before starting the stack.

## Users

Single MySQL user (`DB_USERNAME`/`DB_PASS`) for api, worker, and phpmyadmin. All three have full privileges. No need for per-container restricted users since only these three containers can connect — the security boundary is the Docker network, not MySQL user permissions.

## Backup

- `db_backups` volume shared between `api` (creates backups) and `background-worker` (processes backup tasks).
- Backup operations triggered through API internal endpoints by `debug` container.
- Worker processes backup tasks from `background_tasks` table.

## Migration Notes

1. Zero schema changes. Zero data migration.
2. Increase `max_connections` to 200.
3. Remove any host port mapping that may exist for development convenience.
4. Only `api`, `worker`, `phpmyadmin` on `net-data`. All other containers removed.
