#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

[ ! -f .venv/bin/activate ] && echo "No .venv found" && exit 1
source .venv/bin/activate

case "${1:-server}" in
  lint)
    echo "==> Ruff check (static analysis, no code execution)"
    ruff check apps/ tests/
    ;;
  all)
    echo "==> Linting first..."
    ruff check apps/ tests/
    echo "==> Full suite (browser + server)"
    RUN_SELENIUM_TESTS=1 pytest tests/ -v
    ;;
  server)
    echo "==> Linting first..."
    ruff check apps/ tests/
    echo "==> Server-side tests only (safe over SSH)"
    pytest tests/test_server.py -v
    ;;
  browser)
    echo "==> Linting first..."
    ruff check apps/ tests/
    echo "==> Browser tests only"
    RUN_SELENIUM_TESTS=1 pytest tests/test_selenium.py -v
    ;;
  *)
    echo "Usage: $0 {all|server|browser|lint}"
    echo "  all      — lint + browser + server (requires Playwright/chromium)"
    echo "  server   — lint + server-side only (default, safe over SSH)"
    echo "  browser  — lint + Playwright tests only"
    echo "  lint     — ruff check only (no tests, no DB)"
    exit 1
    ;;
esac
