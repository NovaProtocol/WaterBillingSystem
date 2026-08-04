#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "==> Documentation — Flask + mkdocs"

if [ ! -f .venv/bin/activate ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if [ ! -f .venv/.requirements_installed ]; then
    echo "==> Installing dependencies..."
    pip install -r ../shared/requirements.txt --quiet --break-system-packages || true
    pip install -r requirements.txt --quiet --break-system-packages || true
    touch .venv/.requirements_installed
    echo "==> Dependencies installed."
fi

echo "==> Building static site..."
mkdocs build

echo "==> Starting Flask dev server..."
export PYTHONPATH=../shared
export FLASK_APP=app.py
export FLASK_DEBUG=1
export SECRET_KEY="${SECRET_KEY:-dev-secret-key}"
export DEPLOYMENT_TYPE="${DEPLOYMENT_TYPE:-DEBUG}"
flask run --host 0.0.0.0 --port 8005
