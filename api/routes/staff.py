from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from flask import Response, jsonify, request
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from blueprint import blueprint
from models import ApiKey, Billing, Config, Customer, ManagementLog, MeterReading, NfcTag, Staff
from billing_service import ensure_penalty
from customer_service import (
    create_customer,
    get_customer_by_number,
    get_customer_or_404,
    list_customers,
    toggle_active,
    update_customer,
)
from services.payment_service import (
    compute_cashier_tally,
    compute_nav_dates,
    drop_payment as service_drop_payment,
    parse_date_range,
    recalc_cumulative_balance,
    submit_payment as service_submit_payment,
)
from reading_service import (
    drop_reading as service_drop_reading,
    edit_reading as service_edit_reading,
)
from utils import _get_staff_id, require_staff, resolve_api_key
from pricing import compute_water_bill


@blueprint.route("/staff/login", methods=["POST"])
def staff_login() -> Response:
    data = request.get_json()
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    staff = Staff.query.filter_by(username=username).first()
    if not staff or not staff.is_active:
        return jsonify({"error": "Invalid credentials"}), 401
    pw_str = staff.password.decode("utf-8", errors="replace")
    if "$" in pw_str:
        if not check_password_hash(pw_str, password):
            return jsonify({"error": "Invalid credentials"}), 401
    else:
        import binascii, hashlib
        try:
            stored = pw_str
            salt = stored[:64]
            pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt.encode("ascii"), 100000)
            if binascii.hexlify(pwdhash).decode("ascii") != stored[64:]:
                return jsonify({"error": "Invalid credentials"}), 401
        except (ValueError, UnicodeDecodeError, IndexError):
            return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({
        "id": staff.id,
        "username": staff.username,
        "name": staff.name,
        "email": staff.email,
        "contact_number": staff.contact_number,
        "is_active": staff.is_active,
        "can_read_meters": staff.can_read_meters,
        "can_accept_payment": staff.can_accept_payment,
        "can_enroll_customer": staff.can_enroll_customer,
        "can_drop_reading": staff.can_drop_reading,
        "can_drop_payment": staff.can_drop_payment,
        "can_enroll_staff": staff.can_enroll_staff,
        "can_manage_billing": staff.can_manage_billing,
    })


def _staff_to_dict(staff: Staff) -> dict:
    return {
        "id": staff.id,
        "username": staff.username,
        "name": staff.name,
        "email": staff.email,
        "contact_number": staff.contact_number,
        "is_active": staff.is_active,
        "can_read_meters": staff.can_read_meters,
        "can_accept_payment": staff.can_accept_payment,
        "can_enroll_customer": staff.can_enroll_customer,
        "can_drop_reading": staff.can_drop_reading,
        "can_drop_payment": staff.can_drop_payment,
        "can_enroll_staff": staff.can_enroll_staff,
        "can_manage_billing": staff.can_manage_billing,
    }


@blueprint.route("/staff/info")
def staff_info() -> Response:
    auth = require_staff()
    if auth[1]:
        return auth[1]
    api_key = auth[0]

    if api_key is True:
        staff_id = _get_staff_id()
        if not staff_id:
            return jsonify({"error": "staff_id required via X-Staff-ID header or request body"}), 400
        staff = Staff.query.get(staff_id)
        if not staff:
            return jsonify({"error": "Staff not found"}), 404
    else:
        staff = api_key.staff
        if not staff:
            return jsonify({"error": "Staff not found"}), 404

    return jsonify({
        "staff": _staff_to_dict(staff),
        "auth_type": "internal_key" if api_key is True else "api_key",
        "api_key": {
            "id": api_key.id,
            "label": api_key.label,
            "is_active": api_key.is_active,
        } if api_key is not True else None,
    })


@blueprint.route("/staff/all")
def staff_all() -> Response:
    api_key, err = require_staff("can_enroll_staff")
    if err:
        return err
    staff_list = Staff.query.all()
    return jsonify({
        "staff": [
            {
                "id": s.id,
                "username": s.username,
                "name": s.name,
                "email": s.email,
                "contact_number": s.contact_number,
                "is_active": s.is_active,
                "can_read_meters": s.can_read_meters,
                "can_accept_payment": s.can_accept_payment,
                "can_enroll_customer": s.can_enroll_customer,
                "can_drop_reading": s.can_drop_reading,
                "can_drop_payment": s.can_drop_payment,
                "can_enroll_staff": s.can_enroll_staff,
                "can_manage_billing": s.can_manage_billing,
            }
            for s in staff_list
        ]
    })


@blueprint.route("/staff/<int:staff_id>")
def staff_get(staff_id: int) -> Response:
    api_key, err = require_staff("can_enroll_staff")
    if err:
        return err
    staff = Staff.query.get_or_404(staff_id)
    return jsonify({
        "id": staff.id,
        "username": staff.username,
        "name": staff.name,
        "email": staff.email,
        "contact_number": staff.contact_number,
        "is_active": staff.is_active,
        "can_read_meters": staff.can_read_meters,
        "can_accept_payment": staff.can_accept_payment,
        "can_enroll_customer": staff.can_enroll_customer,
        "can_drop_reading": staff.can_drop_reading,
        "can_drop_payment": staff.can_drop_payment,
        "can_enroll_staff": staff.can_enroll_staff,
        "can_manage_billing": staff.can_manage_billing,
    })


