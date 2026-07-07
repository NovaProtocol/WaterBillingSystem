from __future__ import annotations

import os

os.environ["DEPLOYMENT_TYPE"] = "PRODUCTION"

from run import _preflight_db, app  # noqa: E402

_preflight_db(app)
