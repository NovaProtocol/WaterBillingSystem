from __future__ import annotations

from datetime import datetime

from flask import Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from apps import db
from apps.models import Config, Customer, NfcTag
from apps.services.customer_service import (
    compute_batch_due,
    create_customer,
    get_customer_or_404,
    list_customers,
    toggle_active,
    update_customer,
)
from apps.staff import blueprint


@blueprint.route("/customers", methods=["GET"])
def customers() -> Response | str:
    if not current_user.is_authenticated or not current_user.can_enroll_customer:
        return redirect(url_for("staff_blueprint.login"))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = min(max(per_page, 10), 200)
    pagination = Customer.query.order_by(Customer.name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template(
        "staff/customers.html",
        customers=pagination.items,
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        pages=pagination.pages,
    )


@blueprint.route("/customers/create", methods=["POST"])
def customer_create() -> Response:
    if not current_user.is_authenticated or not current_user.can_enroll_customer:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    customer, error = create_customer(data)
    if error:
        status = 409 if "already exists" in error else 400
        return jsonify({"error": error}), status

    return (
        jsonify(
            {
                "message": "Customer enrolled",
                "customer_number": customer.customer_number,
            }
        ),
        201,
    )


@blueprint.route("/manage-customers", methods=["GET"])
def manage_customers() -> Response | str:
    if not current_user.is_authenticated or not current_user.can_enroll_customer:
        return redirect(url_for("staff_blueprint.login"))

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "name")
    sort_dir = request.args.get("sort_dir", "asc")

    pagination = list_customers(
        page=page, per_page=per_page, q=q or None, sort_by=sort_by, sort_dir=sort_dir
    )
    due_map = compute_batch_due(pagination.items)

    customers = pagination.items
    for customer in customers:
        customer.total_due = due_map.get(customer.customer_number, 0.0)

    if sort_by == "total_due":
        reverse = sort_dir == "desc"
        customers = sorted(customers, key=lambda c: c.total_due, reverse=reverse)

    nfc_tags = {
        t.customer_number: t.uid
        for t in NfcTag.query.filter(
            NfcTag.customer_number.in_([c.customer_number for c in customers])
        ).all()
    }

    return render_template(
        "staff/manage_customers.html",
        customers=customers,
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        pages=pagination.pages,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        nfc_tags=nfc_tags,
    )


@blueprint.route("/manage-customers/<int:customer_id>/edit", methods=["POST"])
def edit_customer(customer_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_enroll_customer:
        return jsonify({"error": "Unauthorized"}), 403

    customer = get_customer_or_404(customer_id)
    data = request.get_json()
    update_customer(customer, data)

    return jsonify({"message": "Customer updated"})


@blueprint.route("/manage-customers/<int:customer_id>/toggle-active", methods=["POST"])
def toggle_customer_active(customer_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_enroll_customer:
        return jsonify({"error": "Unauthorized"}), 403

    customer = get_customer_or_404(customer_id)
    toggle_active(customer)

    return jsonify(
        {
            "message": f'Customer {"deactivated" if not customer.is_active else "reactivated"}',
            "is_active": customer.is_active,
        }
    )


@blueprint.route("/manage-customers/<int:customer_id>/clear-nfc", methods=["POST"])
def clear_customer_nfc(customer_id: int) -> Response:
    if not current_user.is_authenticated or not current_user.can_enroll_customer:
        return jsonify({"error": "Unauthorized"}), 403

    customer = get_customer_or_404(customer_id)
    NfcTag.query.filter_by(customer_number=customer.customer_number).delete()

    gen_row = Config.query.filter_by(key="nfc_generation").first()
    if gen_row:
        gen_row.value = str(int(gen_row.value) + 1)
    else:
        db.session.add(Config(key="nfc_generation", value="1"))

    customer.date_modified = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": f"NFC mapping cleared for {customer.customer_number}"})