@blueprint.route("/staff/new", methods=["POST"])
def staff_new() -> Response:
    api_key, err = require_staff("can_enroll_staff")
    if err:
        return err
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if Staff.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409
    staff = Staff(
        username=username,
        name=data.get("name", "").strip() or username,
        password=generate_password_hash(password).encode("utf-8"),
        email=data.get("email", "").strip() or None,
        contact_number=data.get("contact_number", "").strip() or None,
        can_read_meters=data.get("can_read_meters", False),
        can_accept_payment=data.get("can_accept_payment", False),
        can_enroll_customer=data.get("can_enroll_customer", False),
        can_drop_reading=data.get("can_drop_reading", False),
        can_drop_payment=data.get("can_drop_payment", False),
        can_enroll_staff=data.get("can_enroll_staff", False),
        can_manage_billing=data.get("can_manage_billing", False),
    )
    db.session.add(staff)
    db.session.commit()
    return jsonify({"message": "Staff created", "username": staff.username, "name": staff.name}), 201


@blueprint.route("/staff/<int:staff_id>/edit", methods=["POST"])
def staff_edit(staff_id: int) -> Response:
    api_key, err = require_staff("can_enroll_staff")
    if err:
        return err
    data = request.get_json() or {}
    staff = Staff.query.get_or_404(staff_id)
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Username is required"}), 400
    existing = Staff.query.filter(Staff.username == username, Staff.id != staff_id).first()
    if existing:
        return jsonify({"error": "Username already exists"}), 409
    staff.username = username
    staff.name = data.get("name", "").strip() or username
    password = data.get("password", "")
    if password:
        staff.password = generate_password_hash(password).encode("utf-8")
    staff.email = data.get("email", "").strip() or None
    staff.contact_number = data.get("contact_number", "").strip() or None
    staff.can_read_meters = data.get("can_read_meters", False)
    staff.can_accept_payment = data.get("can_accept_payment", False)
    staff.can_enroll_customer = data.get("can_enroll_customer", False)
    staff.can_drop_reading = data.get("can_drop_reading", False)
    staff.can_drop_payment = data.get("can_drop_payment", False)
    staff.can_enroll_staff = data.get("can_enroll_staff", False)
    staff.can_manage_billing = data.get("can_manage_billing", False)
    staff.is_active = data.get("is_active", True)
    db.session.commit()
    return jsonify({"message": "Staff updated", "username": staff.username, "name": staff.name})


@blueprint.route("/staff/<int:staff_id>/cashier-tally")
def staff_cashier_tally(staff_id: int) -> Response:
    api_key, err = require_staff("can_accept_payment")
    if err:
        return err
    period = request.args.get("period", "daily")
    today = datetime.utcnow()
    start_str = request.args.get("start_date") or request.args.get("date")
    end_str = request.args.get("end_date")
    group_days = request.args.get("group_days", 1, type=int)
    start, end = parse_date_range(period, start_str, end_str, today)
    tally, use_matrix = compute_cashier_tally(start, end, staff_id, group_days)
    nav = compute_nav_dates(period, start, end, today)
    return jsonify({
        "tally": tally,
        "use_matrix": use_matrix,
        "nav_date": nav.get("nav_date"),
        "group_days": group_days,
        "start_date": start.strftime("%Y-%m-%d") if start else "",
        "end_date": end.strftime("%Y-%m-%d") if end else "",
        "display": nav["display"],
        "prev_date": nav["prev_date"],
        "next_date": nav["next_date"],
        "is_today": nav["is_today"],
        "period": period,
    })


@blueprint.route("/staff/<int:staff_id>/reading-logs")
def staff_reading_logs(staff_id: int) -> Response:
    api_key, err = require_staff("can_drop_reading")
    if err:
        return err
    logs = (
        ManagementLog.query.filter_by(target_type="reading")
        .order_by(desc(ManagementLog.timestamp))
        .limit(50)
        .all()
    )
    return jsonify({
        "logs": [
            {
                "id": log.id,
                "staff_id": log.staff_id,
                "staff_name": log.staff.name if log.staff else None,
                "action_type": log.action_type,
                "target_id": log.target_id,
                "customer_number": log.customer_number,
                "details": log.details,
                "timestamp": int(log.timestamp.timestamp()) if log.timestamp else 0,
            }
            for log in logs
        ]
    })


@blueprint.route("/staff/<int:staff_id>/api-keys")
def staff_api_keys(staff_id: int) -> Response:
    api_key, err = require_staff()
    if err:
        return err
    keys = (
        ApiKey.query
        .options(joinedload(ApiKey.staff))
        .order_by(desc(ApiKey.date_created))
        .all()
    )
    return jsonify({
        "keys": [
            {
                "id": k.id,
                "key": k.key,
                "label": k.label,
                "is_active": k.is_active,
                "staff_id": k.staff_id,
                "staff_name": k.staff.name if k.staff else None,
                "date_created": k.date_created.isoformat() if k.date_created else None,
            }
            for k in keys
        ]
    })


@blueprint.route("/staff/<int:staff_id>/api-key/generate", methods=["POST"])
def staff_api_key_generate(staff_id: int) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
    data = request.get_json()
    label = ((data or {}).get("label", "") or "").strip() or None
    staff = Staff.query.get(staff_id)
    if not staff:
        return jsonify({"error": "Staff not found"}), 404
    key = "CRDC-" + secrets.token_hex(16).upper()
    new_key = ApiKey(key=key, label=label, staff_id=staff_id)
    db.session.add(new_key)
    db.session.commit()
    return jsonify({"key": key, "label": label, "id": new_key.id}), 201


@blueprint.route("/staff/<int:staff_id>/api-key/<int:key_id>/revoke", methods=["POST"])
def staff_api_key_revoke(staff_id: int, key_id: int) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
    target = ApiKey.query.get_or_404(key_id)
    target.is_active = False
    db.session.commit()
    return jsonify({"message": "Key revoked"})


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
