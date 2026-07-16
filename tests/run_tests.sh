#!/bin/bash
# Multi-stage test runner.
# Stage 1: Endpoint tests (pytest, fast)
# Stage 2: Page render tests   (Playwright, renders pages)
# Stage 3: Flow tests          (multi-step processes)
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
    "$VENV" -m playwright install chromium
fi

STAGE=${1:-all}

run_stage() {
    local name="$1"
    local stage="$2"
    local dir="$TESTS_DIR/$stage-tests"
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  STAGE $stage: $name"
    echo "═══════════════════════════════════════════════════"
    if [ -d "$dir" ]; then
        "$VENV" -m pytest "$dir" -v --tb=short 2>&1 | tail -20
    else
        echo "  (no tests)"
    fi
}

if [ "$STAGE" = "all" ] || [ "$STAGE" = "1" ]; then
    run_stage "API Endpoints" "api"
fi
if [ "$STAGE" = "all" ] || [ "$STAGE" = "2" ]; then
    run_stage "Page Rendering" "page"
fi
if [ "$STAGE" = "all" ] || [ "$STAGE" = "3" ]; then
    run_stage "Business Flows" "flow"
fi
