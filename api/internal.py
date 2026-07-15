from __future__ import annotations

import os
import secrets
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from models import (
    ApiKey,
    BackgroundTask,
    Billing,
    Config,
    Customer,
    ManagementLog,
    MeterReading,
    NfcTag,
    Staff,
    XenditTransaction,
)
from pricing import PRICING_TIERS, compute_water_bill
from services.billing_service import ensure_penalty
from services.customer_service import (
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
from services.reading_service import (
    drop_reading as service_drop_reading,
    edit_reading as service_edit_reading,
)


api_internal_bp = Blueprint("api_internal", __name__, url_prefix="/api/internal")

BACKUP_DIR = Path("/app/db_backups")


def require_internal_key(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        auth = request.headers.get("Authorization", "")
        expected = os.environ.get("INTERNAL_API_KEY", "")
        if not auth.startswith("Bearer ") or auth[7:] != expected:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ── Customer endpoints ──────────────────────────────────────────────────


@api_internal_bp.route("/customer/verify", methods=["POST"])
@require_internal_key
def customer_verify() -> Response:
    data = request.get_json() or {}
    account_number = data.get("account_number", "").strip()
    registered_name = data.get("registered_name", "").strip()
    last_receipt = data.get("last_receipt", "").strip()

    if not account_number:
        return jsonify({"error": "Customer number is required", "error_code": "CUS400"}), 400

    customer = Customer.query.filter_by(customer_number=account_number, is_active=True).first()
    if not customer:
        return jsonify({"error": "Customer not found", "error_code": "CUS404"}), 404

    if registered_name and customer.name.lower().strip() != registered_name.lower().strip():
        return jsonify({"error": "Name does not match", "error_code": "CUS403"}), 403

    return jsonify({
        "customer_number": customer.customer_number,
        "customer": {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address or "",
            "contact_number": customer.contact_number or "",
            "email": customer.email or "",
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
        }
    })


@api_internal_bp.route("/customer/<customer_number>/billing")
@require_internal_key
def customer_billing(customer_number: str) -> Response:
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    unpaid_bills = Billing.query.filter_by(customer_number=customer_number, is_paid=False).order_by(Billing.date_created.asc()).all()
    for b in unpaid_bills:
        ensure_penalty(b)

    total_unpaid = sum(float(b.billed_amount or 0) for b in unpaid_bills)
    total_penalties = sum(float(b.penalty or 0) for b in unpaid_bills)
    total_carryover = float(
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar() or 0
    )
    total_due = max(0, total_unpaid + total_penalties - total_carryover)

    return jsonify({
        "customer_number": customer.customer_number,
        "name": customer.name,
        "total_unpaid": round(total_unpaid, 2),
        "total_penalties": round(total_penalties, 2),
        "total_due": round(total_due, 2),
        "cumulative_balance": float(customer.cumulative_balance or 0),
    })


@api_internal_bp.route("/customer/<customer_number>/readings")
@require_internal_key
def customer_readings(customer_number: str) -> Response:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    pagination = (
        MeterReading.query
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .filter_by(customer_number=customer_number)
        .order_by(desc(MeterReading.timestamp))
        .paginate(page=page, per_page=per_page, error_out=False)
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
        "items": items,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    })


@api_internal_bp.route("/customer/<customer_number>/payments")
@require_internal_key
def customer_payments(customer_number: str) -> Response:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    base = Billing.query.filter_by(customer_number=customer_number, is_paid=True)
    total = base.count()
    items = (
        base.order_by(desc(Billing.payment_timestamp))
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )
    return jsonify({
        "items": [
            {
                "id": b.id,
                "receipt_number": b.receipt_number,
                "paid_amount": float(b.paid_amount),
                "cashier_id": b.cashier_id,
                "cashier": (b.cashier.name or b.cashier.username) if b.cashier else None,
                "timestamp": int(b.payment_timestamp.timestamp()) if b.payment_timestamp else 0,
            }
            for b in items
        ],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


@api_internal_bp.route("/customer/<customer_number>/history")
@require_internal_key
def customer_history(customer_number: str) -> Response:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 12, type=int)

    readings = (
        MeterReading.query.filter_by(customer_number=customer_number)
        .order_by(MeterReading.timestamp.asc())
        .all()
    )
    items = []
    for i in range(1, len(readings)):
        prev = readings[i - 1]
        curr = readings[i]
        consumption = float(round(float(curr.reading_value) - float(prev.reading_value), 2))
        billing = Billing.query.filter_by(reading_id=curr.id).first()
        month_label = curr.timestamp.strftime("%B %Y")
        month_key = curr.timestamp.strftime("%Y-%m")
        if billing:
            ensure_penalty(billing)
            billed_amount = round(float(billing.billed_amount), 2)
            penalty = float(billing.penalty)
            paid_amount = float(billing.paid_amount) if billing.is_paid else None
        else:
            billed_amount, _ = compute_water_bill(consumption)
            penalty = 0.0
            paid_amount = None
        items.append({
            "month": month_label,
            "month_key": month_key,
            "usage": consumption,
            "billed_amount": billed_amount,
            "paid_amount": paid_amount,
            "penalty": round(penalty, 2),
            "reading_id": curr.id,
            "timestamp": int(curr.timestamp.timestamp()),
        })
    items.sort(key=lambda x: x["month_key"], reverse=True)
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    return jsonify({
        "items": items[start:end],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    })


@api_internal_bp.route("/customer/<customer_number>/invoice", methods=["POST"])
@require_internal_key
def customer_invoice(customer_number: str) -> Response:
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    data = request.get_json() or {}
    amount = data.get("amount", 0)
    if not amount or float(amount) <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    payment_method = data.get("payment_method", "")
    if not payment_method:
        return jsonify({"error": "Payment method is required"}), 400

    from services.fee_service import calculate_fee
    fee_rate, fee_amount = calculate_fee(float(amount), payment_method)
    total_amount = round(float(amount) + fee_amount, 2)

    external_id = f"wbs-{customer_number}-{int(datetime.utcnow().timestamp())}-{secrets.token_hex(4)}"

    from models import PaymentMethod
    method = PaymentMethod.query.filter_by(code=payment_method, is_active=True).first()
    channels = [method.channel_code] if method and method.channel_code else []

    import urllib.request, urllib.error, json as jsonlib, base64

    api_key_str = os.environ.get("XENDIT_API_KEY", "")
    if not api_key_str:
        return jsonify({"error": "Xendit not configured"}), 503

    names = (customer.name or customer_number).strip().split(" ", 1)
    given_names = names[0] or customer_number
    surname = names[1] if len(names) > 1 else ""

    payload = {
        "reference_id": external_id,
        "session_type": "PAY",
        "mode": "PAYMENT_LINK",
        "amount": total_amount,
        "currency": "PHP",
        "country": "PH",
        "allowed_payment_channels": channels,
        "success_return_url": data.get("success_url", ""),
        "cancel_return_url": data.get("cancel_url", ""),
        "description": f"Water bill payment - {customer.name or customer_number}",
        "customer": {
            "reference_id": external_id,
            "type": "INDIVIDUAL",
            "individual_detail": {"given_names": given_names},
        },
    }
    if surname:
        payload["customer"]["individual_detail"]["surname"] = surname
    if customer.email:
        payload["customer"]["email"] = customer.email
    if customer.contact_number:
        payload["customer"]["mobile_number"] = customer.contact_number

    auth = base64.b64encode(f"{api_key_str}:".encode()).decode()
    req = urllib.request.Request(
        "https://api.xendit.co/sessions",
        data=jsonlib.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            session = jsonlib.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return jsonify({"error": f"Xendit error: {error_body}"}), 502
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

    session_id = session.get("payment_session_id", "")
    payment_link_url = session.get("payment_link_url", "")
    if not payment_link_url:
        return jsonify({"error": "No redirect URL from Xendit"}), 502

    txn = XenditTransaction(
        customer_number=customer_number,
        xendit_pr_id=session_id,
        external_id=external_id,
        amount=total_amount,
        base_amount=amount,
        fee_amount=fee_amount,
        fee_rate=fee_rate,
        payment_method=payment_method,
        status="PENDING",
    )
    db.session.add(txn)
    db.session.commit()

    return jsonify({
        "redirect_url": payment_link_url,
        "external_id": external_id,
        "id": session_id,
        "base_amount": float(amount),
        "fee_amount": fee_amount,
        "fee_rate": fee_rate,
    })


# ── Staff endpoints ─────────────────────────────────────────────────────


@api_internal_bp.route("/staff/login", methods=["POST"])
@require_internal_key
def staff_login() -> Response:
    data = request.get_json()
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    staff = Staff.query.filter_by(username=username).first()
    if not staff or not staff.is_active:
        return jsonify({"error": "Invalid credentials"}), 401
    try:
        if not check_password_hash(staff.password.decode("utf-8"), password):
            return jsonify({"error": "Invalid credentials"}), 401
    except (ValueError, TypeError):
        import binascii, hashlib
        try:
            stored = staff.password.decode("ascii")
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
        "can_read_meters": staff.can_read_meters,
        "can_accept_payment": staff.can_accept_payment,
        "can_enroll_customer": staff.can_enroll_customer,
        "can_drop_reading": staff.can_drop_reading,
        "can_drop_payment": staff.can_drop_payment,
        "can_enroll_staff": staff.can_enroll_staff,
        "can_manage_billing": staff.can_manage_billing,
    })


@api_internal_bp.route("/staff/customer-lookup")
@require_internal_key
def staff_customer_lookup() -> Response:
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    customers = (
        Customer.query.filter(
            Customer.customer_number.like(f"%{q}%") | Customer.name.like(f"%{q}%")
        )
        .limit(10)
        .all()
    )
    return jsonify([
        {"customer_number": c.customer_number, "name": c.name, "address": c.address}
        for c in customers
    ])


@api_internal_bp.route("/staff/customers")
@require_internal_key
def staff_customers() -> Response:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "name")
    sort_dir = request.args.get("sort_dir", "asc")
    pagination = list_customers(
        page=page, per_page=per_page, q=q or None, sort_by=sort_by, sort_dir=sort_dir
    )
    customers_data = []
    for c in pagination.items:
        nfc_tag = NfcTag.query.filter_by(customer_number=c.customer_number).first()
        customers_data.append({
            "id": c.id,
            "customer_number": c.customer_number,
            "name": c.name,
            "address": c.address,
            "contact_number": c.contact_number,
            "phase": c.phase,
            "block": c.block,
            "street": c.street,
            "is_active": c.is_active,
            "nfc_uid": nfc_tag.uid if nfc_tag else None,
        })
    return jsonify({
        "customers": customers_data,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    })


