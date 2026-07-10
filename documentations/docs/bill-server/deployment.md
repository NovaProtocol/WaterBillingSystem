# Deployment

## Docker

The project runs as four containers defined in `compose.yaml` at the project root.

### Services

| Service | Container | Host Port | Purpose |
|---------|-----------|-----------|---------|
| `waterbillingsystem_db` | waterbillingsystem_db | — | MySQL 8.4, healthchecked via `mysqladmin ping` |
| `waterbillingsystem_main` | waterbillingsystem_main | `7000` | Flask app under Gunicorn (port 5005) |
| `waterbillingsystem_phpmyadmin` | waterbillingsystem_phpmyadmin | `7002` | Database admin UI |
| `waterbillingsystem_documentation` | waterbillingsystem_documentation | `7001` | MkDocs documentation served via `python -m http.server` |

The `waterbillingsystem_main` service waits for the `waterbillingsystem_db` health check to pass before starting. Data persists in named volumes: `mysql_data` for the database and `db_backups` for database backup files (mounted at `/app/db_backups` in the BillServer container). The docs container builds MkDocs on startup from `./documentations`.

### compose.yaml

```yaml
services:
  waterbillingsystem_db:
    image: mysql:8.4
    container_name: waterbillingsystem_db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASS}
      MYSQL_DATABASE: ${DB_NAME}
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 5s
      retries: 10

  waterbillingsystem_main:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: waterbillingsystem_main
    restart: unless-stopped
    ports:
      - "7000:5005"
    networks:
      - default
      - proxy
    environment:
      DEPLOYMENT_TYPE: PRODUCTION
      DB_ENGINE: ${DB_ENGINE}
      DB_HOST: waterbillingsystem_db
      DB_PORT: 3306
      CACHE_TYPE: SimpleCache
      DB_NAME: ${DB_NAME}
      DB_USERNAME: ${DB_USERNAME}
      DB_PASS: ${DB_PASS}
      SECRET_KEY: ${SECRET_KEY}
      NFC_PWD_SECRET: ${NFC_PWD_SECRET}
      XENDIT_API_KEY: ${XENDIT_API_KEY}
      XENDIT_WEBHOOK_TOKEN: ${XENDIT_WEBHOOK_TOKEN}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-true}
      DEBUG: ${DEBUG:-false}
      REVERSE_PROXY_PREFIX: ${REVERSE_PROXY_PREFIX}
    depends_on:
      waterbillingsystem_db:
        condition: service_healthy

  waterbillingsystem_phpmyadmin:
    image: phpmyadmin:latest
    container_name: waterbillingsystem_phpmyadmin
    restart: unless-stopped
    ports:
      - "7002:80"
    environment:
      PMA_HOST: waterbillingsystem_db
    depends_on:
      - waterbillingsystem_db

  waterbillingsystem_documentation:
    image: python:3.14-slim
    container_name: waterbillingsystem_documentation
    restart: unless-stopped
    working_dir: /app
    command: >
      sh -c "
        pip install -r requirements.txt --quiet &&
        mkdocs build --site-dir /app/_site &&
        exec python -m http.server 8000 --directory /app/_site
      "
    ports:
      - "7001:8000"
    networks:
      - default
      - proxy
    volumes:
      - ./documentations:/app

volumes:
  mysql_data:
  db_backups:

networks:
  default:
  proxy:
    external: true
    name: reverse-proxy_proxy
```

### Dockerfile

The Dockerfile uses a multi-stage build. The `builder` stage installs Python dependencies and compiles all `.py` files. The final stage copies only the installed packages and the app code.

```dockerfile
FROM python:3.14-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && rm -rf /var/lib/apt/lists/*
COPY BillServer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY BillServer/ .
RUN python -m compileall -q . 2>/dev/null || true

FROM python:3.14-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app
EXPOSE 5005
ENV DEPLOYMENT_TYPE=PRODUCTION
CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "3", "--access-logfile", "-", "wsgi:app"]
```

The container starts via `wsgi:app`, which sets `DEPLOYMENT_TYPE=PRODUCTION`, compiles SCSS, and runs a database preflight check (DB connectivity, table verification, superuser and xendit system user seeding). At startup, SCSS is compiled via `libsass`, ensuring styles are up to date without needing a build step.

## Environment Configuration

Docker Compose reads `.env` automatically from the project root. Variables referenced in `compose.yaml`:

| Variable | Purpose |
|----------|---------|
| `DB_ENGINE` | SQLAlchemy engine (e.g. `mysql+pymysql`) |
| `DB_NAME` | MySQL database name |
| `DB_USERNAME` | MySQL user |
| `DB_PASS` | MySQL password (also used as `MYSQL_ROOT_PASSWORD`) |
| `SECRET_KEY` | Flask session signing key |
| `NFC_PWD_SECRET` | Seed for NFC tag passwords |
| `XENDIT_API_KEY` | Xendit secret API key |
| `XENDIT_WEBHOOK_TOKEN` | Xendit webhook verification token |
| `SESSION_COOKIE_SECURE` | Whether session cookies require HTTPS (`true` / `false`) |
| `DEBUG` | Enable debug dashboard (`true` / `false`)

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Set `SECRET_KEY` and `NFC_PWD_SECRET` to unique 64-hex-char strings:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Deployment Commands

Start all services:

```bash
docker compose up -d
```

Rebuild the `billserver` image after code changes:

```bash
docker compose up -d --build billserver
```

View logs:

```bash
docker compose logs -f
```

Stop everything:

```bash
docker compose down
```

## Nginx Reverse Proxy

The app is designed to sit behind an nginx reverse proxy. An external Docker network (`reverse-proxy_proxy`) connects the `billserver` container to the nginx instance.

The template at `BillServer/deploy/nginx-billserver.conf` proxies requests under a configurable `__SITE_PREFIX__` path to `http://127.0.0.1:5005/`.

To use it:

1. Pick a site prefix (e.g. `/water-billing-system`).
2. Replace `__SITE_PREFIX__` in the template with your prefix.
3. Include the file in your nginx `server` block:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example.com;

    include /path/to/nginx-billserver.conf;
}
```

4. Set `REVERSE_PROXY_PREFIX` in `.env` to match your prefix, or enable `ProxyFix` mode. See the template comments and `.env.example` for both options.

## Health Check

```bash
curl http://localhost:5005/api/health
```

Response:

```json
{"status": "ok", "db": true}
```

The endpoint checks database connectivity. The `db` field reflects whether the connection succeeded.
