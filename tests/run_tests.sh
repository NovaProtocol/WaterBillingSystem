#!/bin/bash
# Multi-stage test runner.
# Stage 1: API endpoint tests (no dependencies)
# Stage 2: Page render tests  (each in its own process to avoid import conflicts)
# Stage 3: Flow tests         (multi-step processes)
#
# Usage: ./tests/run_tests.sh          # run all stages
#        ./tests/run_tests.sh 1        # stage 1 only
#        ./tests/run_tests.sh 2        # stage 2 only
#        ./tests/run_tests.sh 3        # stage 3 only

set -e
VENV="$(dirname "$0")/.venv/bin/python"
TESTS_DIR="$(dirname "$0")"

if [ ! -f "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$(dirname "$0")/.venv"
    "$VENV" -m pip install -q playwright pytest requests flask flask_sqlalchemy flask_login flask_wtf flask_caching werkzeug wtforms itsdangerous python-dotenv cryptography
    "$VENV" -m playwright install chromium 2>/dev/null || true
fi

STAGE=${1:-all}

run_file() {
    local file="$1"
    if [ -f "$file" ]; then
        echo ""
        echo "  $(basename "$file"):"
        "$VENV" -m pytest "$file" -v --tb=short 2>&1 | tail -5
    fi
}

run_dir_separate() {
    local dir="$1"
    if [ -d "$dir" ]; then
        for f in "$dir"/test_*.py; do
            [ -f "$f" ] && run_file "$f"
        done
    fi
}

if [ "$STAGE" = "all" ] || [ "$STAGE" = "1" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  STAGE 1: API Endpoints"
    echo "═══════════════════════════════════════════════════"
    "$VENV" -m pytest "$TESTS_DIR/api-tests" -v --tb=short 2>&1 | tail -5
fi

if [ "$STAGE" = "all" ] || [ "$STAGE" = "2" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  STAGE 2: Page Rendering"
    echo "═══════════════════════════════════════════════════"
    for f in "$TESTS_DIR/page-tests"/test_*.py; do
        [ -f "$f" ] && run_file "$f"
    done
fi

if [ "$STAGE" = "all" ] || [ "$STAGE" = "3" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  STAGE 3: Business Flows"
    echo "═══════════════════════════════════════════════════"
    "$VENV" -m pytest "$TESTS_DIR/flow-tests" -v --tb=short 2>&1 | tail -5
fi
