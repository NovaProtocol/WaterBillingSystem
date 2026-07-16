#!/bin/bash
# Run all tests or specific container tests.
# Usage: ./tests/run_tests.sh              # run all
#        ./tests/run_tests.sh api          # run api tests only
#        ./tests/run_tests.sh staff-portal # run staff portal tests only

set -e
VENV="$(dirname "$0")/.venv/bin/python"
TESTS_DIR="$(dirname "$0")"

if [ ! -f "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$(dirname "$0")/.venv"
    "$(dirname "$0")/.venv/bin/pip" install -q pytest requests flask flask_sqlalchemy flask_login flask_wtf flask_caching werkzeug wtforms itsdangerous python-dotenv cryptography
fi

if [ $# -eq 0 ]; then
    echo "Running all tests..."
    "$VENV" -m pytest "$TESTS_DIR" -v
else
    TARGET="$TESTS_DIR/$1-tests"
    if [ -d "$TARGET" ]; then
        echo "Running $1 tests..."
        "$VENV" -m pytest "$TARGET" -v
    else
        echo "No test directory found for: $1"
        echo "Available: api, landing-page, customer-portal, staff-portal, developer-portal, worker"
        exit 1
    fi
fi
