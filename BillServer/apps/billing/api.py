from __future__ import annotations

import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime

from flask import Response, current_app, jsonify, make_response, request, url_for
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from apps import cache, cache_lock, csrf, db
from apps.billing import blueprint
from apps.models import ApiKey, Billing, Customer, MeterReading, Staff, XenditTransaction
from apps.pricing import compute_water_bill
from apps.services.billing_service import ensure_penalty
from apps.services.fee_service import calculate_fee
from apps.services.payment_service import recalc_cumulative_balance, submit_payment

_RATE_LIMIT = 10
_RATE_WINDOW = 60


def _check_rate_limit(ip: str) -> bool:
    cache_key = f"rl:billing:{ip}"
    with cache_lock:
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
    if last_billing and not current_app.config.get("DEBUG_ENABLED"):
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


def _xendit_api_key() -> str:
    key = os.environ.get("XENDIT_API_KEY", "")
    if not key or key == "your-xendit-secret-api-key":
        return ""
    return key


PAYMENT_CHANNEL_MAP: dict[str, list[str]] = {
    "gcash_ewallet": ["GCASH"],
    "maya_ewallet": ["PAYMAYA"],
    "grabfpay": ["GRABPAY"],
    "shopeepay": ["SHOPEEPAY"],
    "card_domestic": ["CARDS"],
    "card_international": ["CARDS"],
    "bpi_directdebit": ["BPI"],
    "ubp_directdebit": ["UBP"],
    "rcbc_directdebit": ["RCBC"],
    "online_banking": ["BPI", "BDO_EPAY", "UBP"],
    "7eleven_otc": ["OTC"],
    "cebuana_otc": ["OTC"],
    "ecpay_otc": ["OTC"],
    "lbc_otc": ["OTC"],
    "mlhuillier_otc": ["OTC"],
    "palawan_otc": ["OTC"],
    "robinsons_otc": ["OTC"],
    "sm_otc": ["OTC"],
    "ussc_otc": ["OTC"],
    "qrph": ["QRPH"],
    "billease": ["BILLEASE"],
    "virtual_account": ["VIRTUAL_ACCOUNT"],
}


_XENDIT_TIMEOUT = 30


