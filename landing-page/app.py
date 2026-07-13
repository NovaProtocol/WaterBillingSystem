import os, sys
from flask import Flask
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

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
    app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-not-secure')

    prefix = _validate_prefix('REVERSE_PROXY_PUBLIC_PREFIX')
    _apply_prefix_middleware(app, prefix)
    csrf.init_app(app)

    @app.context_processor
    def inject_prefix():
        return {'REVERSE_PROXY_PUBLIC_PREFIX': prefix}

    from routes import landing_blueprint
    app.register_blueprint(landing_blueprint)

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
