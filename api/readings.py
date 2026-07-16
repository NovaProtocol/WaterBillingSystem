from __future__ import annotations

from datetime import datetime

from flask import Response, jsonify, request
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from app import cache, db
from __init__ import blueprint
from utils import resolve_api_key
from models import ApiKey, Customer, ManagementLog, MeterReading, NfcTag
from pricing import DUE_DAYS, LATE_PENALTY, PRICING_TIERS
from reading_service import (
    drop_reading as service_drop_reading,
    edit_reading as service_edit_reading,
    sync_readings,
    upload_reading,
)


@blueprint.route("/readings/customer/<customer_number>")
def readings_customer_reference(customer_number: str) -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    last = (
        MeterReading.query
        .options(
            joinedload(MeterReading.token).joinedload(ApiKey.staff)
        )
        .filter_by(customer_number=customer_number)
        .order_by(desc(MeterReading.timestamp))
        .first()
    )

    return jsonify(
        {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address,
            "contact_number": customer.contact_number,
            "phase": customer.phase,
            "block": customer.block,
            "street": customer.street,
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
            "max_meter_value": float(customer.max_meter_value or 99999),
            "last_reading_value": float(last.reading_value) if last else None,
            "last_reading_timestamp": int(last.timestamp.timestamp()) if last else None,
            "last_reading_reader": last.token.staff.name if last and last.token and last.token.staff else None,
        }
    )


@blueprint.route("/readings/sync", methods=["POST"])
def readings_sync() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401

    staff = api_key.staff
    token_id = api_key.id
    staff_id = staff.id
    if not staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403
    if staff_id is None:
        return jsonify({"error": "API key has no associated staff member"}), 400

    data = request.get_json()
    if not data or "readings" not in data:
        return jsonify({"error": "Request body must contain a readings array"}), 400

    readings = data["readings"]
    if not isinstance(readings, list):
        return jsonify({"error": "readings must be an array"}), 400

    staff_name = staff.name or "Unknown"
    synced, results, errors = sync_readings(readings, token_id, staff_id, staff_name)

    return jsonify(
        {
            "synced": synced,
            "total": len(readings),
            "results": results,
            "errors": errors,
        }
    )


@blueprint.route("/readings/upload", methods=["POST"])
def readings_upload() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401

    staff = api_key.staff
    token_id = api_key.id
    staff_id = staff.id
    if not staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    customer_number = data.get("customer_number", "").strip()
    reading_value = data.get("reading_value")
    timestamp = data.get("timestamp", datetime.utcnow().timestamp())

    if not customer_number:
        return jsonify({"error": "customer_number is required"}), 400
    if reading_value is None:
        return jsonify({"error": "reading_value is required"}), 400

    staff_name = staff.name or "Unknown"
    try:
        reading_float = float(reading_value)
        ts_float = float(timestamp)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid reading_value or timestamp"}), 400
    reading, error, status = upload_reading(
        customer_number, reading_float, ts_float, token_id, staff_id, staff_name
    )
    if error:
        return jsonify({"error": error}), status

    return (
        jsonify(
            {
                "success": True,
                "reading_id": reading.id,
                "customer_number": customer_number,
                "reading_value": float(reading_value),
                "timestamp": int(timestamp),
                "reader": staff.name,
            }
        ),
        201,
    )


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


@blueprint.route("/readings/bulk")
def readings_bulk() -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

    customer_numbers_param = request.args.get("customer_numbers", "")
    cust_list = [c.strip() for c in customer_numbers_param.split(",") if c.strip()]
    if len(cust_list) > 5000:
        return jsonify({"error": "Too many customer numbers (max 5000)"}), 400
    limit = request.args.get("limit", 0, type=int)

    if not cust_list:
        return jsonify({"error": "customer_numbers parameter is required"}), 400

    # Single query for all customers
    customers = Customer.query.filter(
        Customer.customer_number.in_(cust_list)
    ).all()

    # Single query for all readings for these customers
    all_readings = (
        MeterReading.query
        .options(
            joinedload(MeterReading.token).joinedload(ApiKey.staff)
        )
        .filter(
            MeterReading.customer_number.in_(cust_list)
        )
        .order_by(MeterReading.timestamp.desc())
        .all()
    )

    # Group readings by customer, capping at limit if set
    readings_by_customer: dict[str, list] = {cn: [] for cn in cust_list}
    for r in all_readings:
        group = readings_by_customer[r.customer_number]
        if limit and len(group) >= limit:
            continue
        group.append(
            {
                "id": r.id,
                "reading_value": float(r.reading_value),
                "reader": r.token.staff.name if r.token and r.token.staff else None,
                "timestamp": int(r.timestamp.timestamp()),
            }
        )

    # Build nfc_uid lookup: customer_number -> uid
    nfc_tags = NfcTag.query.filter(NfcTag.customer_number.in_(cust_list)).all()
    nfc_by_customer: dict[str, str] = {
        t.customer_number: t.uid for t in nfc_tags
    }

    # Build response
    result = {}
    for c in customers:
        result[c.customer_number] = {
            "customer": {
                "customer_number": c.customer_number,
                "name": c.name,
                "address": c.address,
                "contact_number": c.contact_number,
                "phase": c.phase,
                "block": c.block,
                "street": c.street,
                "x_coordinate": c.x_coordinate,
                "y_coordinate": c.y_coordinate,
                "max_meter_value": float(c.max_meter_value or 99999),
                "nfc_uid": nfc_by_customer.get(c.customer_number),
            },
            "readings": readings_by_customer.get(c.customer_number, []),
        }

    return jsonify({"customers": result})


@blueprint.route("/customer/<customer_number>/reading")
def customer_readings(customer_number: str) -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 50, type=int)
    pagination = (
        MeterReading.query
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .filter_by(customer_number=customer_number)
        .order_by(desc(MeterReading.timestamp))
        .paginate(page=page, per_page=size, error_out=False)
    )
    items = [
        {
            "id": r.id,
            "reading_value": float(r.reading_value),
            "reader": r.token.staff.name if r.token and r.token.staff else None,
            "timestamp": int(r.timestamp.timestamp()),
        }
        for r in pagination.items
    ]
    return jsonify({
        "data": items,
        "meta": {
            "current_page": pagination.page,
            "page_size": pagination.per_page,
            "total_items": pagination.total,
            "total_pages": pagination.pages,
        },
    })


@blueprint.route("/customer/<customer_number>/reading/drop", methods=["POST"])
def customer_reading_drop(customer_number: str) -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_drop_reading:
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json() or {}
    reading_id = data.get("reading_id")
    reason = data.get("reason", "").strip()
    if not reading_id:
        return jsonify({"error": "reading_id is required"}), 400
    if not reason:
        return jsonify({"error": "Reason is required"}), 400
    try:
        service_drop_reading(reading_id, api_key.staff.id, reason)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"message": "Reading dropped"})


@blueprint.route("/customer/<customer_number>/reading/edit", methods=["POST"])
def customer_reading_edit(customer_number: str) -> Response:
    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_manage_billing:
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json() or {}
    reading_id = data.get("reading_id")
    try:
        new_value = float(data.get("reading_value", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid reading value"}), 400
    if not reading_id:
        return jsonify({"error": "reading_id is required"}), 400
    service_edit_reading(reading_id, new_value, api_key.staff.id)
    return jsonify({"message": "Reading updated"})
