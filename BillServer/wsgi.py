from __future__ import annotations

import os

os.environ["DEPLOYMENT_TYPE"] = "PRODUCTION"

from run import _compile_scss, _ensure_prerequisites, app  # noqa: E402

_compile_scss(app)
_ensure_prerequisites(app)

from apps.services.scheduler import start_scheduler
start_scheduler(app)
