from __future__ import annotations

from flask import Response, jsonify, request

from app import cache, db
from __init__ import blueprint
from utils import resolve_api_key
from pricing import DUE_DAYS, LATE_PENALTY, PRICING_TIERS


@blueprint.route("/health")
def health() -> Response:
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok})


@blueprint.route("/pricing")
@cache.cached(timeout=3600, query_string=True)
def pricing() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403
    return jsonify({
        "tiers": PRICING_TIERS,
        "late_penalty": LATE_PENALTY,
        "due_days": DUE_DAYS,
    })
