from __future__ import annotations

from flask import Blueprint

blueprint = Blueprint("api_blueprint", __name__, url_prefix="/api")
