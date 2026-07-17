from __future__ import annotations

from datetime import datetime, timezone, timedelta

from flask import Response, jsonify, request
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from app import db
from blueprint import blueprint
from models import ApiKey, Billing, Config, Customer, ManagementLog, MeterReading, NfcTag, PaymentMethod, XenditTransaction
from pricing import PRICING_TIERS
from billing_service import ensure_penalty
from services.payment_service import (
    drop_payment as service_drop_payment,
    submit_payment as service_submit_payment,
)
from fee_service import calculate_fee
from reading_service import (
    drop_reading as service_drop_reading,
    edit_reading as service_edit_reading,
    upload_reading as service_upload_reading,
)
from customer_service import (
    create_customer,
    get_customer_by_number,
    get_customer_or_404,
    list_customers,
    toggle_active,
    update_customer,
)
from utils import require_staff, resolve_api_key


@blueprint.route("/customer/count")
def customer_count() -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
    count = Customer.query.filter_by(is_active=True).count()
    return jsonify({"count": count})


@blueprint.route("/customer/all")
def customer_all() -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 50, type=int)
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "name")
    sort_dir = request.args.get("sort_dir", "asc")
    pagination = list_customers(
        page=page, per_page=size, q=q or None, sort_by=sort_by, sort_dir=sort_dir
    )
    customers_data = []
    from customer_service import compute_batch_due
    due_map = compute_batch_due(list(pagination.items))
    for c in pagination.items:
        nfc_tag = NfcTag.query.filter_by(customer_number=c.customer_number).first()
        customers_data.append({
            "id": c.id,
            "customer_number": c.customer_number,
            "name": c.name,
            "address": c.address,
            "meter_serial_number": c.meter_serial_number or "",
            "contact_number": c.contact_number,
            "email": c.email,
            "phase": c.phase,
            "block": c.block,
            "street": c.street,
            "x_coordinate": c.x_coordinate,
            "y_coordinate": c.y_coordinate,
            "cumulative_balance": float(c.cumulative_balance or 0),
            "max_meter_value": float(c.max_meter_value or 99999),
            "total_due": due_map.get(c.customer_number, 0.0),
            "is_active": c.is_active,
            "nfc_uid": nfc_tag.uid if nfc_tag else None,
        })
    return jsonify({
        "data": customers_data,
        "meta": {
            "current_page": pagination.page,
            "page_size": pagination.per_page,
            "total_items": pagination.total,
            "total_pages": pagination.pages,
        },
    })


