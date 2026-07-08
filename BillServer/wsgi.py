from __future__ import annotations

import os

os.environ["DEPLOYMENT_TYPE"] = "PRODUCTION"

from run import _compile_scss, _preflight_db, app  # noqa: E402

_compile_scss(app)
_preflight_db(app)
