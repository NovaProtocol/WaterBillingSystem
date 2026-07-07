from __future__ import annotations

from datetime import datetime

from flask import Response, current_app, jsonify, request

from apps import db
from apps.api import blueprint
from apps.api.utils import resolve_api_key
from apps.models import Config, Customer, NfcTag


@blueprint.route("/nfc/config")
def nfc_config() -> Response:
    api_key = resolve_api_key()
    if not api_key or not api_key.is_active:
        return jsonify({"error": "Authentication required"}), 401
    if (
        not api_key.staff
        or not (
            api_key.staff.can_read_meters or api_key.staff.can_enroll_customer
        )
    ):
        return jsonify({"error": "Permission denied"}), 403

    gen_row = Config.query.filter_by(key="nfc_generation").first()
    generation = int(gen_row.value) if gen_row else 0

    return jsonify({
        "nfc_pwd_secret": current_app.config["NFC_PWD_SECRET"],
        "nfc_generation": generation,
    })


@blueprint.route("/nfc/clear", methods=["POST"])
def nfc_clear() -> Response:
    api_key = resolve_api_key()
    if not api_key or not api_key.is_active:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_enroll_customer:
        return jsonify({"error": "Permission denied"}), 403

    count = NfcTag.query.delete()

    gen_row = Config.query.filter_by(key="nfc_generation").first()
    if gen_row:
        gen_row.value = str(int(gen_row.value) + 1)
    else:
        db.session.add(Config(key="nfc_generation", value="1"))

    Customer.query.update(
        {Customer.date_modified: datetime.utcnow()},
        synchronize_session=False,
    )

    db.session.commit()

    return jsonify({"cleared": count, "message": f"Cleared {count} NFC tag(s)"})


@blueprint.route("/nfc/tags")
def nfc_tags() -> Response:
    api_key = resolve_api_key()
    if not api_key or not api_key.is_active:
        return jsonify({"error": "Authentication required"}), 401
    if not api_key.staff or not api_key.staff.can_read_meters:
        return jsonify({"error": "Permission denied"}), 403

    tags = NfcTag.query.order_by(NfcTag.date_created.desc()).all()
    return jsonify({
        "tags": [
            {
                "uid": t.uid,
                "customer_number": t.customer_number,
            }
            for t in tags
        ]
    })


@blueprint.route("/nfc/sync", methods=["POST"])
def nfc_sync() -> Response:
    api_key = resolve_api_key()
    if not api_key or not api_key.is_active:
        return jsonify({"error": "Authentication required"}), 401

    if not api_key.staff.can_enroll_customer:
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"error": "Invalid JSON body"}), 400
    enrollments = data.get("enrollments", [])
    if not isinstance(enrollments, list):
        return jsonify({"error": "enrollments must be a list"}), 400

    synced = 0
    errors: list[dict] = []

    for idx, item in enumerate(enrollments):
        uid = item.get("uid", "").strip()
        customer_number = item.get("customer_number", "").strip()

        if not uid or not customer_number:
            errors.append({"index": idx, "error": "uid and customer_number required"})
            continue

        existing = NfcTag.query.filter_by(uid=uid).first()
        if existing:
            if existing.customer_number != customer_number:
                existing.customer_number = customer_number
                existing.enrolled_by_id = api_key.staff_id
                synced += 1
            else:
                synced += 1
        else:
            new_tag = NfcTag(
                uid=uid,
                customer_number=customer_number,
                enrolled_by_id=api_key.staff_id,
            )
            db.session.add(new_tag)
            synced += 1

        # Touch customer's date_modified so change detection picks it up
        customer = Customer.query.filter_by(customer_number=customer_number).first()
        if customer:
            customer.date_modified = datetime.utcnow()

    db.session.commit()

    return jsonify({"synced": synced, "total": len(enrollments), "errors": errors})