@api_internal_bp.route("/staff/dashboard")
@require_internal_key
def staff_dashboard() -> Response:
    total_customers = Customer.query.filter_by(is_active=True).count()
    total_unpaid = Billing.query.filter_by(is_paid=False).count()
    total_paid_today = Billing.query.filter(
        Billing.is_paid.is_(True),
        Billing.date_paid >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
    ).count()
    total_staff = Staff.query.filter_by(is_active=True).count()
    latest_readings = (
        MeterReading.query
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .order_by(desc(MeterReading.timestamp))
        .limit(10)
        .all()
    )
    return jsonify({
        "total_customers": total_customers,
        "total_unpaid_bills": total_unpaid,
        "total_paid_today": total_paid_today,
        "total_staff": total_staff,
        "latest_readings": [
            {
                "id": r.id,
                "customer_number": r.customer_number,
                "reading_value": float(r.reading_value),
                "reader": r.token.staff.name if r.token and r.token.staff else None,
                "timestamp": int(r.timestamp.timestamp()),
            }
            for r in latest_readings
        ],
    })


@api_internal_bp.route("/staff/customer", methods=["POST"])
@require_internal_key
def staff_customer_create() -> Response:
    data = request.get_json()
    customer, error = create_customer(data or {})
    if error:
        status = 409 if "already exists" in error else 400
        return jsonify({"error": error}), status
    return jsonify({"message": "Customer enrolled", "customer_number": customer.customer_number}), 201


