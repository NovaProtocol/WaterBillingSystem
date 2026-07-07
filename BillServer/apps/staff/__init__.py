from __future__ import annotations

from flask import Blueprint

blueprint = Blueprint(
    "staff_blueprint", __name__, url_prefix="/staff", template_folder="templates"
)
