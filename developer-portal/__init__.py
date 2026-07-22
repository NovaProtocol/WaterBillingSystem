from flask import Blueprint
dev_bp = Blueprint('dev', __name__, url_prefix='/developer', template_folder='templates')