@api_internal_bp.route("/staff/customer/<int:customer_id>/edit", methods=["POST"])
@require_internal_key
def staff_customer_edit(customer_id: int) -> Response:
    customer = get_customer_or_404(customer_id)
    data = request.get_json()
    update_customer(customer, data or {})
    return jsonify({"message": "Customer updated"})


@api_internal_bp.route("/staff/customer/<int:customer_id>/toggle-active", methods=["POST"])
@require_internal_key
def staff_customer_toggle_active(customer_id: int) -> Response:
    customer = get_customer_or_404(customer_id)
    toggle_active(customer)
    return jsonify({
        "message": f'Customer {"deactivated" if not customer.is_active else "reactivated"}',
        "is_active": customer.is_active,
    })


@api_internal_bp.route("/staff/customer/<int:customer_id>/clear-nfc", methods=["POST"])
@require_internal_key
def staff_customer_clear_nfc(customer_id: int) -> Response:
    customer = get_customer_or_404(customer_id)
    NfcTag.query.filter_by(customer_number=customer.customer_number).delete()
    gen_row = Config.query.filter_by(key="nfc_generation").first()
    if gen_row:
        gen_row.value = str(int(gen_row.value) + 1)
    else:
        db.session.add(Config(key="nfc_generation", value="1"))
    customer.date_modified = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": f"NFC mapping cleared for {customer.customer_number}"})


