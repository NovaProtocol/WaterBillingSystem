#!/bin/bash
set -e
VENV="$(dirname "$0")/.venv/bin/python"
TESTS_DIR="$(dirname "$0")"

if [ ! -f "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$(dirname "$0")/.venv"
    "$(dirname "$0")/.venv/bin/pip" install -q pytest requests flask flask_sqlalchemy flask_login flask_wtf flask_caching werkzeug wtforms itsdangerous python-dotenv cryptography
fi

run_suite() {
    local name="$1"
    local dir="$TESTS_DIR/$name-tests"
    if [ -d "$dir" ]; then
        echo "=== $name ==="
        "$VENV" -m pytest "$dir" -v --tb=short 2>&1 | tail -5
        echo ""
    fi
}

if [ $# -eq 0 ]; then
    for suite in api landing-page customer-portal staff-portal developer-portal worker; do
        run_suite "$suite"
    done
elif [ $# -eq 1 ]; then
    run_suite "$1"
else
    echo "Usage: $0 [suite]"
    echo "Suites: api, landing-page, customer-portal, staff-portal, developer-portal, worker"
    exit 1
fi
