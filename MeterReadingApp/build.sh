#!/bin/bash
set -euo pipefail

MODE="${1:?Usage: $0 [dev|prod|both]}"

export GRADLE_OPTS="-Xmx1024m -Xms512m"

cd "$(dirname "$0")"

case "$MODE" in
  dev)
    echo "==> Building development APK (remote)..."
    npx eas build --platform android --profile development 2>&1
    ;;
  prod)
    echo "==> Building production APK (remote)..."
    npx eas build --platform android --profile production 2>&1
    ;;
  both)
    echo "==> Building both APKs (dev + prod)..."
    npx eas build --platform android --profile development 2>&1
    echo ""
    echo "==> Dev build done, starting prod build..."
    npx eas build --platform android --profile production 2>&1
    ;;
  *)
    echo "Error: mode must be 'dev', 'prod', or 'both'"
    echo "Usage: $0 [dev|prod|both]"
    exit 1
    ;;
esac

echo "==> Done ($MODE build finished)"
