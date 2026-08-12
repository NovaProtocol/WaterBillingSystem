# Testing

**Directory**: `tests/` (root)

Tests are organized in stages:

```
tests/
├── stage-1-unit/              # Unit tests per container
│   ├── api/                   # API unit tests
│   ├── customer/              # Customer portal unit tests
│   ├── dev/                   # Developer portal unit tests
│   ├── landing/               # Landing page unit tests
│   └── staff/                 # Staff portal unit tests
├── stage-2-page/              # Playwright browser tests per container
│   ├── customer/              # Customer portal page tests
│   ├── dev/                   # Developer portal page tests
│   ├── landing/               # Landing page page tests
│   └── staff/                 # Staff portal page tests
├── stage-3-deploy/            # Deployment integration tests
├── .venv/                     # Virtual environment
└── run_tests.sh               # Test runner script
```

## Running Tests

```bash
./tests/run_tests.sh
```

This script runs pytest across the test stage directories.

## Test Infrastructure

- **Framework**: pytest
- **Browser tests**: Playwright (for page-level end-to-end testing)
- **Database**: Each test suite uses its own approach (mock DB, test DB, or in-memory SQLite)

## Test Stages

### Stage 1 — Unit Tests (`stage-1-unit/`)
Tests for each portal's Flask routes, template rendering, form handling, and API client behavior. One subdirectory per portal (customer, staff, dev).

### Stage 2 — Page Tests (`stage-2-page/`)
Playwright-based browser tests that test the actual rendered pages with JavaScript execution, DOM interaction, and visual assertions. One subdirectory per portal.

### Stage 3 — Deploy Tests (`stage-3-deploy/`)
Deployment integration tests.

## Legacy Information

The original BillServer monolith (now removed) has been fully replaced by the current multi-container architecture.
