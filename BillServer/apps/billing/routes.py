from __future__ import annotations

from datetime import datetime, timedelta

from flask import Response, flash, redirect, render_template, request, url_for
from sqlalchemy import desc

from apps import db
from apps.billing import (
    api,  # noqa: F401
    blueprint,
)
from apps.models import Billing, Customer, MeterReading, XenditTransaction
from apps.pricing import PRICING_TIERS, compute_water_bill
from apps.services.billing_service import ensure_penalty


@blueprint.route("/")
def index() -> str:
    return render_template("billing/billing.html", segment="billing")


@blueprint.route("/<customer_number>")
def billing_page(customer_number: str) -> Response | str:
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer

    raw = request.cookies.get("billing_session", "")
    cookie_ok = False
    if raw:
        try:
            s = URLSafeTimedSerializer(current_app.secret_key, salt="billing-cookie")
            data = s.loads(raw, max_age=3600)
            cookie_ok = data.get("customer_number") == customer_number
        except Exception:
            cookie_ok = False
    if not cookie_ok:
        flash("Session expired. Please look up your account again.", "error")
        return redirect(url_for("landing_blueprint.index"))

    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        flash("Customer not found.", "error")
        return redirect(url_for("landing_blueprint.index"))

    readings = (
        MeterReading.query.filter_by(customer_number=customer_number)
        .order_by(desc(MeterReading.timestamp))
        .all()
    )

    payments = (
        Billing.query.filter_by(customer_number=customer_number)
        .order_by(desc(Billing.payment_timestamp))
        .limit(10)
        .all()
    )

    latest_reading = readings[0] if len(readings) > 0 else None
    last_reading = readings[1] if len(readings) > 1 else None

    consumption = float(
        float(latest_reading.reading_value) - float(last_reading.reading_value)
        if latest_reading and last_reading
        else 0
    )
    water_bill, bill_breakdown = compute_water_bill(consumption)

    billing_for_latest = (
        Billing.query.filter_by(reading_id=latest_reading.id).first()
        if latest_reading
        else None
    )
    latest_unpaid = bool(billing_for_latest and not billing_for_latest.is_paid) if latest_reading else False

    total_carryover = float(
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )
    carryover = abs(total_carryover)
    balance = total_carryover

    # Use stored billing data instead of recomputing from tiers
    unpaid_bills = []
    for bill in (
        Billing.query.filter_by(customer_number=customer_number, is_paid=False)
        .order_by(Billing.date_created.asc())
        .all()
    ):
        ensure_penalty(bill)
        reading = bill.reading
        month_label = reading.timestamp.strftime("%B %Y") if reading else "Unknown"
        unpaid_bills.append(
            {
                "month": month_label,
                "amount": round(float(bill.billed_amount), 2),
                "penalty": round(float(bill.penalty), 2),
                "timestamp": reading.timestamp if reading else bill.date_created,
            }
        )

    total_unpaid = sum(b["amount"] for b in unpaid_bills)
    total_penalties = sum(b["penalty"] for b in unpaid_bills)
    total_due = max(0, total_unpaid + total_penalties - balance)

    due_date = None
    days_remaining = None
    if unpaid_bills:
        due_dt = unpaid_bills[0]["timestamp"] + timedelta(days=7)
        due_date = due_dt.strftime("%m-%d-%Y")
        days_remaining = max(0, (due_dt - datetime.utcnow()).days)

    pending_xendit = (
        XenditTransaction.query.filter_by(
            customer_number=customer_number, status="PENDING"
        )
        .order_by(XenditTransaction.date_created.desc())
        .first()
    )

    from apps.models import PaymentMethod
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.sort_order).all()

    return render_template(
        "billing/billing.html",
        customer=customer,
        latest_reading=latest_reading,
        last_reading=last_reading,
        consumption=consumption,
        bill_breakdown=bill_breakdown,
        original_water_bill=water_bill,
        unpaid_bills=unpaid_bills,
        total_unpaid=total_unpaid,
        total_penalties=total_penalties,
        carryover=carryover,
        balance=balance,
        total_due=total_due,
        due_date=due_date,
        days_remaining=days_remaining,
        PRICING_TIERS=PRICING_TIERS,
        recent_readings=readings,
        recent_payments=payments,
        latest_unpaid=latest_unpaid,
        pending_xendit=pending_xendit,
        payment_methods=payment_methods,
    )
