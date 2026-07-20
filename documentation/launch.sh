#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "==> Documentations — mkdocs serve"

if [ ! -f .venv/bin/activate ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if [ ! -f .venv/.requirements_installed ]; then
    echo "==> Installing dependencies..."
    python -m pip install -r requirements.txt --quiet --break-system-packages || true
    touch .venv/.requirements_installed
    echo "==> Dependencies installed."
fi

echo "==> Starting mkdocs serve..."
mkdocs serve
