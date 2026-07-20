# Documentation

Full project documentation, built with [MkDocs](https://www.mkdocs.org/) and the Material theme.

## Contents

| Section | Description |
|---------|-------------|
| [Getting Started](./docs/getting-started.md) | Prerequisites and step-by-step startup |
| [Architecture](./docs/architecture.md) | System diagrams, data flow, API auth |
| [BillServer](./docs/bill-server/) | API reference, models, services, deployment, staff portal |
| [MeterReadingApp](./docs/meter-reading-app/) | App features, NFC security, sync flow, screens |
| [API Contract](./docs/api-contract/) | Complete API endpoint reference |
| [Docker](./docs/docker/) | Database infrastructure |

## Building Locally

```bash
pip install -r requirements.txt
mkdocs build
mkdocs serve    # preview at http://localhost:8000
```
