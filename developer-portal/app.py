import os, sys
from flask import Flask, session, request
from shared.logger import attach_sqlite_logging
from flask_login import LoginManager
login_manager = LoginManager()

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

class Staff:
    def __init__(self, data: dict):
        self.id = data.get('id')
        self.username = data.get('username')
        self.is_superuser = data.get('username') == 'superuser'
        self.is_active = True
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE', 'GATEKEEPER_INTERNAL')

    app = Flask(__name__, template_folder='templates', static_url_path='/developer/static')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(staff_id):
        data = session.get('staff_data')
        if data and str(data.get('id')) == str(staff_id):
            return Staff(data)
        return None

    from routes import debug_bp
    app.register_blueprint(debug_bp)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'debug': 'enabled'}

    from shared.gatekeeper import gatekeeper_check
    app.before_request(gatekeeper_check)

    attach_sqlite_logging('developer-portal')

    import logging
    http_logger = logging.getLogger('http')

    @app.after_request
    def log_request(response):
        container = request.headers.get('X-Container-Name', '-')
        http_logger.info(
            f"{request.method} {request.path} {response.status_code}",
            extra={'http': {
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'remote_addr': request.remote_addr,
                'container': container,
            }}
        )
        return response

    return app
