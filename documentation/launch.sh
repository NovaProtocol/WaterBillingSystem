#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 -m pip install -q -r "$DIR/requirements.txt"
mkdocs serve -f "$DIR/mkdocs.yml" --dev-addr 0.0.0.0:8005