@blueprint.route("/customer/<customer_number>")
def customer_info(customer_number: str) -> Response:
    """Get full billing details for a specific customer."""
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    staff_filter = request.args.get("staff_id", type=int)
    token_filter = request.args.get("token_id", type=int)

    readings_query = (
        MeterReading.query
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .filter_by(customer_number=customer_number)
    )
    if token_filter:
        readings_query = readings_query.filter(MeterReading.token_id == token_filter)
    if staff_filter:
        readings_query = readings_query.join(MeterReading.token).filter(
            ApiKey.staff_id == staff_filter
        )
    readings = readings_query.order_by(desc(MeterReading.timestamp)).all()

    latest_reading = readings[0] if len(readings) > 0 else None
    last_reading = readings[1] if len(readings) > 1 else None

    consumption = (
        float(round(latest_reading.reading_value - last_reading.reading_value, 2))
        if latest_reading and last_reading
        else 0
    )

    # Query stored bills for this customer
    all_bills = (
        Billing.query
        .filter_by(customer_number=customer_number)
        .order_by(Billing.date_created.desc())
        .all()
    )

    # Separate into unpaid and paid
    unpaid_bills_list: list[Billing] = []
    paid_bills_list: list[Billing] = []
    for b in all_bills:
        if not b.is_paid:
            ensure_penalty(b)
            unpaid_bills_list.append(b)
        else:
            paid_bills_list.append(b)

    # Build unpaid bills display
    unpaid_bills = []
    for bill in unpaid_bills_list:
        reading = bill.reading
        if reading:
            month_str = reading.timestamp.strftime("%B %Y")
            ts = int(reading.timestamp.timestamp())
        else:
            month_str = bill.date_created.strftime("%B %Y") if bill.date_created else "Unknown"
            ts = int(bill.date_created.timestamp()) if bill.date_created else 0
        unpaid_bills.append(
            {
                "id": bill.id,
                "month": month_str,
                "amount": round(float(bill.billed_amount), 2),
                "penalty": round(float(bill.penalty), 2),
                "timestamp": ts,
            }
        )

    total_unpaid = sum(b["amount"] for b in unpaid_bills)
    total_penalties = sum(b["penalty"] for b in unpaid_bills)
    total_carryover = (
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )
    balance = float(total_carryover)
    total_due = max(0, total_unpaid + total_penalties - balance)

    due_date = None
    days_remaining = None
    if unpaid_bills:
        due_dt = datetime.fromtimestamp(unpaid_bills[0]["timestamp"], tz=timezone.utc).replace(tzinfo=None) + timedelta(days=7)
        due_date = due_dt.strftime("%m-%d-%Y")
        days_remaining = max(0, (due_dt - datetime.now(tz=timezone.utc).replace(tzinfo=None)).days)

    # Build billing items with reading history
    reading_pairs = []
    for i in range(len(readings)):
        curr = readings[i]
        prev = readings[i + 1] if i + 1 < len(readings) else None
        cons = float(round(curr.reading_value - prev.reading_value, 2)) if prev else 0.0

        # Find the bill for this reading
        bill = next((b for b in all_bills if b.reading_id == curr.id), None)
        if bill:
            wb = round(float(bill.billed_amount), 2)
            pen = round(float(bill.penalty), 2)
            td = round(wb + pen, 2)
            status = "Paid" if bill.is_paid else "Unpaid"
            billing_id = bill.id
            paid_amt = float(bill.paid_amount)
            receipt = bill.receipt_number
        else:
            wb = 0.0
            pen = 0.0
            td = 0.0
            status = "No bill"
            billing_id = None
            paid_amt = 0
            receipt = None

        carryover_off = float(bill.carryover_offset) if bill else 0.0

        reading_pairs.append(
            {
                "id": curr.id,
                "billing_id": billing_id,
                "reading_value": float(curr.reading_value),
                "consumption": cons,
                "water_bill": wb,
                "penalty": pen,
                "total_due": td,
                "timestamp": int(curr.timestamp.timestamp()),
                "period": int(curr.timestamp.timestamp()),
                "paid_amount": paid_amt,
                "receipt_number": receipt,
                "status": status,
                "carryover_offset": carryover_off,
                "is_latest_paid": False,
            }
        )

    # Determine the latest receipt group for waterfall undo.
    # All bills in the same receipt form a group; undoing one undoes all.
    latest_receipt: str | None = None
    latest_receipt_ts: datetime | None = None
    for b in all_bills:
        if b.is_paid and b.receipt_number and b.payment_timestamp:
            if latest_receipt_ts is None or b.payment_timestamp > latest_receipt_ts:
                latest_receipt_ts = b.payment_timestamp
                latest_receipt = b.receipt_number

    latest_receipt_billing_ids: set[int] = set()
    if latest_receipt:
        for b in all_bills:
            if b.receipt_number == latest_receipt:
                latest_receipt_billing_ids.add(b.id)

    for item in reading_pairs:
        item["is_latest_paid"] = item["billing_id"] in latest_receipt_billing_ids

    # Recent payments: find bills that have been paid
    recent_billings = (
        Billing.query
        .filter_by(customer_number=customer_number, is_paid=True)
        .filter(Billing.receipt_number.isnot(None))
        .order_by(desc(Billing.date_paid))
        .limit(10)
        .all()
    )

    # Estimated bill for latest consumption only (for display consistency)
    from pricing import compute_water_bill
    water_bill, bill_breakdown = compute_water_bill(consumption) if consumption > 0 else (0.0, [])
    carryover = abs(float(total_carryover))
    balance = float(total_carryover)
    latest_unpaid = len(unpaid_bills) > 0

    return jsonify(
        {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address,
        "meter_serial_number": customer.meter_serial_number or "",
            "contact_number": customer.contact_number,
            "email": customer.email,
            "phase": customer.phase,
            "block": customer.block,
            "street": customer.street,
            "max_meter_value": float(customer.max_meter_value or 99999),
            "latest_reading": (
                {
                    "id": latest_reading.id,
                    "reading_value": float(latest_reading.reading_value),
                    "reader": (
                        latest_reading.token.staff.name
                        if latest_reading.token and latest_reading.token.staff
                        else None
                    ),
                    "timestamp": int(latest_reading.timestamp.timestamp()),
                }
                if latest_reading
                else None
            ),
            "last_reading": (
                {
                    "id": last_reading.id,
                    "reading_value": float(last_reading.reading_value),
                    "reader": (
                        last_reading.token.staff.name
                        if last_reading.token and last_reading.token.staff
                        else None
                    ),
                    "timestamp": int(last_reading.timestamp.timestamp()),
                }
                if last_reading
                else None
            ),
            "consumption": consumption,
            "bill_breakdown": bill_breakdown,
            "pricing_tiers": PRICING_TIERS,
            "water_bill": water_bill,
            "original_water_bill": water_bill,
            "carryover": carryover,
            "cumulative_balance": balance,
            "penalty": round(total_penalties, 2),
            "total_due": round(total_due, 2),
            "latest_unpaid": latest_unpaid,
            "unpaid_bills": unpaid_bills,
            "total_unpaid": round(total_unpaid, 2),
            "total_penalties": round(total_penalties, 2),
            "due_date": due_date,
            "days_remaining": days_remaining,
            "billing_items": reading_pairs,
            "recent_payments": [
                {
                    "id": b.id,
                    "receipt_number": b.receipt_number,
                    "paid_amount": float(b.paid_amount),
                    "timestamp": (
                        int(b.payment_timestamp.timestamp())
                        if b.payment_timestamp
                        else int(b.date_paid.timestamp())
                        if b.date_paid
                        else 0
                    ),
                    "cashier_id": b.cashier_id,
                    "cashier": (
                        (b.cashier.name or b.cashier.username) if b.cashier else None
                    ),
                }
                for b in recent_billings
            ],
            "payment_methods": [
                {
                    "code": pm.code,
                    "label": pm.label,
                    "sort_order": pm.sort_order,
                    "fee_percent": float(pm.fee_percent) if pm.fee_percent else 0,
                    "fee_flat": float(pm.fee_flat) if pm.fee_flat else 0,
                    "fee_minimum": float(pm.fee_minimum) if pm.fee_minimum else 0,
                    "xendit_fee": float(pm.xendit_fee) if pm.xendit_fee else 0,
                }
                for pm in PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.sort_order).all()
            ],
        }
    )


