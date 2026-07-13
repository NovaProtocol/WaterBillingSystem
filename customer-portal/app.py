import os, sys
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

csrf = CSRFProtect()

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

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
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__, template_folder='templates')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['WTF_CSRF_ENABLED'] = True
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    prefix = _validate_prefix('REVERSE_PROXY_PUBLIC_PREFIX')
    _apply_prefix_middleware(app, prefix)
    csrf.init_app(app)

    from routes import customer_bp
    app.register_blueprint(customer_bp)

    @app.context_processor
    def inject_prefix():
        return {'REVERSE_PROXY_PUBLIC_PREFIX': prefix}

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
