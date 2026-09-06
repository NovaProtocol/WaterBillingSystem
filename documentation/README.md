# Documentation

MkDocs Material site for the WaterBillingSystem, served as its own FastAPI container on `8005` behind the Caddy gateway (`/documentation/*` on `:7020` via wildcard gate `gatekeeper_dynamic`).

## Contents

| Section | Description |
|---------|-------------|
| [Getting Started](./docs/getting-started.md) | Prerequisites and step-by-step startup |
| [Architecture](./docs/architecture.md) | System diagrams, data flow, API auth, gRPC vs HTTP |
| [BillServer](./docs/bill-server/) | API reference, models, services, deployment, staff portal |
| [MeterReadingApp](./docs/meter-reading-app/) | App features, NFC security, sync flow, screens |
| [API Contract](./docs/api-contract/) | Complete API endpoint reference |
| [Docker](./docs/docker/) | Database infrastructure |

## Building Locally

```bash
pip install -r requirements.txt
mkdocs build
mkdocs serve    # preview at http://localhost:8000
./launch.sh     # alternative: serves via mkdocs dev server on :8005
```

In Docker the site is pre-built in `documentation/Dockerfile` (`mkdocs build`) and served by `app.py` (FastAPI + granian on `8005`) — see `compose.yaml` `documentation` service and `caddy-gateway/Caddyfile` `handle_path /documentation/*`.