@blueprint.route("/customer/<customer_number>/details")
def customer_details(customer_number: str) -> Response:
    """Get customer profile with recent reading history."""
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
        return jsonify({"error": "Permission denied"}), 403

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    history = request.args.get("history", "5")
    try:
        history = int(history)
    except (ValueError, TypeError):
        return jsonify({"error": "history must be an integer"}), 400

    readings = (
        MeterReading.query
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .filter_by(customer_number=customer_number)
        .order_by(desc(MeterReading.timestamp))
        .limit(history)
        .all()
    )

    return jsonify(
        {
            "customer": {
                "customer_number": customer.customer_number,
                "name": customer.name,
                "address": customer.address,
        "meter_serial_number": customer.meter_serial_number or "",
                "contact_number": customer.contact_number,
                "email": customer.email,
                "phase": customer.phase,
                "block": customer.block,
                "street": customer.street,
                "x_coordinate": customer.x_coordinate,
                "y_coordinate": customer.y_coordinate,
                "cumulative_balance": float(customer.cumulative_balance or 0),
                "max_meter_value": float(customer.max_meter_value or 99999),
            },
            "readings": [
                {
                    "id": r.id,
                    "reading_value": float(r.reading_value),
                    "reader": r.token.staff.name if r.token and r.token.staff else None,
                    "timestamp": int(r.timestamp.timestamp()),
                }
                for r in readings
            ],
        }
    )


