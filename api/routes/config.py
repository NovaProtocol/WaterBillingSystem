from __future__ import annotations

from flask import Response, current_app, jsonify, request

from app import cache, db
from blueprint import blueprint
from utils import require_staff, resolve_api_key
from models import Config as AppConfig
from pricing import DUE_DAYS, LATE_PENALTY, PRICING_TIERS


@blueprint.route("/config/nfc_secret")
def config_nfc_secret() -> Response:
    api_key = resolve_api_key()
    if not api_key or not api_key.is_active:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not (
        api_key.staff.can_read_meters or api_key.staff.can_enroll_customer
    ):
        return jsonify({"error": "Permission denied"}), 403

    gen_row = AppConfig.query.filter_by(key="nfc_generation").first()
    generation = int(gen_row.value) if gen_row else 0

    return jsonify({
        "nfc_pwd_secret": current_app.config["NFC_PWD_SECRET"],
        "nfc_generation": generation,
    })


@blueprint.route("/config/pricing")
@cache.cached(timeout=3600, query_string=True)
def config_pricing() -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
    return jsonify({
        "tiers": PRICING_TIERS,
        "late_penalty": LATE_PENALTY,
        "due_days": DUE_DAYS,
    })
