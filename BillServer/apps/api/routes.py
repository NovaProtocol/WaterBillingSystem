from __future__ import annotations

from flask import Response, jsonify

from apps import db
from apps.api import (
    blueprint,
    customer,  # noqa: F401
    nfc,  # noqa: F401
    readings,  # noqa: F401
)


@blueprint.route("/health")
def health() -> Response:
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok})
