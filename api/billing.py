from __future__ import annotations

from flask import Response, jsonify, request
from sqlalchemy import desc

from app import db
from __init__ import blueprint
from models import Billing, MeterReading
from billing_service import ensure_penalty
from services.payment_service import (
    drop_payment as service_drop_payment,
    submit_payment as service_submit_payment,
)
from utils import require_staff


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
def customer_billing_drop(customer_number: str) -> Response:
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
