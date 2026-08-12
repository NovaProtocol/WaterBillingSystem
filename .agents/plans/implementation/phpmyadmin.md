# phpmyadmin — Implementation Plan

## Purpose

MySQL web administration interface. Only accessible through the `debug` container's reverse proxy at `/developer/phpmyadmin`. **No host port mapping.**

## Access Path

```
User (VPN + device cert + staff login + superuser)
  → nginx:8443 (mTLS)
    → debug:8004 (must be running, --profile debug)
      → superuser role check
        → /developer/phpmyadmin (reverse proxy)
          → phpmyadmin:80
            → mysql-db:3306
```

**Six layers** before reaching the database through PMA.

## Configuration

```yaml
phpmyadmin:
  image: phpmyadmin:latest
  container_name: waterbillingsystem_phpmyadmin
  restart: unless-stopped
  networks:
    - net-data
    # NOT on net-landing, net-customer, net-staff, net-debug, net-api-ext, net-api-cust, net-api-staff, net-api-debug
    # No host port mapping — only reachable through debug proxy
  environment:
    PMA_HOST: ${PMA_HOST}
    PMA_PORT: ${PMA_PORT}
    PMA_ARBITRARY: ${PMA_ARBITRARY}
    UPLOAD_LIMIT: ${UPLOAD_LIMIT}
  depends_on:
    mysql-db:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:80')"]
    interval: 15s
    timeout: 5s
    retries: 3
```

## Key Difference from Current

Current `compose.yaml` exposes PMA directly on host port 7002. In the new architecture:

```diff
- ports:
-   - "7002:80"
+ # No ports exposed. Only reachable through:
+ #   debug container → proxy → phpmyadmin:80
+ # Access requires: VPN + mTLS cert + staff login + superuser + debug container running
```

## Scaling

Single instance. Not scaled.

## Migration Notes

1. Remove `ports: "7002:80"` from compose.yaml.
2. Update any documentation or bookmarks referencing `http://host:7002`.
3. PMA is now accessed at `https://host:8443/developer/phpmyadmin` (private port, requires all auth layers).
