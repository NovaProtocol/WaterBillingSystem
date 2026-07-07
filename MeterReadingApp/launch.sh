#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "==> MeterReadingApp — Expo"

if [ ! -d node_modules ]; then
    echo "==> Installing Node dependencies..."
    npm install
    echo "==> Dependencies installed."
fi

echo "==> Starting Expo..."
npx expo start
