from __future__ import annotations

import secrets

from flask import Response, jsonify, request
from flask_login import current_user

from apps import db
from apps.models import ApiKey, Customer
from apps.staff import blueprint


@blueprint.route("/customer-lookup")
def customer_lookup() -> Response:
    if not current_user.is_authenticated or not current_user.can_read_meters:
        return jsonify({"error": "Unauthorized"}), 403
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify([])
    customers = (
        Customer.query.filter(
            Customer.customer_number.like(f"%{q}%") | Customer.name.like(f"%{q}%")
        )
        .limit(10)
        .all()
    )
    return jsonify(
        [
            {
                "customer_number": c.customer_number,
                "name": c.name,
                "address": c.address,
            }
            for c in customers
        ]
    )


@blueprint.route("/meter-reading/generate", methods=["POST"])
def generate_api_key() -> Response:
    if not current_user.is_authenticated or not current_user.can_read_meters:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    label = data.get("label", "").strip() or None
    key = "CRDC-" + secrets.token_hex(16).upper()
    api_key = ApiKey(key=key, label=label, staff_id=current_user.id)
    db.session.add(api_key)
    db.session.commit()
    return jsonify({"key": key, "label": label, "id": api_key.id}), 201


@blueprint.route("/meter-reading/revoke/<int:key_id>", methods=["POST"])
def revoke_api_key(key_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_read_meters:
        return jsonify({"error": "Unauthorized"}), 403
    api_key = ApiKey.query.get_or_404(key_id)
    if not current_user.can_drop_reading and api_key.staff_id != current_user.id:
        return jsonify({"error": "You can only revoke your own keys"}), 403
    api_key.is_active = False
    db.session.commit()
    return jsonify({"message": "Key revoked"})
