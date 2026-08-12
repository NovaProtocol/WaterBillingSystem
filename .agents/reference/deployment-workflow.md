# Deployment Workflow

**ABSOLUTE RULES — never violate these.**

## Workflow

1. **Local changes** — edit code, test locally
2. **Commit** — agent commits to `main`
3. **User pushes** — only the user pushes to remote (`git push`)
4. **Auto-deploy** — remote server auto-deploys on push (git hook / CI)
5. **User tells agent** — user confirms "ok run the command" before any remote command

## Never

- NEVER run `docker compose up`, `docker compose build`, `docker compose down`, or any compose lifecycle command
- NEVER `docker compose run` — creates temp containers that don't exist in the running stack
- NEVER modify files inside a running container with `sed`, `vi`, or similar
- NEVER exec into a container to edit code — the image is immutable after build

## Allowed remote commands

Only `docker exec` + `docker compose exec` against **already running** containers:

```bash
bash .agents/scripts/docker.sh exec <container> <command>
```

Valid container names:
| Container | Purpose |
|-----------|---------|
| `waterbillingsystem_gateway` | Caddy reverse proxy |
| `waterbillingsystem_landing` | Landing page |
| `waterbillingsystem_customerportal` | Customer portal |
| `waterbillingsystem_staffportal` | Staff portal |
| `waterbillingsystem_devportal` | Developer portal |
| `waterbillingsystem_documentation` | Documentation (MkDocs static site) |
| `waterbillingsystem_api` | REST API |
| `waterbillingsystem_worker` | Background worker |
| `waterbillingsystem_phpmyadmin` | phpMyAdmin |
| `waterbillingsystem_db` | MySQL 8.4 database |

All containers have explicit `container_name:` fields in compose.yaml, so no auto-generated names are used.

Examples:
```bash
# Run Python code on the API container
bash .agents/scripts/docker.sh exec waterbillingsystem_api python -c "from app import db; ..."

# Check worker logs
bash .agents/scripts/docker.sh logs waterbillingsystem_worker --tail 50

# Execute on worker
bash .agents/scripts/docker.sh exec waterbillingsystem_worker python -c "print('hello')"
```

## GateKeeper Authentication (Caddy gate)

Auth lives in the Caddy gateway, not the apps. Each site block runs
`forward_auth gatekeeper:7000 { uri /api/authz/forward-auth }` on every handle
except `/webhook/*`, `/health`, and `/404`. The `caddy-gateway` container is the
only one on the `net-gk` network (`gatekeeper_default`). Do not re-add app-level
gatekeeper middleware.

## Database Migrations

This project does NOT use Alembic/Flask-Migrate. Schema changes are handled via:
1. **`db.create_all()`** — runs on API startup in `create_app()` (creates all tables from models)
2. **`api/migrate.py`** — manual migration script for column additions (e.g., `meter_serial_number` column)
3. The `run_migrations()` function is called on startup after `db.create_all()` to apply any pending ALTER TABLE statements

## Scripts

```bash
# Remote docker commands via SSH
bash .agents/scripts/docker.sh ps
bash .agents/scripts/docker.sh logs waterbillingsystem_worker --tail 100
bash .agents/scripts/docker.sh inspect waterbillingsystem_db
```

See `.agents/scripts/README.md` for setup instructions (SSH config for `agent-access`).
