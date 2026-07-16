#!/bin/sh
if [ "$DEPLOYMENT_TYPE" = "DEBUG" ]; then
    cp /etc/caddy/Caddyfile.dev /etc/caddy/Caddyfile
else
    cp /etc/caddy/Caddyfile.prod /etc/caddy/Caddyfile
fi
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