@blueprint.route("/customer/<customer_number>/profile")
def customer_profile(customer_number: str) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err
    return customer_info(customer_number)


@blueprint.route("/customer/new", methods=["POST"])
def customer_new() -> Response:
    api_key, err = require_staff("can_enroll_customer")
    if err:
        return err
    data = request.get_json()
    customer, error = create_customer(data or {})
    if error:
        status = 409 if "already exists" in error else 400
        return jsonify({"error": error}), status
    return jsonify({
        "message": "Customer created",
        "customer_number": customer.customer_number,
    }), 201


@blueprint.route("/customer/update/<customer_number>", methods=["PUT"])
def customer_update(customer_number: str) -> Response:
    api_key, err = require_staff("can_enroll_customer")
    if err:
        return err
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
    data = request.get_json()
    update_customer(customer, data or {})
    return jsonify({"message": "Customer updated"})


@blueprint.route("/customer/delete/<customer_number>", methods=["DELETE"])
def customer_delete(customer_number: str) -> Response:
    api_key, err = require_staff("can_enroll_customer")
    if err:
        return err
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
    toggle_active(customer)
    return jsonify({
        "message": f'Customer {"deactivated" if not customer.is_active else "reactivated"}',
        "is_active": customer.is_active,
    })


@blueprint.route("/customer/login", methods=["POST"])
def customer_login() -> Response:
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
            "meter_serial_number": customer.meter_serial_number or "",
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
        }
    })


@blueprint.route("/customer/<customer_number>/invoice", methods=["POST"])
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

    fee_rate, fee_amount = calculate_fee(float(amount), payment_method)
    total_amount = round(float(amount) + fee_amount, 2)

    import os, secrets
    external_id = f"wbs-{customer_number}-{int(datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp())}-{secrets.token_hex(4)}"

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


# ── Reading CRUD ────────────────────────────────────────────────────────


@blueprint.route("/customer/<customer_number>/reading")
def customer_readings(customer_number: str) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

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


@blueprint.route("/customer/<customer_number>/reading/new", methods=["POST"])
def customer_reading_new(customer_number: str) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

    data = request.get_json() or {}
    reading_value = data.get("reading_value")
    timestamp = data.get("timestamp", datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp())
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    staff_name = data.get("staff_name") if api_key is True else api_key.staff.name

    if reading_value is None:
        return jsonify({"error": "reading_value is required"}), 400

    try:
        reading_float = float(reading_value)
        ts_float = float(timestamp)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid reading_value or timestamp"}), 400

    if api_key is True:
        from models import ApiKey as KeyModel
        token = KeyModel.query.filter_by(is_active=True).first()
        token_id = token.id if token else None
    else:
        token_id = api_key.id
    reading, error, status = service_upload_reading(
        customer_number, reading_float, ts_float, token_id, staff_id, staff_name
    )
    if error:
        return jsonify({"error": error}), status

    return jsonify({
        "success": True,
        "reading_id": reading.id,
        "customer_number": customer_number,
        "reading_value": float(reading_value),
        "timestamp": int(timestamp),
        "reader": staff_name,
    }), 201


