from __future__ import annotations

from flask import Blueprint

blueprint = Blueprint(
    "billing_blueprint", __name__, url_prefix="/billing", template_folder="templates"
)
