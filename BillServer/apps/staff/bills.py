from __future__ import annotations

from flask import Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from apps.models import Billing
from apps.services.payment_service import drop_payment as service_drop_payment
from apps.staff import blueprint


@blueprint.route("/manage-billing")
def manage_billing() -> Response | str:
    if not current_user.is_authenticated or (
        not current_user.can_drop_payment
        and not current_user.can_manage_billing
        and not current_user.can_drop_reading
    ):
        return redirect(url_for("staff_blueprint.login"))
    return render_template("staff/manage_billing.html")


@blueprint.route("/manage-billing/undo-payment/<int:payment_id>", methods=["POST"])
def undo_payment(payment_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_drop_payment:
        return jsonify({"error": "Unauthorized"}), 403
    billing = Billing.query.get_or_404(payment_id)
    if not billing.is_paid:
        return jsonify({"error": "Bill is not paid"}), 400

    data = request.get_json()
    reason = (data.get("reason", "") or "").strip()
    if not reason:
        return jsonify({"error": "Reason is required"}), 400

    result = service_drop_payment(payment_id, current_user.id, reason)
    if result and "error" in result:
        return jsonify(result), 400

    return jsonify(result or {"message": "Payment undone"})

