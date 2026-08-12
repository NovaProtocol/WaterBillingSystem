# background-worker — Implementation Plan

## Purpose

Async task processor. Polls `background_tasks` DB table. No web port. Only on `net-data`.

## Changes from Previous Iteration

**No significant changes.** The worker's role is identical — it has always been on `net-data` only and always had direct DB access. The API-as-sole-access model doesn't affect the worker because the worker needs DB access for task processing.

**DEPLOYMENT_TYPE is `PRODUCTION`** (not DEBUG). The worker is a production service.

## Configuration

```yaml
background-worker:
  build:
    context: .
    dockerfile: Dockerfile.worker
  container_name: waterbillingsystem_worker
  restart: unless-stopped
  networks:
    - net-data
    # NOT on any net-api-* network — no web access, period
    # NOT on net-landing, net-customer, net-staff, net-debug
  environment:
    DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE}
    DB_ENGINE: ${DB_ENGINE}
    DB_HOST: ${DB_HOST}
    DB_PORT: ${DB_PORT}
    DB_NAME: ${DB_NAME}
    DB_USERNAME: ${DB_USERNAME}
    DB_PASS: ${DB_PASS}
    XENDIT_API_KEY: ${XENDIT_API_KEY}
  volumes:
    - db_backups:/app/db_backups
  command: ["python", "apps/background_worker.py"]
  depends_on:
    mysql-db:
      condition: service_healthy
```

## Tasks

| Task | Triggered By |
|------|-------------|
| `xendit_reconcile` | Auto-started at worker startup |
| `backup` | Debug → API internal → writes to `background_tasks` |
| `restore` | Debug → API internal → writes to `background_tasks` |
| `clear` | Debug → API internal → writes to `background_tasks` |
| `seed` | Debug → API internal → writes to `background_tasks` |
| `read-this-month` | Debug → API internal → writes to `background_tasks` |
| `unread-this-month` | Debug → API internal → writes to `background_tasks` |
| `pay-this-month` | Debug → API internal → writes to `background_tasks` |
| `remove-payment-this-month` | Debug → API internal → writes to `background_tasks` |

## Dockerfile

```dockerfile
FROM billserver-base:latest

COPY BillServer/apps/background_worker.py /app/apps/background_worker.py

# No EXPOSE — this container has no web port

CMD ["python", "apps/background_worker.py"]
```

## Migration Notes

1. No code changes. Same `apps/background_worker.py`, same `apps/services/task_handlers.py`.
2. Same `db_backups` volume mounted.
3. Debug container triggers tasks by calling API internal endpoints, which write to `background_tasks` table. Worker polls and processes as before.
