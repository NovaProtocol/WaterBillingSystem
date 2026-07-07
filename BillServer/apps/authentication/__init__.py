from __future__ import annotations

from flask import Blueprint

blueprint = Blueprint(
    "authentication_blueprint", __name__, url_prefix="", template_folder="templates"
)
