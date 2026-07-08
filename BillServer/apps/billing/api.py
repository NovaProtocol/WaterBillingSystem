from __future__ import annotations

import secrets
import time
from datetime import datetime

from flask import Response, current_app, jsonify, make_response, request, url_for
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from apps import cache
from apps.billing import blueprint
from apps.models import ApiKey, Billing, Customer, MeterReading
from apps.pricing import compute_water_bill
from apps.services.billing_service import ensure_penalty

_RATE_LIMIT = 10
_RATE_WINDOW = 60


def _check_rate_limit(ip: str) -> bool:
    cache_key = f"rl:billing:{ip}"
    attempts: list[float] = cache.get(cache_key) or []
    now = time.time()
    attempts = [t for t in attempts if now - t < _RATE_WINDOW]
    if len(attempts) >= _RATE_LIMIT:
        return False
    attempts.append(now)
    cache.set(cache_key, attempts, timeout=_RATE_WINDOW + 30)
    return True


def _billing_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="billing-cookie")


def _verify_billing_cookie(customer_number: str) -> bool:
    raw = request.cookies.get("billing_session", "")
    if not raw:
        return False
    try:
        data = _billing_serializer().loads(raw, max_age=3600)
        return data.get("customer_number") == customer_number
    except Exception:
        return False


def _log_billing_access(endpoint: str, ip: str, customer_number: str, status: int) -> None:
    current_app.logger.info(
        "BILLING_ACCESS endpoint=%s ip=%s customer_number=%s status=%d",
        endpoint, ip, customer_number, status,
    )


@blueprint.route("/api/lookup", methods=["POST"])
def lookup_customer() -> Response:
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        return jsonify({"error": "Too many requests. Please try again later."}), 429

    data = request.get_json()
    customer_number = data.get("customer_number", "").strip()
    last_receipt = data.get("last_receipt", "").strip()

    if not customer_number:
        return jsonify({"error": "Customer number is required"}), 400

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    last_billing = (
        Billing.query.filter_by(customer_number=customer_number)
        .order_by(desc(Billing.payment_timestamp))
        .first()
    )
    if last_billing:
        if not last_receipt or last_billing.receipt_number != last_receipt:
            _log_billing_access("lookup", ip, customer_number, 403)
            return jsonify({"error": "Receipt number does not match our records"}), 403

    _log_billing_access("lookup", ip, customer_number, 200)
    return jsonify(
        {
            "customer_number": customer.customer_number,
            "name": customer.name,
            "address": customer.address,
            "contact_number": customer.contact_number,
            "email": customer.email,
            "x_coordinate": customer.x_coordinate,
            "y_coordinate": customer.y_coordinate,
            "cumulative_balance": float(customer.cumulative_balance or 0),
        }
    )


@blueprint.route("/api/confirm", methods=["POST"])
def confirm_customer() -> Response:
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        return jsonify({"error": "Too many requests. Please try again later."}), 429

    data = request.get_json()
    customer_number = data.get("customer_number", "").strip()

    if not customer_number:
        return jsonify({"error": "Customer number is required"}), 400

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        _log_billing_access("confirm", ip, customer_number, 404)
        return jsonify({"error": "Customer not found"}), 404

    _log_billing_access("confirm", ip, customer_number, 200)
    receipt_number = (
        "RCP-"
        + str(int(datetime.utcnow().timestamp()))
        + "-"
        + secrets.token_hex(8).upper()
    )

    session_data = _billing_serializer().dumps(
        {"customer_number": customer_number, "receipt_number": receipt_number}
    )
    resp = make_response(
        jsonify(
            {
                "redirect": url_for("billing_blueprint.billing_page", customer_number=customer_number),
                "receipt_number": receipt_number,
                "customer_number": customer_number,
            }
        )
    )
    resp.set_cookie(
        "billing_session", session_data, max_age=3600,
        httponly=True, samesite="Lax", secure=request.is_secure
    )
    return resp


@blueprint.route("/api/<customer_number>/readings")
def paginated_readings(customer_number: str) -> Response:
    if not _verify_billing_cookie(customer_number):
        return jsonify({"error": "Unauthorized"}), 403

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
            "date_created": r.date_created.isoformat() if r.date_created else None,
        }
        for r in pagination.items
    ]

    return jsonify(
        {
            "items": items,
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        }
    )


@blueprint.route("/api/<customer_number>/payments")
def paginated_payments(customer_number: str) -> Response:
    if not _verify_billing_cookie(customer_number):
        return jsonify({"error": "Unauthorized"}), 403

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

    return jsonify(
        {
            "items": [
                {
                    "id": b.id,
                    "receipt_number": b.receipt_number,
                    "paid_amount": float(b.paid_amount),
                    "cashier_id": b.cashier_id,
                    "cashier": (b.cashier.name or b.cashier.username) if b.cashier else None,
                    "timestamp": int(b.payment_timestamp.timestamp()) if b.payment_timestamp else 0,
                    "date_created": b.date_created.isoformat() if b.date_created else None,
                }
                for b in items
            ],
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
        }
    )


@blueprint.route("/api/<customer_number>/history")
def billing_history(customer_number: str) -> Response:
    if not _verify_billing_cookie(customer_number):
        return jsonify({"error": "Unauthorized"}), 403

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

        items.append(
            {
                "month": month_label,
                "month_key": month_key,
                "usage": consumption,
                "billed_amount": billed_amount,
                "paid_amount": paid_amount,
                "penalty": round(penalty, 2),
                "reading_id": curr.id,
                "timestamp": int(curr.timestamp.timestamp()),
            }
        )

    items.sort(key=lambda x: x["month_key"], reverse=True)

    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    return jsonify(
        {
            "items": page_items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
        }
    )
