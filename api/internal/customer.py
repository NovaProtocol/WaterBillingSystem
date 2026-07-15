from . import api_internal_bp, db, Response, jsonify, request
from . import Customer, MeterReading, Billing, ApiKey, XenditTransaction
from . import PRICING_TIERS, compute_water_bill
from . import ensure_penalty
from . import datetime, timedelta, desc, joinedload

@api_internal_bp.route("/customer/login", methods=["POST"])
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


@api_internal_bp.route("/customer/<customer_number>/billing")
def customer_billing(customer_number: str) -> Response:
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    readings = (
        MeterReading.query.filter_by(customer_number=customer_number)
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .order_by(desc(MeterReading.timestamp))
        .all()
    )

    payments = (
        Billing.query.filter_by(customer_number=customer_number)
        .order_by(desc(Billing.payment_timestamp))
        .limit(10)
        .all()
    )

    latest_reading = readings[0] if readings else None
    last_reading = readings[1] if len(readings) > 1 else None

    consumption = float(latest_reading.reading_value) - float(last_reading.reading_value) if latest_reading and last_reading else 0
    water_bill, bill_breakdown = compute_water_bill(consumption) if consumption > 0 else (0.0, [])

    def rd(d):
        return round(float(d), 2) if d is not None else 0.0

    unpaid_bills = []
    for b in Billing.query.filter_by(customer_number=customer_number, is_paid=False).order_by(Billing.date_created.asc()).all():
        ensure_penalty(b)
        reading = MeterReading.query.get(b.reading_id) if b.reading_id else None
        month_label = reading.timestamp.strftime("%B %Y") if reading else "Unknown"
        unpaid_bills.append({
            "month": month_label,
            "amount": rd(b.billed_amount),
            "penalty": rd(b.penalty),
            "timestamp": reading.timestamp.isoformat() if reading else (b.created_at.isoformat() if b.created_at else None),
        })

    total_unpaid = sum(b["amount"] for b in unpaid_bills)
    total_penalties = sum(b["penalty"] for b in unpaid_bills)
    total_carryover = float(db.session.query(db.func.sum(Billing.carryover_offset)).filter_by(customer_number=customer_number).scalar() or 0)
    carryover = abs(total_carryover)
    balance = total_carryover
    total_due = max(0, total_unpaid + total_penalties - balance)

    due_date = None
    days_remaining = None
    if unpaid_bills:
        ts = unpaid_bills[0].get("timestamp")
        if ts:
            due_dt = datetime.fromisoformat(ts) + timedelta(days=7)
            due_date = due_dt.strftime("%m-%d-%Y")
            days_remaining = max(0, (due_dt - datetime.utcnow()).days)

    pending_xendit = XenditTransaction.query.filter_by(customer_number=customer_number, status="PENDING").order_by(XenditTransaction.date_created.desc()).first()

    from models import PaymentMethod
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.sort_order).all()

    def reading_to_dict(r):
        if not r:
            return None
        return {
            "reading_value": float(r.reading_value),
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "token": {
                "staff": {
                    "name": r.token.staff.name if r.token and r.token.staff else "Unknown"
                }
            } if r.token else {"staff": {"name": "Unknown"}},
        }

    return jsonify({
        "customer": {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address or "",
            "contact_number": customer.contact_number or "",
            "email": customer.email or "",
            "meter_serial_number": customer.meter_serial_number or "",
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
        },
        "latest_reading": reading_to_dict(latest_reading),
        "last_reading": reading_to_dict(last_reading),
        "consumption": round(consumption, 2),
        "bill_breakdown": bill_breakdown,
        "original_water_bill": rd(water_bill),
        "unpaid_bills": unpaid_bills,
        "total_unpaid": round(total_unpaid, 2),
        "total_penalties": round(total_penalties, 2),
        "carryover": round(carryover, 2),
        "balance": round(balance, 2),
        "total_due": round(total_due, 2),
        "due_date": due_date,
        "days_remaining": days_remaining,
        "PRICING_TIERS": PRICING_TIERS,
        "recent_readings": [reading_to_dict(r) for r in readings[:5]],
        "recent_payments": [
            {
                "receipt_number": p.receipt_number,
                "paid_amount": rd(p.paid_amount),
                "timestamp": p.payment_timestamp.isoformat() if p.payment_timestamp else None,
            } for p in payments
        ],
        "latest_unpaid": unpaid_bills[0] if unpaid_bills else None,
        "pending_xendit": {
            "status": pending_xendit.status,
            "amount": rd(pending_xendit.amount),
        } if pending_xendit else None,
        "payment_methods": [
            {
                "code": pm.code,
                "label": pm.label,
                "sort_order": pm.sort_order,
                "fee_percent": rd(pm.fee_percent),
                "fee_flat": rd(pm.fee_flat),
                "fee_minimum": rd(pm.fee_minimum),
                "xendit_fee": rd(pm.xendit_fee),
            } for pm in payment_methods
        ],
    })


@api_internal_bp.route("/customer/<customer_number>/readings")
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

    from fee_service import calculate_fee
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

