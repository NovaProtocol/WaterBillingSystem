import os, sys
from flask import Flask, session
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

login_manager = LoginManager()
csrf = CSRFProtect()

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
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'PMA_URL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__, template_folder='templates')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    login_manager.init_app(app)

    csrf.init_app(app)
    app.config['WTF_CSRF_METHODS'] = []

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

    return app