@api_internal_bp.route("/staff/payment/submit", methods=["POST"])
@require_internal_key
def staff_payment_submit() -> Response:
    data = request.get_json()
    customer_number = (data or {}).get("customer_number", "").strip()
    amount = data.get("amount", 0)
    staff_id = data.get("staff_id", 0)
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid payment amount"}), 400
    if not staff_id:
        return jsonify({"error": "staff_id is required"}), 400
    result, error, status = service_submit_payment(customer_number, amount_float, staff_id)
    if error:
        return jsonify({"error": error}), status
    db.session.commit()
    return jsonify(result), status


@api_internal_bp.route("/staff/cashier-tally")
@require_internal_key
def staff_cashier_tally() -> Response:
    staff_id = request.args.get("staff_id", type=int)
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
        "display": nav["display"],
        "prev_date": nav["prev_date"],
        "next_date": nav["next_date"],
        "is_today": nav["is_today"],
        "period": period,
    })


@api_internal_bp.route("/staff/reading/<int:reading_id>/drop", methods=["POST"])
@require_internal_key
def staff_reading_drop(reading_id: int) -> Response:
    data = request.get_json()
    staff_id = (data or {}).get("staff_id", 0)
    reason = (data or {}).get("reason", "").strip()
    if not staff_id:
        return jsonify({"error": "staff_id is required"}), 400
    if not reason:
        return jsonify({"error": "Reason is required"}), 400
    try:
        service_drop_reading(reading_id, staff_id, reason)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"message": "Reading dropped"})


