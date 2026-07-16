from __future__ import annotations

from datetime import datetime

from flask import Response, jsonify, request

from app import cache, db
from __init__ import blueprint
from utils import resolve_api_key
from models import ApiKey, Customer, ManagementLog, MeterReading
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


@blueprint.route("/key/info")
def api_key_info() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401

    staff = api_key.staff
    return jsonify(
        {
            "api_key": {
                "id": api_key.id,
                "label": api_key.label,
                "is_active": api_key.is_active,
                "date_created": (
                    api_key.date_created.isoformat() if api_key.date_created else None
                ),
            },
            "staff": (
                {
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
                }
                if staff
                else None
            ),
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


# === New sync endpoints ===


@blueprint.route("/customers/changed")
def customers_changed() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

    since = request.args.get("since", type=int)
    if since is None:
        return jsonify({"error": "since parameter is required (Unix timestamp)"}), 400

    try:
        since_dt = datetime.fromtimestamp(since)
    except (ValueError, OSError, OverflowError):
        return jsonify({"error": "Invalid since timestamp"}), 400

    # Customers whose profile was modified
    modified_customers = (
        Customer.query.with_entities(Customer.customer_number)
        .filter(
            Customer.date_modified > since_dt,
            Customer.is_active.is_(True),
        )
        .all()
    )

    # Customers who have new or edited readings since the timestamp
    reading_customers = (
        db.session.query(MeterReading.customer_number.distinct())
        .filter(
            db.or_(
                MeterReading.date_created > since_dt,
                MeterReading.date_modified > since_dt,
            )
        )
        .all()
    )

    # Customers whose readings were dropped since the timestamp
    dropped_logs = (
        ManagementLog.query.with_entities(ManagementLog.customer_number.distinct())
        .filter(
            ManagementLog.date_created > since_dt,
            ManagementLog.action_type.in_(["drop", "edit"]),
            ManagementLog.target_type == "reading",
            ManagementLog.customer_number.isnot(None),
        )
        .all()
    )
    dropped_customers = {r[0] for r in dropped_logs if r[0]}

    # Combine
    all_changed = {c[0] for c in modified_customers}
    all_changed.update(c[0] for c in reading_customers)
    all_changed.update(dropped_customers)

    return jsonify(
        {
            "customer_numbers": list(all_changed),
            "server_time": int(datetime.utcnow().timestamp()),
            "total_customers": Customer.query.filter_by(is_active=True).count(),
        }
    )



