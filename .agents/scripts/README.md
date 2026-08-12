# Agent Scripts

Scripts for remote operations. All target the production server via SSH.

> **⚠️ Not persisted in git.** The `.agents/` directory is gitignored (matched by `.*`).
> These files exist only on disk. A fresh clone or redeploy from git will NOT include them.
> Keep a backup if you customize these scripts.

## docker.sh

Run any `docker` command on the remote server.

```bash
bash .agents/scripts/docker.sh ps
bash .agents/scripts/docker.sh logs waterbillingsystem_worker --tail 50
bash .agents/scripts/docker.sh logs waterbillingsystem_main --tail 100
bash .agents/scripts/docker.sh inspect waterbillingsystem_main
bash .agents/scripts/docker.sh exec waterbillingsystem_main python -c "from apps.models import BackgroundTask; print([(t.task_type, t.status) for t in BackgroundTask.query.all()])"
```

The script uses SSH config host `agent-access`. Set it up:

```bash
# One-time setup:
ssh-keygen -t ed25519 -f ~/.ssh/agent-access
ssh-copy-id -i ~/.ssh/agent-access user@server

# Add to ~/.ssh/config:
echo 'Host agent-access
    HostName server
    User user
    IdentityFile ~/.ssh/agent-access' >> ~/.ssh/config
```

## Permissions for AI Agents

When using these scripts, AI agents are restricted to:

**Allowed (read-only):**
- `ps` — list containers
- `logs` — view container logs
- `inspect` — inspect container config
- `stats` — resource usage
- `top` — processes inside container

**Allowed only with human approval:**
- `restart` — restart a container
- `stop` / `start` — stop/start containers
- `exec` — run commands inside a container

**NEVER allowed without explicit human permission:**
- `compose up / down / restart` — manage the entire stack
- `compose build` — rebuild images
- Any command that modifies running containers, volumes, networks, or images
- Any command that could cause data loss or service disruption
```
