from flask import Blueprint

blueprint = Blueprint(
    "landing_blueprint", __name__, url_prefix="", template_folder="templates"
)
