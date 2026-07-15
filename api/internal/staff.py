from . import api_internal_bp, db, Response, jsonify, request
from . import Customer, Staff, ApiKey, Billing, ManagementLog, MeterReading, Config
from . import PRICING_TIERS, compute_water_bill
from . import service_drop_payment, service_submit_payment, service_drop_reading, service_edit_reading
from . import ensure_penalty
from . import datetime, timedelta, desc, joinedload
from . import secrets
from . import generate_password_hash, check_password_hash
from . import list_customers
from . import threading


@api_internal_bp.route("/staff/login", methods=["POST"])
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
        {"customer_number": c.customer_number, "name": c.name, "address": c.address,
            "meter_serial_number": c.meter_serial_number or ""}
        for c in customers
    ])


@api_internal_bp.route("/staff/customers")
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
            "meter_serial_number": c.meter_serial_number or "",
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
def staff_customer_create() -> Response:
    data = request.get_json()
    customer, error = create_customer(data or {})
    if error:
        status = 409 if "already exists" in error else 400
        return jsonify({"error": error}), status
    return jsonify({"message": "Customer enrolled", "customer_number": customer.customer_number}), 201


@api_internal_bp.route("/staff/customer/<int:customer_id>/edit", methods=["POST"])
def staff_customer_edit(customer_id: int) -> Response:
    customer = get_customer_or_404(customer_id)
    data = request.get_json()
    update_customer(customer, data or {})
    return jsonify({"message": "Customer updated"})


@api_internal_bp.route("/staff/customer/<int:customer_id>/toggle-active", methods=["POST"])
def staff_customer_toggle_active(customer_id: int) -> Response:
    customer = get_customer_or_404(customer_id)
    toggle_active(customer)
    return jsonify({
        "message": f'Customer {"deactivated" if not customer.is_active else "reactivated"}',
        "is_active": customer.is_active,
    })


@api_internal_bp.route("/staff/customer/<int:customer_id>/clear-nfc", methods=["POST"])
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
def staff_api_key_revoke(key_id: int) -> Response:
    api_key = ApiKey.query.get_or_404(key_id)
    api_key.is_active = False
    db.session.commit()
    return jsonify({"message": "Key revoked"})


@api_internal_bp.route("/staff/api-keys")
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
def staff_staff_get(staff_id: int) -> Response:
    staff = Staff.query.get_or_404(staff_id)
    return jsonify(staff.to_dict())


@api_internal_bp.route("/staff/staff/<int:staff_id>/edit", methods=["POST"])
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

