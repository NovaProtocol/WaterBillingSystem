from __future__ import annotations

from flask import Response, abort, render_template, request
from sqlalchemy import desc

from apps.landing import blueprint
from apps.models import Billing, Customer

MODEL_TEMPLATES: dict[str, str] = {
    "catherine-4": "landing/models/catherine-4.html",
    "bernice-4": "landing/models/bernice-4.html",
    "tristen": "landing/models/tristen.html",
    "sophia": "landing/models/sophia.html",
    "margarette-2": "landing/models/margarette-2.html",
    "claire-2": "landing/models/claire-2.html",
    "amelia-3": "landing/models/amelia-3.html",
}

MODELS: dict[str, dict] = {
    "catherine-4": {
        "name": "Model Catherine 4",
        "type": "2-Storey House",
        "bedrooms": 4,
        "bathrooms": 2,
        "garage": "1-Car Garage",
        "features": ["Kitchen Area", "Living Area", "Dining Area", "Family Area"],
        "image": "46640e4afb1006868c364b5172d51391.jpg",
        "description": "A spacious two-storey home with four bedrooms and a family area — perfect for families.",
    },
    "bernice-4": {
        "name": "Model Bernice 4",
        "type": "2-Storey House",
        "bedrooms": 4,
        "bathrooms": 2,
        "garage": "1-Car Garage",
        "features": ["Kitchen Area", "Living Area", "Dining Area", "Family Area"],
        "image": "b2ac041f1088aef3d0b04632d3778d7a.jpg",
        "description": "A two-storey home with four bedrooms and a family area — ideal for families who value space.",
    },
    "tristen": {
        "name": "Model Tristen",
        "type": "Bungalow",
        "bedrooms": 3,
        "bathrooms": 2,
        "garage": "1-Car Garage",
        "features": ["Kitchen Area", "Living Area", "Dining Area", "Laundry Area"],
        "image": "59321c5a11e9fada9a10c58688812021.jpg",
        "description": "A bungalow with three bedrooms and a laundry area — single-level living at its finest.",
    },
    "sophia": {
        "name": "Model Sophia",
        "type": "Bungalow",
        "bedrooms": 4,
        "bathrooms": 2,
        "garage": "1-Car Garage",
        "features": ["Kitchen Area", "Living Area", "Dining Area"],
        "image": "277667f5a5d5cd3a61317509a0930c40.jpg",
        "description": "A spacious four-bedroom bungalow with generous living spaces and no stairs.",
    },
    "margarette-2": {
        "name": "Model Margarette 2",
        "type": "Socialized Housing",
        "bedrooms": 2,
        "bathrooms": 1,
        "garage": None,
        "features": ["Living Area", "Dining Area", "Kitchen Area", "Porch Area"],
        "image": "466b81dd012dea504f589a2c39f2f0b6.jpg",
        "description": "Affordable two-bedroom socialized housing with a porch — perfect for starting families.",
    },
    "claire-2": {
        "name": "Model Claire 2",
        "type": "Socialized Housing",
        "bedrooms": 2,
        "bathrooms": 1,
        "garage": None,
        "features": ["Living Area", "Dining Area", "Kitchen Area", "Porch Area"],
        "image": "0dbac0562ce14748ca094f28d6eb51e0.jpg",
        "description": "Cozy two-bedroom socialized housing with a porch — affordable living for new homeowners.",
    },
    "amelia-3": {
        "name": "Model Amelia 3",
        "type": "Bungalow",
        "bedrooms": 3,
        "bathrooms": 1,
        "garage": "1-Car Garage",
        "features": ["Living Area", "Dining Area", "Kitchen Area"],
        "image": "0e609c93043001dc0605dc7868f895b3.jpg",
        "description": "A practical bungalow with three bedrooms and a car garage. Smart living for modern families.",
    },
}


@blueprint.route("/offerings")
def offerings() -> str:
    return render_template("landing/offerings.html", models=MODELS)


@blueprint.route("/offerings/<slug>")
def model_detail(slug: str) -> str:
    template = MODEL_TEMPLATES.get(slug)
    if not template:
        abort(404)
    return render_template(template, models=MODELS, current_slug=slug)


@blueprint.route("/", methods=["GET", "POST"])
def index() -> Response | str:
    if request.method == "POST":
        customer_number = request.form.get("customer_number", "").strip()
        last_receipt = request.form.get("last_receipt", "").strip()

        if not customer_number:
            return render_template(
                "landing/index.html", models=MODELS, modal_error="Customer number is required."
            )

        customer = Customer.query.filter_by(customer_number=customer_number).first()

        if not customer:
            return render_template(
                "landing/index.html", models=MODELS, modal_error="Customer not found."
            )

        last_billing = (
            Billing.query.filter_by(customer_number=customer_number)
            .order_by(desc(Billing.payment_timestamp))
            .first()
        )
        if last_billing and last_billing.receipt_number != last_receipt:
            return render_template(
                "landing/index.html",
                models=MODELS,
                modal_error="Receipt number does not match our records.",
            )
        return render_template(
            "landing/index.html", models=MODELS, modal_success=True, customer=customer
        )

    return render_template("landing/index.html", models=MODELS)
