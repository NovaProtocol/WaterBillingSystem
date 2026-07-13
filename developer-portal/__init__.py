from flask import Blueprint
debug_bp = Blueprint('debug', __name__, url_prefix='/developer', template_folder='templates')