@api_internal_bp.route("/staff/reading/<int:reading_id>/edit", methods=["POST"])
@require_internal_key
def staff_reading_edit(reading_id: int) -> Response:
    data = request.get_json()
    staff_id = (data or {}).get("staff_id", 0)
    try:
        new_value = float((data or {}).get("reading_value", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid reading value"}), 400
    if not staff_id:
        return jsonify({"error": "staff_id is required"}), 400
    service_edit_reading(reading_id, new_value, staff_id)
    return jsonify({"message": "Reading updated"})


@api_internal_bp.route("/staff/billing/<int:payment_id>/undo", methods=["POST"])
@require_internal_key
def staff_billing_undo(payment_id: int) -> Response:
    data = request.get_json()
    staff_id = (data or {}).get("staff_id", 0)
    reason = (data or {}).get("reason", "").strip()
    if not staff_id:
        return jsonify({"error": "staff_id is required"}), 400
    if not reason:
        return jsonify({"error": "Reason is required"}), 400
    billing = Billing.query.get_or_404(payment_id)
    if not billing.is_paid:
        return jsonify({"error": "Bill is not paid"}), 400
    result = service_drop_payment(payment_id, staff_id, reason)
    if result and "error" in result:
        return jsonify(result), 400
    return jsonify(result or {"message": "Payment undone"})


@api_internal_bp.route("/staff/api-key/generate", methods=["POST"])
@require_internal_key
def staff_api_key_generate() -> Response:
    data = request.get_json()
    label = ((data or {}).get("label", "") or "").strip() or None
    staff_id = (data or {}).get("staff_id", 0)
    if not staff_id:
        return jsonify({"error": "staff_id is required"}), 400
    staff = Staff.query.get(staff_id)
    if not staff:
        return jsonify({"error": "Staff not found"}), 404
    key = "CRDC-" + secrets.token_hex(16).upper()
    api_key = ApiKey(key=key, label=label, staff_id=staff_id)
    db.session.add(api_key)
    db.session.commit()
    return jsonify({"key": key, "label": label, "id": api_key.id}), 201


@api_internal_bp.route("/staff/api-key/<int:key_id>/revoke", methods=["POST"])
@require_internal_key
def staff_api_key_revoke(key_id: int) -> Response:
    api_key = ApiKey.query.get_or_404(key_id)
    api_key.is_active = False
    db.session.commit()
    return jsonify({"message": "Key revoked"})


@api_internal_bp.route("/staff/api-keys")
@require_internal_key
def staff_api_key_list() -> Response:
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
                "key": k.key[:20] + "..." if len(k.key) > 20 else k.key,
                "label": k.label,
                "is_active": k.is_active,
                "staff_id": k.staff_id,
                "staff_name": k.staff.name if k.staff else None,
                "date_created": k.date_created.isoformat() if k.date_created else None,
            }
            for k in keys
        ]
    })


@api_internal_bp.route("/staff/reading-logs")
@require_internal_key
def staff_reading_logs() -> Response:
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


@api_internal_bp.route("/staff/staff")
@require_internal_key
def staff_staff_list() -> Response:
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


@api_internal_bp.route("/staff/staff/create", methods=["POST"])
@require_internal_key
def staff_staff_create() -> Response:
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


@api_internal_bp.route("/staff/staff/<int:staff_id>")
@require_internal_key
def staff_staff_get(staff_id: int) -> Response:
    staff = Staff.query.get_or_404(staff_id)
    return jsonify(staff.to_dict())


@api_internal_bp.route("/staff/staff/<int:staff_id>/edit", methods=["POST"])
@require_internal_key
def staff_staff_edit(staff_id: int) -> Response:
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


# ── Debug endpoints ─────────────────────────────────────────────────────


_last_restore_newest_time = 0.0
_restore_newest_lock = threading.Lock()


def _superuser_only() -> Response | None:
    if not BACKUP_DIR.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return None


@api_internal_bp.route("/debug/backup", methods=["POST"])
@require_internal_key
def debug_backup() -> Response:
    task = BackgroundTask.enqueue(task_type="backup", params={}, title="Backup Database")
    return jsonify({"ok": True, "order_id": task.id, "message": "Backup queued."})


@api_internal_bp.route("/debug/backups")
@require_internal_key
def debug_backups() -> Response:
    _superuser_only()
    if not BACKUP_DIR.exists():
        return jsonify({"backups": []})
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    return jsonify({
        "backups": [
            {
                "name": b.name,
                "size": b.stat().st_size,
                "modified": datetime.fromtimestamp(b.stat().st_mtime).isoformat(),
            }
            for b in backups
        ]
    })