@blueprint.route("/customer/<customer_number>/reading/drop", methods=["POST"])
def customer_reading_drop(customer_number: str) -> Response:
    api_key, err = require_staff("can_drop_reading")
    if err:
        return err

    data = request.get_json() or {}
    reading_id = data.get("reading_id")
    reason = data.get("reason", "").strip()
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    if not reading_id:
        return jsonify({"error": "reading_id is required"}), 400
    if not reason:
        return jsonify({"error": "Reason is required"}), 400
    try:
        service_drop_reading(reading_id, staff_id, reason)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"message": "Reading dropped"})


@blueprint.route("/customer/<customer_number>/reading/edit", methods=["POST"])
def customer_reading_edit(customer_number: str) -> Response:
    api_key, err = require_staff("can_manage_billing")
    if err:
        return err

    data = request.get_json() or {}
    reading_id = data.get("reading_id")
    try:
        new_value = float(data.get("reading_value", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid reading value"}), 400
    if not reading_id:
        return jsonify({"error": "reading_id is required"}), 400
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    service_edit_reading(reading_id, new_value, staff_id)
    return jsonify({"message": "Reading updated"})


@blueprint.route("/customers/changed")
def customers_changed() -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

    since = request.args.get("since", type=int)
    if since is None:
        return jsonify({"error": "since parameter is required (Unix timestamp)"}), 400

    try:
        since_dt = datetime.fromtimestamp(since)
    except (ValueError, OSError, OverflowError):
        return jsonify({"error": "Invalid since timestamp"}), 400

    modified_customers = (
        Customer.query.with_entities(Customer.customer_number)
        .filter(Customer.date_modified > since_dt, Customer.is_active.is_(True))
        .all()
    )

    reading_customers = (
        db.session.query(MeterReading.customer_number.distinct())
        .filter(db.or_(MeterReading.date_created > since_dt, MeterReading.date_modified > since_dt))
        .all()
    )

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

    all_changed = {c[0] for c in modified_customers}
    all_changed.update(c[0] for c in reading_customers)
    all_changed.update(dropped_customers)

    return jsonify({
        "customer_numbers": list(all_changed),
        "server_time": int(datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp()),
        "total_customers": Customer.query.filter_by(is_active=True).count(),
    })


# ── Billing CRUD ────────────────────────────────────────────────────────


@blueprint.route("/customer/<customer_number>/billing")
def customer_billing(customer_number: str) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 50, type=int)
    pagination = (
        Billing.query
        .filter_by(customer_number=customer_number)
        .order_by(desc(Billing.date_created))
        .paginate(page=page, per_page=size, error_out=False)
    )
    items = []
    for b in pagination.items:
        ensure_penalty(b)
        reading = MeterReading.query.get(b.reading_id) if b.reading_id else None
        items.append({
            "id": b.id,
            "reading_id": b.reading_id,
            "month": reading.timestamp.strftime("%B %Y") if reading else None,
            "previous_reading": float(b.previous_reading_value) if b.previous_reading_value else None,
            "current_reading": float(b.current_reading_value) if b.current_reading_value else None,
            "consumption": float(b.consumption) if b.consumption else None,
            "billed_amount": float(b.billed_amount),
            "penalty": float(b.penalty),
            "paid_amount": float(b.paid_amount),
            "is_paid": b.is_paid,
            "receipt_number": b.receipt_number,
            "cashier_id": b.cashier_id,
            "payment_timestamp": int(b.payment_timestamp.timestamp()) if b.payment_timestamp else None,
            "date_paid": int(b.date_paid.timestamp()) if b.date_paid else None,
            "created_at": int(b.date_created.timestamp()) if b.date_created else None,
        })
    return jsonify({
        "data": items,
        "meta": {
            "current_page": pagination.page,
            "page_size": pagination.per_page,
            "total_items": pagination.total,
            "total_pages": pagination.pages,
        },
    })


@blueprint.route("/customer/<customer_number>/billing/new", methods=["POST"])
def customer_billing_new(customer_number: str) -> Response:
    api_key, err = require_staff("can_accept_payment")
    if err:
        return err

    data = request.get_json() or {}
    amount = data.get("amount", 0)
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid payment amount"}), 400
    if amount_float <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    result, error, status = service_submit_payment(customer_number, amount_float, staff_id)
    if error:
        return jsonify({"error": error}), status
    db.session.commit()
    return jsonify(result), status


@blueprint.route("/customer/<customer_number>/billing/drop", methods=["POST"])
def customer_billing_drop(customer_number: str = "") -> Response:
    api_key, err = require_staff("can_drop_payment")
    if err:
        return err

    data = request.get_json() or {}
    billing_id = data.get("billing_id")
    reason = data.get("reason", "").strip()
    staff_id = data.get("staff_id") if api_key is True else api_key.staff.id
    if not billing_id:
        return jsonify({"error": "billing_id is required"}), 400
    if not reason:
        return jsonify({"error": "Reason is required"}), 400

    billing = Billing.query.get(billing_id)
    if not billing:
        return jsonify({"error": "Billing record not found"}), 404
    if not billing.is_paid:
        return jsonify({"error": "Bill is not paid"}), 400

    result = service_drop_payment(billing_id, staff_id, reason)
    if result and "error" in result:
        return jsonify(result), 400
    return jsonify(result or {"message": "Payment dropped"})


# ── NFC ──────────────────────────────────────────────────────────────────


@blueprint.route("/customer/<customer_number>/nfc")
def customer_nfc(customer_number: str) -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

    tag = NfcTag.query.filter_by(customer_number=customer_number).first()
    if not tag:
        return jsonify({"nfc_uid": None})

    return jsonify({
        "nfc_uid": tag.uid,
        "customer_number": tag.customer_number,
    })


@blueprint.route("/customer/all/nfc")
def customer_all_nfc() -> Response:
    api_key, err = require_staff("can_read_meters")
    if err:
        return err

    tags = NfcTag.query.order_by(NfcTag.date_created.desc()).all()
    return jsonify({
        "tags": [
            {"uid": t.uid, "customer_number": t.customer_number}
            for t in tags
        ]
    })


@blueprint.route("/customer/<customer_number>/nfc/create", methods=["POST"])
def customer_nfc_create(customer_number: str) -> Response:
    api_key, err = require_staff("can_enroll_customer")
    if err:
        return err

    data = request.get_json() or {}
    uid = data.get("uid", "").strip()
    if not uid:
        return jsonify({"error": "uid is required"}), 400

    existing_tag = NfcTag.query.filter_by(uid=uid).first()
    if existing_tag:
        return jsonify({"error": "Tag UID already assigned"}), 409

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    tag = NfcTag(uid=uid, customer_number=customer_number, enrolled_by_id=api_key.staff.id)
    db.session.add(tag)
    customer.date_modified = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.session.commit()

    return jsonify({"message": "Tag assigned", "uid": uid, "customer_number": customer_number}), 201


@blueprint.route("/customer/<customer_number>/nfc/delete", methods=["POST"])
def customer_nfc_delete(customer_number: str) -> Response:
    api_key, err = require_staff("can_enroll_customer")
    if err:
        return err

    tag = NfcTag.query.filter_by(customer_number=customer_number).first()
    if not tag:
        return jsonify({"error": "No NFC tag assigned to this customer"}), 404

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    db.session.delete(tag)

    gen_row = Config.query.filter_by(key="nfc_generation").first()
    if gen_row:
        gen_row.value = str(int(gen_row.value) + 1)
    else:
        db.session.add(Config(key="nfc_generation", value="1"))

    if customer:
        customer.date_modified = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.session.commit()

    return jsonify({"message": "Tag deleted", "uid": tag.uid})
