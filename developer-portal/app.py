import os, sys
from flask import Flask, session
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

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
        self.is_superuser = data.get('is_superuser', False)
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

def _validate_prefix(name):
    prefix = os.environ.get(name)
    if prefix is None:
        print(f"FATAL: {name} is not set.")
        sys.exit(1)
    prefix = prefix.rstrip('/')
    if prefix and not prefix.startswith('/'):
        print(f"FATAL: {name} must start with '/' (got: '{prefix}')")
        sys.exit(1)
    return prefix

def _apply_prefix_middleware(app, prefix):
    if not prefix:
        return
    class PrefixMiddleware:
        def __init__(self, wsgi_app, p):
            self.wsgi_app = wsgi_app
            self.prefix = p.rstrip('/')
        def __call__(self, environ, start_response):
            path = environ.get('PATH_INFO', '')
            if path.startswith(self.prefix):
                environ['PATH_INFO'] = path[len(self.prefix):]
            environ['SCRIPT_NAME'] = self.prefix
            return self.wsgi_app(environ, start_response)
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'PMA_URL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__, template_folder='templates')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    private_prefix = _validate_prefix('REVERSE_PROXY_PRIVATE_PREFIX')
    _apply_prefix_middleware(app, private_prefix)

    login_manager.init_app(app)

    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(staff_id):
        data = session.get('staff_data')
        if data and str(data.get('id')) == str(staff_id):
            return Staff(data)
        return None

    from routes import debug_bp
    app.register_blueprint(debug_bp)

    @app.context_processor
    def inject_prefix():
        return {'REVERSE_PROXY_PRIVATE_PREFIX': private_prefix}

    @app.route('/health')
    def health():
        return {'status': 'ok', 'debug': 'enabled'}

    return app
