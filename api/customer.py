from __future__ import annotations

from datetime import datetime, timedelta

from flask import Response, jsonify, request
from flask_login import current_user
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from app import db
from __init__ import blueprint
from models import ApiKey, Billing, Customer, MeterReading
from pricing import PRICING_TIERS
from services.billing_service import ensure_penalty


@blueprint.route("/customer/<customer_number>")
def customer_info(customer_number: str) -> Response:
    """Get full billing details for a specific customer.

    Accepts session auth (Flask-Login), Bearer token, or ?api_key= query param.
    Returns customer profile, latest reading, consumption, water bill breakdown,
    pricing tiers, penalties, due date, recent billing items, and payments.
    ---
    Auth: session OR API key
    """
    auth_header = request.headers.get("Authorization", "")
    api_key = request.args.get("api_key", "")
    api_key_obj = None
    if not current_user.is_authenticated:
        if auth_header.startswith("Bearer "):
            key = auth_header[7:]
            api_key_obj = ApiKey.query.filter_by(key=key, is_active=True).first()
        if not api_key_obj and api_key:
            api_key_obj = ApiKey.query.filter_by(key=api_key, is_active=True).first()
        if not api_key_obj or not api_key_obj.staff.can_read_meters:
            return jsonify({"error": "Authentication required"}), 401
    elif not current_user.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

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
        due_dt = datetime.utcfromtimestamp(unpaid_bills[0]["timestamp"]) + timedelta(days=7)
        due_date = due_dt.strftime("%m-%d-%Y")
        days_remaining = max(0, (due_dt - datetime.utcnow()).days)

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
        }
    )


@blueprint.route("/customer/<customer_number>/details")
def customer_details(customer_number: str) -> Response:
    """Get customer profile with recent reading history.

    Requires API key auth (Bearer token or ?api_key= param).
    Query param ?history=5 (default) controls how many past readings to include.
    Returns customer info plus the last N readings sorted newest-first.
    ---
    Auth: API key
    """
    from utils import resolve_api_key

    api_key = resolve_api_key()
    if not api_key:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff.can_read_meters:
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