@api_internal_bp.route("/debug/restore", methods=["POST"])
@require_internal_key
def debug_restore() -> Response:
    filename = (request.get_json() or {}).get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No backup file specified"}), 400
    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".sql"):
        return jsonify({"error": "Backup file not found"}), 404
    task = BackgroundTask.enqueue(
        task_type="restore", params={"filename": filename}, title=f"Restore: {filename}"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Restore queued."})


@api_internal_bp.route("/debug/restore-newest")
@require_internal_key
def debug_restore_newest() -> Response:
    global _last_restore_newest_time
    with _restore_newest_lock:
        now = time.time()
        if now - _last_restore_newest_time < 5:
            remaining = round(5 - (now - _last_restore_newest_time), 1)
            return jsonify({"error": f"Cooldown active. Try again in {remaining}s"}), 429
        _last_restore_newest_time = now
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    if not backups:
        return jsonify({"error": "No backup files found"}), 404
    filename = backups[0].name
    task = BackgroundTask.enqueue(
        task_type="restore", params={"filename": filename}, title=f"Restore newest: {filename}"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": f"Restoring from newest backup: {filename}"})


@api_internal_bp.route("/debug/clear", methods=["POST"])
@require_internal_key
def debug_clear() -> Response:
    task = BackgroundTask.enqueue(task_type="clear", params={}, title="Clear Database")
    return jsonify({"ok": True, "order_id": task.id, "message": "Clear queued."})


@api_internal_bp.route("/debug/seed", methods=["POST"])
@require_internal_key
def debug_seed() -> Response:
    data = request.get_json() or {}
    try:
        n_customers = int(data.get("customers", "0"))
        n_months = int(data.get("months", "0"))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid customer count or months"}), 400
    if n_customers < 1 or n_customers > 10000:
        return jsonify({"error": "Customer count must be between 1 and 10000"}), 400
    if n_months < 1 or n_months > 240:
        return jsonify({"error": "Months must be between 1 and 240"}), 400
    task = BackgroundTask.enqueue(
        task_type="seed",
        params={"customers": n_customers, "months": n_months},
        title=f"Seed: {n_customers}c \u00d7 {n_months}m",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Seed queued."})


@api_internal_bp.route("/debug/read-this-month", methods=["POST"])
@require_internal_key
def debug_read_month() -> Response:
    task = BackgroundTask.enqueue(
        task_type="read-this-month", params={}, title="Read This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Read-this-month queued."})


@api_internal_bp.route("/debug/unread-this-month", methods=["POST"])
@require_internal_key
def debug_unread_month() -> Response:
    task = BackgroundTask.enqueue(
        task_type="unread-this-month", params={}, title="Unread This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Unread-this-month queued."})


@api_internal_bp.route("/debug/pay-this-month", methods=["POST"])
@require_internal_key
def debug_pay_month() -> Response:
    task = BackgroundTask.enqueue(
        task_type="pay-this-month", params={}, title="Pay This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Pay-this-month queued."})


@api_internal_bp.route("/debug/remove-payment-this-month", methods=["POST"])
@require_internal_key
def debug_remove_pay_month() -> Response:
    task = BackgroundTask.enqueue(
        task_type="remove-payment-this-month", params={}, title="Remove Payment This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Remove-payment queued."})


@api_internal_bp.route("/debug/tasks")
@require_internal_key
def debug_tasks() -> Response:
    current_task = BackgroundTask.query.filter_by(status="running").first()
    queue = BackgroundTask.query.filter_by(status="queued").order_by(BackgroundTask.created_at.asc()).all()
    history = (
        BackgroundTask.query.filter(BackgroundTask.status.in_(["completed", "failed"]))
        .order_by(BackgroundTask.created_at.desc())
        .limit(20)
        .all()
    )

    def _to_dict(t: BackgroundTask) -> dict:
        return {
            "id": str(t.id),
            "task_type": t.task_type,
            "title": t.title,
            "status": t.status,
            "progress": t.progress,
            "messages": t.messages or [],
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }

    return jsonify({
        "current": _to_dict(current_task) if current_task else None,
        "queue_depth": len(queue),
        "history": [_to_dict(t) for t in history],
    })


@api_internal_bp.route("/debug/tasks/<int:task_id>")
@require_internal_key
def debug_task(task_id: int) -> Response:
    task = BackgroundTask.query.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({
        "task": {
            "id": str(task.id),
            "task_type": task.task_type,
            "title": task.title,
            "status": task.status,
            "progress": task.progress,
            "messages": task.messages or [],
            "params": task.params,
            "result": task.result,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
    })
