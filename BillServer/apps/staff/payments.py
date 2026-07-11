from __future__ import annotations

from datetime import datetime, timedelta

from flask import Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from apps import db
from apps.services.payment_service import (
    compute_cashier_tally,
    compute_nav_dates,
    parse_date_range,
)
from apps.services.payment_service import (
    submit_payment as service_submit_payment,
)
from apps.staff import blueprint


@blueprint.route("/payments")
def payments() -> Response | str:
    if not current_user.is_authenticated or not current_user.can_accept_payment:
        return redirect(url_for("staff_blueprint.login"))
    return render_template("staff/payments.html")


@blueprint.route("/payments/submit", methods=["POST"])
def submit_payment() -> Response:
    if not current_user.is_authenticated or not current_user.can_accept_payment:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    customer_number = data.get("customer_number", "").strip()
    amount = data.get("amount", 0)

    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid payment amount"}), 400

    result, error, status = service_submit_payment(
        customer_number, amount_float, current_user.id
    )
    if error:
        return jsonify({"error": error}), status
    db.session.commit()
    return jsonify(result), status


@blueprint.route("/cashier-tally")
def cashier_tally() -> Response | str:
    if not current_user.is_authenticated or not (
        current_user.can_accept_payment or current_user.can_manage_billing
    ):
        return redirect(url_for("staff_blueprint.login"))

    can_see_all = current_user.can_manage_billing
    period = request.args.get("period", "daily")
    today = datetime.utcnow()

    start_str = request.args.get("start_date") or request.args.get("date")
    end_str = request.args.get("end_date")
    group_days = request.args.get("group_days", 1, type=int)

    start, end = parse_date_range(period, start_str, end_str, today)

    staff_id = None if can_see_all else current_user.id
    tally, use_matrix = compute_cashier_tally(start, end, staff_id, group_days)
    nav = compute_nav_dates(period, start, end, today)

    return render_template(
        "staff/cashier_tally.html",
        tally=tally,
        display=nav["display"],
        prev_date=nav["prev_date"],
        next_date=nav["next_date"],
        is_today=nav["is_today"],
        period=period,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=(end - timedelta(days=1)).strftime("%Y-%m-%d"),
        nav_date=nav["nav_date"],
        use_matrix=use_matrix or False,
        group_days=group_days,
    )
