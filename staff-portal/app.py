import os, sys
from flask import Flask, session
from flask_login import LoginManager, login_user
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect

login_manager = LoginManager()
cache = Cache()
csrf = CSRFProtect()

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

class Staff:
    def __init__(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'CACHE_TYPE', 'DEPLOYMENT_TYPE')

    app = Flask(__name__, template_folder='templates')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['WTF_CSRF_ENABLED'] = os.environ.get('WTF_CSRF_ENABLED', 'True').lower() in ('true', '1', 'yes')

    login_manager.init_app(app)
    login_manager.login_view = 'staff_blueprint.login'

    cache_type = os.environ['CACHE_TYPE']
    app.config['CACHE_TYPE'] = cache_type
    cache.init_app(app)

    csrf.init_app(app)
    app.config['WTF_CSRF_METHODS'] = []

    @login_manager.user_loader
    def load_user(staff_id):
        data = session.get('staff_data')
        if data and str(data.get('id')) == str(staff_id):
            return Staff(data)
        return None

    from routes import staff_bp
    app.register_blueprint(staff_bp)

    @app.template_filter('datetimeformat')
    def datetimeformat(ts):
        if ts:
            from datetime import datetime
            return datetime.strptime(str(ts)[:19], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
        return ''

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
