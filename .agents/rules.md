# Rules

## Deployment environment

- This PC runs on **WSL** — it is NOT the deployment target. Docker used here is local-only for testing.
- Remote (deployment) docker: use `~/Projects/helper_script/docker.sh` **only for reading logs or similar read-only cases**. Never run compose or any deployment-mutating command against remote.
- Local docker on WSL is free to use, but **always delete containers/volumes after testing** — leave the machine as found.

## Commits

- Commit policy is contextual: **if the next request is similar to the last (iterating on the same feature), amend the existing commit; if it's a new/different topic, make a new commit.** Judge each request on whether it continues the previous work or starts something else.
- **Scope beyond the request**: if an edit is requested for a feature but it causes changes on other parts as well, do it anyway **as long as it's an improvement, not a side effect**. (Example: moving header controls into the mobile drawer was requested for staff/dev — applying the same standard to the customer portal is an improvement, so do it.)
- Never push. Only the user pushes to remote and deploys.

## Static assets & templates

- **All static lives in `shared/static/`** — container dirs contain code + templates ONLY, never static files.
- Served at `/static/*` by the **landing-page container** (`static_folder=shared_static_dir()`); Caddy routes `/static/*` → landing-page:8001. All 4 portals use the same app config so `/static/*` also resolves when run standalone (stage-2 tests).
- Layout rules:
  - `shared/static/common/*` — used by 2+ containers (css, vendor, favicon)
  - `shared/static/<container>/*` — container-specific (e.g. `staff/js/`, `customer/js/`, `dev/js/`, `landing/img/`, `landing/video/`)
  - Single-container vendor libs live under that container's folder (e.g. `staff/vendor/qrcodejs`, `landing/vendor/photo-sphere-viewer`)
- Templates reference assets with **hardcoded absolute paths** (`/static/common/css/cotta.css`) — no `url_for('static', ...)`.
- JS logic goes in files under `shared/static/<container>/js/`; only tiny inline config vars (e.g. `window.DEV_URLS = {...}` with `url_for` values) stay in templates.
- Landing's model photo scanner (`routes.py` `_IMAGE_DIR`) resolves via `shared_static_dir()`.

## Shared portal shell

- **All 3 portals (staff/dev/customer) extend `shared/templates/common/base.html`** — one shell: head, navbar (`portal_label`, `brand_url`, `nav_right` blocks), sidebar (`sidebar_items` block), content, footer, scripts. Maximize common theme: a single edit in the shell affects all portals.
- Per-portal `base.html` files are thin (`{% extends "common/base.html" %}` + nav items); pages extend the per-portal base.
- `main-content` gets `.no-sidebar` when `sidebar_items` renders empty — login pages empty `{% block sidebar %}`.
- Wiring: `shared_templates_dir()` in shared/config.py + `ChoiceLoader` (portal templates first) in staff/dev/customer app.py. Landing is NOT part of the shell.
- Auth/error cards use the `.auth-card` component in cotta.css.
- Customer portal sections (Billing / Maintenance Request / Report an Issue) are sidebar entries; scaffold pages are cookie-gated via `load_session()`.

## Testing

- Stage-1 unit tests run in docker: mount repo + tests venv site-packages, run per-portal (never multiple portal dirs in one pytest run — both import a module named `app` and collide).
- Browser checks: `tests/.venv/bin/python` + playwright against a smoke compose stack (`/tmp/opencode/compose.smoke.yaml` — fresh DB volume, ports 9101/9102). Landing/portal static served through the same compose stack.
- After testing: `docker compose -f compose.yaml -f /tmp/opencode/compose.smoke.yaml down -v`, verify no leftover containers.
- `pkill -f` self-matches the shell command — use bracket patterns like `pkill -f "browser_check[.]py"`.

## Local testing freedom (user-approved)

- Full freedom with local docker for testing (throwaway containers, runtime pip installs, bridge networks, any hack) as long as the **final product** is right and the **deployment server is never touched** unless explicitly told.
- Keep the WSL filesystem tidy: scratch files go in `/tmp/opencode`; avoid scattering extra files in the repo or home dir unless necessary.
