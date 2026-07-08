#!/usr/bin/env bash
set -e

DEPLOYMENT_TYPE="${1}"
PORT="${2:-5005}"

if [ -z "${DEPLOYMENT_TYPE}" ] || { [ "${DEPLOYMENT_TYPE}" != "DEBUG" ] && [ "${DEPLOYMENT_TYPE}" != "PRODUCTION" ]; }; then
    echo "Usage: $0 [DEBUG|PRODUCTION] [port]"
    exit 1
fi

echo "==> BillServer — $DEPLOYMENT_TYPE mode on port $PORT"

echo "==> Killing anything on port $PORT..."
fuser -k "${PORT}/tcp" 2>/dev/null || true

if [ ! -f .venv/bin/activate ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi

echo "==> Activating virtual environment..."
source .venv/bin/activate

if [ ! -f .venv/.requirements_installed ]; then
    echo "==> Installing Python dependencies..."
    python -m pip install -r requirements.txt --quiet --break-system-packages || true
    touch .venv/.requirements_installed
    echo "==> Dependencies installed."
fi

echo "==> Starting BillServer..."
python run.py --deployment_type "$DEPLOYMENT_TYPE"
