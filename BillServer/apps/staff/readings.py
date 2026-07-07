from __future__ import annotations

from flask import Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from apps.models import ApiKey, ManagementLog, Staff
from apps.services.reading_service import drop_reading as service_drop_reading
from apps.services.reading_service import edit_reading as service_edit_reading
from apps.staff import blueprint


@blueprint.route("/meter-reading")
def meter_reading() -> Response | str:
    if not current_user.is_authenticated or not current_user.can_read_meters:
        return redirect(url_for("staff_blueprint.login"))
    if current_user.can_drop_reading:
        keys = ApiKey.query.order_by(desc(ApiKey.date_created)).all()
    else:
        keys = (
            ApiKey.query.filter_by(staff_id=current_user.id)
            .order_by(desc(ApiKey.date_created))
            .all()
        )
    return render_template("staff/meter_reading.html", keys=keys)


@blueprint.route("/manage-reading")
def manage_reading() -> Response | str:
    if not current_user.is_authenticated or (
        not current_user.can_drop_reading and not current_user.can_manage_billing
    ):
        return redirect(url_for("staff_blueprint.login"))
    logs = (
        ManagementLog.query.filter_by(target_type="reading")
        .order_by(desc(ManagementLog.timestamp))
        .limit(50)
        .all()
    )
    staff_list = Staff.query.order_by(Staff.name).all()
    if current_user.can_drop_reading:
        tokens = (
            ApiKey.query.options(joinedload(ApiKey.staff))
            .order_by(desc(ApiKey.date_created))
            .all()
        )
    else:
        tokens = (
            ApiKey.query.options(joinedload(ApiKey.staff))
            .filter_by(staff_id=current_user.id)
            .order_by(desc(ApiKey.date_created))
            .all()
        )
    return render_template(
        "staff/manage_reading.html",
        logs=logs,
        staff_list=staff_list,
        tokens=tokens,
    )


@blueprint.route("/manage-reading/drop-reading/<int:reading_id>", methods=["POST"])
def drop_reading(reading_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_drop_reading:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    reason = data.get("reason", "").strip()
    service_drop_reading(reading_id, current_user.id, reason)

    return jsonify({"message": "Reading dropped"})


@blueprint.route("/manage-reading/edit-reading/<int:reading_id>", methods=["POST"])
def edit_reading(reading_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_manage_billing:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    try:
        new_value = float(data.get("reading_value", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid reading value"}), 400
    service_edit_reading(reading_id, new_value, current_user.id)

    return jsonify({"message": "Reading updated"})
