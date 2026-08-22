#!/bin/bash
set -euo pipefail
DIR="$(dirname "$0")"
VENV="$DIR/.venv/bin/python"

if [ ! -f "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$DIR/.venv"
    "$VENV" -m pip install -q -r "$DIR/../shared/requirements.txt" -r "$DIR/requirements.txt"
    "$VENV" -m pip install -q playwright requests
    "$VENV" -m playwright install chromium 2>/dev/null || true
else
    "$VENV" -m pip install -q -r "$DIR/../shared/requirements.txt" -r "$DIR/requirements.txt"
fi

STAGE=${1:-all}

run_subdirs() {
    local label="$1" base="$2"
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  $label"
    echo "═══════════════════════════════════════════════════"
    for dir in "$DIR/$base"/*/; do
        [ -d "$dir" ] || continue
        name=$(basename "$dir")
        echo ""
        echo "  --- $name ---"
        "$VENV" -m pytest "$dir" -v --tb=short 2>&1 | tail -10
    done
}

run_dir() {
    local label="$1" path="$2"
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  $label"
    echo "═══════════════════════════════════════════════════"
    "$VENV" -m pytest "$DIR/$path" -v --tb=short 2>&1 | tail -10
}

if [ "$STAGE" = "all" ] || [ "$STAGE" = "1" ]; then
    run_subdirs "STAGE 1: Individual Unit Tests" "stage-1-unit"
fi

if [ "$STAGE" = "all" ] || [ "$STAGE" = "2" ]; then
    run_subdirs "STAGE 2: Page Render Tests" "stage-2-page"
fi

if [ "$STAGE" = "all" ] || [ "$STAGE" = "3" ]; then
    run_dir "STAGE 3: Full Deployment Test" "stage-3-deploy"
fi
