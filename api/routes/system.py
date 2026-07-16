from __future__ import annotations

from flask import Response, jsonify

from app import db
from .. import blueprint


@blueprint.route("/health")
def health() -> Response:
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok})
