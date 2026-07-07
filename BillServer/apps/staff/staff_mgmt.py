from __future__ import annotations

from flask import Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from apps import db
from apps.authentication.util import hash_pass
from apps.models import Staff
from apps.staff import blueprint


@blueprint.route("/staff", methods=["GET"])
def staff_list() -> Response | str:
    if not current_user.is_authenticated or not current_user.can_enroll_staff:
        return redirect(url_for("staff_blueprint.login"))
    staff = Staff.query.all()
    return render_template("staff/staff_list.html", staff=staff)


@blueprint.route("/staff/create", methods=["POST"])
def staff_create() -> Response:
    if not current_user.is_authenticated or not current_user.can_enroll_staff:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if Staff.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    staff = Staff(
        username=username,
        name=data.get("name", "").strip() or username,
        password=hash_pass(password),
        email=data.get("email", "").strip() or None,
        contact_number=data.get("contact_number", "").strip() or None,
        can_read_meters=data.get("can_read_meters", False),
        can_accept_payment=data.get("can_accept_payment", False),
        can_enroll_customer=data.get("can_enroll_customer", False),
        can_drop_reading=data.get("can_drop_reading", False),
        can_drop_payment=data.get("can_drop_payment", False),
        can_enroll_staff=data.get("can_enroll_staff", False),
        can_manage_billing=data.get("can_manage_billing", False),
    )
    db.session.add(staff)
    db.session.commit()

    return (
        jsonify(
            {"message": "Staff created", "username": staff.username, "name": staff.name}
        ),
        201,
    )


@blueprint.route("/staff/<int:staff_id>", methods=["GET", "POST"])
def staff_edit(staff_id: int) -> Response | str:
    if not current_user.is_authenticated or not current_user.can_enroll_staff:
        return redirect(url_for("staff_blueprint.login"))

    staff = Staff.query.get_or_404(staff_id)

    if request.method == "POST":
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username:
            return jsonify({"error": "Username is required"}), 400

        existing = Staff.query.filter(
            Staff.username == username, Staff.id != staff_id
        ).first()
        if existing:
            return jsonify({"error": "Username already exists"}), 409

        staff.username = username
        staff.name = data.get("name", "").strip() or username
        if password:
            staff.password = hash_pass(password)
        staff.email = data.get("email", "").strip() or None
        staff.contact_number = data.get("contact_number", "").strip() or None
        staff.can_read_meters = data.get("can_read_meters", False)
        staff.can_accept_payment = data.get("can_accept_payment", False)
        staff.can_enroll_customer = data.get("can_enroll_customer", False)
        staff.can_drop_reading = data.get("can_drop_reading", False)
        staff.can_drop_payment = data.get("can_drop_payment", False)
        staff.can_enroll_staff = data.get("can_enroll_staff", False)
        staff.can_manage_billing = data.get("can_manage_billing", False)
        staff.is_active = data.get("is_active", True)
        db.session.commit()

        return jsonify(
            {"message": "Staff updated", "username": staff.username, "name": staff.name}
        )

    return jsonify(
        {
            "id": staff.id,
            "username": staff.username,
            "name": staff.name,
            "email": staff.email,
            "contact_number": staff.contact_number,
            "can_read_meters": staff.can_read_meters,
            "can_accept_payment": staff.can_accept_payment,
            "can_enroll_customer": staff.can_enroll_customer,
            "can_drop_reading": staff.can_drop_reading,
            "can_drop_payment": staff.can_drop_payment,
            "can_enroll_staff": staff.can_enroll_staff,
            "can_manage_billing": staff.can_manage_billing,
            "is_active": staff.is_active,
        }
    )