def _create_xendit_session(
    amount: float,
    reference_id: str,
    description: str,
    success_url: str,
    cancel_url: str,
    channels: list[str],
    customer_number: str,
    customer_name: str,
    customer_email: str = "",
    customer_phone: str = "",
) -> dict:
    api_key = _xendit_api_key()
    if not api_key:
        raise RuntimeError("Xendit API key not configured")

    names = (customer_name or customer_number).strip().split(" ", 1)
    given_names = names[0] or customer_number
    surname = names[1] if len(names) > 1 else ""

    payload = {
        "reference_id": reference_id,
        "session_type": "PAY",
        "mode": "PAYMENT_LINK",
        "amount": amount,
        "currency": "PHP",
        "country": "PH",
        "allowed_payment_channels": channels,
        "success_return_url": success_url,
        "cancel_return_url": cancel_url,
        "description": description,
        "customer": {
            "reference_id": customer_number,
            "type": "INDIVIDUAL",
            "individual_detail": {
                "given_names": given_names,
            },
        },
    }

    if surname:
        payload["customer"]["individual_detail"]["surname"] = surname
    if customer_email:
        payload["customer"]["email"] = customer_email
    if customer_phone:
        payload["customer"]["mobile_number"] = customer_phone

    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req = urllib.request.Request(
        "https://api.xendit.co/sessions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=_XENDIT_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _get_xendit_session(session_id: str) -> dict:
    api_key = _xendit_api_key()
    if not api_key:
        raise RuntimeError("Xendit API key not configured")

    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req = urllib.request.Request(
        f"https://api.xendit.co/sessions/{session_id}",
        headers={"Authorization": f"Basic {auth}"},
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=_XENDIT_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


@blueprint.route("/api/<customer_number>/create-invoice", methods=["POST"])
@csrf.exempt
def create_xendit_invoice(customer_number: str) -> Response:
    if not _verify_billing_cookie(customer_number):
        return jsonify({"error": "Unauthorized"}), 403

    key = _xendit_api_key()
    if not key:
        return jsonify({"error": "Xendit is not configured. Set XENDIT_API_KEY in .env"}), 503

    stale = XenditTransaction.query.filter_by(
        customer_number=customer_number, status="PENDING"
    ).all()
    for s in stale:
        s.status = "EXPIRED"
        s.error_message = "Superseded by new payment link"
    if stale:
        db.session.commit()

    customer = (
        Customer.query
        .filter_by(customer_number=customer_number)
        .with_for_update()
        .first()
    )
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    data = request.get_json() or {}
    amount = data.get("amount", 0)
    if not amount or amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    payment_method = data.get("payment_method", "")
    if not payment_method:
        return jsonify({"error": "Payment method is required"}), 400

    fee_rate, fee_amount = calculate_fee(float(amount), payment_method)
    total_amount = round(float(amount) + fee_amount, 2)

    external_id = f"wbs-{customer_number}-{int(datetime.utcnow().timestamp())}-{secrets.token_hex(4)}"

    success_url = url_for(
        "billing_blueprint.billing_page",
        customer_number=customer_number,
        _external=True,
    )
    failure_url = url_for(
        "billing_blueprint.billing_page",
        customer_number=customer_number,
        _external=True,
    )

    channels = PAYMENT_CHANNEL_MAP.get(payment_method, [])
    if not channels:
        return jsonify({"error": f"Unknown payment method: {payment_method}"}), 400

    try:
        session = _create_xendit_session(
            amount=total_amount,
            reference_id=external_id,
            description=f"Water bill payment - {customer.name}",
            success_url=success_url,
            cancel_url=failure_url,
            channels=channels,
            customer_number=customer_number,
            customer_name=customer.name or customer_number,
            customer_email=customer.email or "",
            customer_phone=customer.contact_number or "",
        )

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

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return jsonify({"error": f"Xendit error: {error_body}"}), 502
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


def _get_xendit_staff() -> Staff | None:
    return Staff.query.filter_by(username="xendit").first()


def _process_xendit_payment(txn: XenditTransaction) -> bool:
    if txn.status != "PENDING":
        return False

    customer = Customer.query.filter_by(customer_number=txn.customer_number).first()
    if not customer:
        txn.status = "FAILED"
        txn.error_message = "Customer not found"
        db.session.commit()
        return False

    staff = _get_xendit_staff()
    if not staff:
        txn.status = "FAILED"
        txn.error_message = "Xendit system user not found"
        db.session.commit()
        return False

    try:
        amount = float(txn.amount)
        result, error, status = submit_payment(
            txn.customer_number, amount, staff.id
        )
        if error:
            txn.status = "FAILED"
            txn.error_message = error
            db.session.commit()
            return False

        txn.status = "PAID"
        txn.receipt_number = result.get("receipt_number")
        txn.billing_receipt = result.get("receipt_number")
        db.session.commit()
        current_app.logger.info(
            "Xendit payment processed: receipt=%s customer=%s amount=%.2f",
            txn.receipt_number, txn.customer_number, amount,
        )
        return True
    except Exception as e:
        current_app.logger.error(
            "Payment processing failed for %s: %s", txn.xendit_pr_id, str(e)
        )
        # Rollback discards any billing changes from submit_payment's flush.
        # merge() re-attaches the txn to the session after rollback expires it.
        db.session.rollback()
        txn = db.session.merge(txn)
        txn.status = "FAILED"
        txn.error_message = str(e)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False


def _reverse_xendit_payment(txn: XenditTransaction) -> bool:
    if txn.status != "PAID":
        return False

    billing_receipt = txn.billing_receipt
    if not billing_receipt:
        txn.status = "REVERSED"
        txn.error_message = "No billing receipt to reverse"
        db.session.commit()
        return True

    bills = Billing.query.filter_by(receipt_number=billing_receipt).with_for_update().all()
    for b in bills:
        b.is_paid = False
        b.paid_amount = 0
        b.receipt_number = None
        b.cashier_id = None
        b.payment_timestamp = None
        b.date_paid = None
        b.carryover_offset = 0

    recalc_cumulative_balance(txn.customer_number)

    txn.status = "REVERSED"
    txn.reversed_at = datetime.utcnow()
    db.session.commit()

    current_app.logger.info(
        "Xendit payment reversed: receipt=%s customer=%s",
        billing_receipt, txn.customer_number,
    )
    return True


@blueprint.route("/api/xendit-webhook", methods=["POST"])
@csrf.exempt
def xendit_webhook() -> Response:
    expected_token = os.environ.get("XENDIT_WEBHOOK_TOKEN", "")
    if expected_token and expected_token != "your-xendit-webhook-verification-token":
        received_token = request.headers.get("x-callback-token", "")
        if not received_token or received_token != expected_token:
            return jsonify({"error": "Invalid webhook token"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    event = data.get("event", "")
    payload = data.get("data", {})

    # Handle Sessions webhook
    if event == "payment_session.completed":
        session_id = payload.get("payment_session_id", "")
        if not session_id:
            return jsonify({"error": "No session ID"}), 400

        txn = XenditTransaction.query.filter_by(xendit_pr_id=session_id).with_for_update().first()
        if not txn:
            return jsonify({"error": "Transaction not found"}), 404

        pr_id = payload.get("payment_request_id", "")
        if pr_id:
            txn.xendit_pr_id = pr_id

        current_app.logger.info(
            "Xendit webhook: event=%s session_id=%s pr_id=%s status=%s",
            event, session_id, pr_id, txn.status,
        )

        if txn.status != "PAID":
            payment_id = payload.get("payment_id", "")
            if payment_id:
                txn.xendit_payment_id = payment_id
            _process_xendit_payment(txn)

        return jsonify({"status": "ok"})

    # Legacy webhooks (Payment Request / Invoice)
    pr_id = payload.get("payment_request_id") or payload.get("id")

    if not pr_id:
        return jsonify({"error": "No payment request ID"}), 400

    txn = XenditTransaction.query.filter_by(xendit_pr_id=pr_id).with_for_update().first()
    if not txn:
        return jsonify({"error": "Transaction not found"}), 404

    current_app.logger.info("Xendit webhook: event=%s pr_id=%s status=%s", event, pr_id, txn.status)

    if event in ("payment.succeeded", "invoice.paid"):
        if txn.status != "PAID":
            payment_id = payload.get("id", "")
            if payment_id:
                txn.xendit_payment_id = payment_id
            _process_xendit_payment(txn)
    elif event in ("payment.failed", "invoice.expired"):
        if txn.status == "PENDING":
            txn.status = "FAILED"
            txn.error_message = "Payment failed or expired"
            db.session.commit()
    elif event in ("payment.reversed", "payment.chargeback"):
        _reverse_xendit_payment(txn)
    else:
        current_app.logger.info("Ignored webhook event: %s", event)

    return jsonify({"status": "ok"})


def reconcile_xendit_payments(app) -> None:
    from flask import current_app

    threshold = datetime.utcnow().timestamp() - 300
    pending = XenditTransaction.query.filter_by(
        status="PENDING"
    ).with_for_update(skip_locked=True).all()

    pending = [
        t for t in pending
        if t.date_created and t.date_created.timestamp() < threshold
    ]

    if not pending:
        return

    key = _xendit_api_key()
    if not key:
        current_app.logger.warning("Reconciliation skipped: Xendit not configured")
        return

    for txn in pending:
        try:
            session_id = txn.xendit_pr_id if txn.xendit_pr_id and txn.xendit_pr_id.startswith("ps-") else None
            if session_id:
                response = _get_xendit_session(session_id)
                status = response.get("status", "")
                current_app.logger.info(
                    "Reconciliation (session): %s -> status=%s", session_id, status
                )
                if status == "COMPLETED":
                    pr_id = response.get("payment_request_id", "")
                    if pr_id:
                        txn.xendit_pr_id = pr_id
                    payment_id = response.get("payment_id", "")
                    if payment_id:
                        txn.xendit_payment_id = payment_id
                    _process_xendit_payment(txn)
                elif status in ("EXPIRED", "CANCELED"):
                    txn.status = "FAILED"
                    txn.error_message = f"Session {status.lower()} (reconciled)"
                    db.session.commit()
            else:
                try:
                    import xendit
                    from xendit.apis import PaymentRequestApi
                    xendit.set_api_key(key)
                    client = xendit.ApiClient()
                    api_instance = PaymentRequestApi(client)
                    response = api_instance.get_payment_request_by_id(txn.xendit_pr_id)
                    status = getattr(response, 'status', None)
                    current_app.logger.info(
                        "Reconciliation: %s -> Xendit status=%s", txn.xendit_pr_id, status
                    )
                    if status and str(status) in ("SUCCEEDED", "PAID", "SETTLED"):
                        payment_id = getattr(response, 'id', '')
                        if payment_id:
                            txn.xendit_payment_id = str(payment_id)
                        _process_xendit_payment(txn)
                    elif status and str(status) in ("FAILED", "EXPIRED"):
                        txn.status = "FAILED"
                        txn.error_message = f"Payment failed (reconciled: {status})"
                        db.session.commit()
                    elif status and str(status) == "REVERSED":
                        _reverse_xendit_payment(txn)
                except Exception as inner_e:
                    current_app.logger.error(
                        "PR reconciliation error for %s: %s", txn.xendit_pr_id, inner_e
                    )
        except Exception as e:
            current_app.logger.error(
                "Reconciliation error for %s: %s", txn.xendit_pr_id, str(e)
            )
