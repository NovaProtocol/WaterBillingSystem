from __future__ import annotations

import logging
from flask import Response, jsonify

from app import db
from blueprint import blueprint

logger = logging.getLogger('api')


@blueprint.route("/health")
def health() -> Response:
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Health check DB query failed:")
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok})
