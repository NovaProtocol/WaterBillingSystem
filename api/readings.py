from __future__ import annotations

from flask import Response, jsonify, request

from app import cache
from __init__ import blueprint
from utils import resolve_api_key
from models import ApiKey
from pricing import DUE_DAYS, LATE_PENALTY, PRICING_TIERS


@blueprint.route("/pricing")
@cache.cached(timeout=3600, query_string=True)
def pricing() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403
    return jsonify(
        {
            "tiers": PRICING_TIERS,
            "late_penalty": LATE_PENALTY,
            "due_days": DUE_DAYS,
        }
    )


@blueprint.route("/staff/<staff_id>/api-key/verify", methods=["POST"])
def staff_api_key_verify(staff_id: int) -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    verify_key = data.get("api_key", "").strip()
    if not verify_key:
        return jsonify({"error": "api_key is required"}), 400

    target = ApiKey.query.filter_by(key=verify_key, is_active=True).first()
    if not target:
        return jsonify({"error": "Invalid or revoked API key"}), 404

    staff = target.staff
    return jsonify({
        "valid": True,
        "api_key": {
            "id": target.id,
            "label": target.label,
            "staff_id": target.staff_id,
            "is_active": target.is_active,
        },
        "staff": {
            "id": staff.id,
            "username": staff.username,
            "name": staff.name,
            "can_read_meters": staff.can_read_meters,
            "can_accept_payment": staff.can_accept_payment,
            "can_enroll_customer": staff.can_enroll_customer,
            "can_drop_reading": staff.can_drop_reading,
            "can_drop_payment": staff.can_drop_payment,
            "can_enroll_staff": staff.can_enroll_staff,
            "can_manage_billing": staff.can_manage_billing,
        } if staff else None,
    })




