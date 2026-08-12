# Project — WaterBillingSystem

## Remote Server

The production server uses a **git-based deploy** workflow:

1. Changes are committed locally
2. User pushes (`git push`)
3. The server has a hook that **automatically pulls and redeploys** on push

So the deploy flow is: `git commit` → user runs `git push` → server redeploys.

**Only the user can push.** The agent must never run `git push` — always ask the user to push when ready.

## Remote Docker Commands

The `.agents/scripts/docker.sh` script lets you run read-only Docker commands on the production server via SSH:

```bash
# List containers
bash .agents/scripts/docker.sh ps

# View logs
bash .agents/scripts/docker.sh logs waterbillingsystem_worker --tail 50

# Inspect a container
bash .agents/scripts/docker.sh inspect waterbillingsystem_db

# Execute a command inside a running container
bash .agents/scripts/docker.sh exec waterbillingsystem_worker python -c "print('hello')"
```

The script uses an SSH host called `agent-access`. See `.agents/scripts/README.md` for one-time setup.

## Environment Variables

The `.env` file is **gitignored** and **never committed** by the agent or pushed to git. When provisioning or updating the server, the **developer manually copies** `.env` contents to the server. The agent never touches `.env` on the remote server — that's the developer's job. Any change to `.env` requires the stack to be rebuilt and restarted (`docker compose up -d --build`).

### phpMyAdmin Config

phpMyAdmin session cookies behind the proxy require:
- `PMA_CONFIG_BASE64` in `.env` — base64-encoded PHP config that sets:
  ```php
  $cfg["ForceSSL"] = false;
  ini_set("session.cookie_secure", "0");
  ```
  The compose.yaml passes this as an environment variable to the phpmyadmin container.

## Commit Style

Follow conventional commits. Format:

```
type(scope): short description in lowercase, no period

Optional narrative body explaining why the change was made.
Wrap at 72 characters. Use plain English.

- Bullet points for listing specific changes
- Each bullet is a complete thought
```

Types: `fix`, `feat`, `chore`, `refactor`, `test`, `docs`, `style`.

Scope is the component or area affected (e.g. `phpmyadmin`, `api`, `staff-portal`).

Examples from this repo:
```
fix(phpmyadmin): make session cookies work when proxied behind a path prefix
chore: untrack workspace file and add *.code-workspace to .gitignore
```

## .agents directory

The entire `.agents/` directory is **gitignored** (`.*` pattern in `.gitignore`). Files here are local-only and not persisted in git. Keep backups if needed.
