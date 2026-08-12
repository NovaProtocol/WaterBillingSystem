# Dockerfile.base — Shared Base Image

## Purpose

Foundation Docker image for all Python containers. Contains shared code (models, services, config, pricing, authentication utilities) and all Python dependencies. Each application container extends this and adds only its blueprint.

## Dockerfile

```dockerfile
# Dockerfile.base
# Python 3.14.6t — free-threaded build
FROM python:3.14.6t-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc g++ libc6-dev default-mysql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY BillServer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Shared application code
COPY BillServer/apps/config.py          /app/apps/config.py
COPY BillServer/apps/models.py          /app/apps/models.py
COPY BillServer/apps/pricing.py         /app/apps/pricing.py
COPY BillServer/apps/authentication/    /app/apps/authentication/
COPY BillServer/apps/services/          /app/apps/services/

RUN python -m compileall -q /app/apps 2>/dev/null || true

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHON_GIL=0
```

## Build Order

```bash
# 1. Base image MUST be built first
docker build -f Dockerfile.base -t billserver-base:latest .

# 2. Application containers (order doesn't matter)
docker build -f Dockerfile.api -t billserver-api:latest .
docker build -f Dockerfile.landing -t billserver-landing:latest .
docker build -f Dockerfile.customerportal -t billserver-customerportal:latest .
docker build -f Dockerfile.staffportal -t billserver-staffportal:latest .
docker build -f Dockerfile.debug -t billserver-debug:latest .
docker build -f Dockerfile.worker -t billserver-worker:latest .
```

## What Containers Add on Top

| Container | Adds | DB? | Networks |
|-----------|------|:---:|----------|
| landing-page | `apps/landing/` | No | net-landing |
| customer-portal | `apps/customer_portal/` | No | net-customer, net-api-cust |
| staff-portal | `apps/staff_portal/` | No | net-staff, net-api-staff |
| debug | `apps/debug/` | No | net-debug, net-api-debug, net-data |
| api | `apps/api/` | Yes | net-api-ext, net-api-cust, net-api-staff, net-api-debug, net-data |
| background-worker | `apps/background_worker.py` | Yes | net-data |

## Notes

- **Python 3.14.6t** — Free-threaded build. `PYTHON_GIL=0` enables free-threading mode.
- **curl** is installed for healthchecks (used by nginx, and as a fallback).
- Containers without DB access still import from base image for shared utilities (`models.py` classes used for type annotations and JSON reconstruction, `config.py` for Flask config patterns, etc.).
- Even though `landing-page` doesn't use `models.py` or `services/`, it's simpler to keep one base image than to create a minimal variant. Disk space is negligible.
- `requests` library is in `requirements.txt` because `customer-portal`, `staff-portal`, and `debug` use it to call the API container.
