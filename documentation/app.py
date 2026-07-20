import os, sys
from flask import Flask, send_file, abort, request

SITE_DIR = os.path.join(os.path.dirname(__file__), 'site')

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'DEPLOYMENT_TYPE', 'GATEKEEPER_INTERNAL')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    @app.route('/', defaults={'path': 'index.html'})
    @app.route('/<path:path>')
    def serve_docs(path):
        if not path:
            path = 'index.html'

        parts = path.rstrip('/')
        candidates = [parts, os.path.join(parts, 'index.html'), parts + '.html']

        for c in candidates:
            full = os.path.normpath(os.path.join(SITE_DIR, c))
            if full.startswith(SITE_DIR) and os.path.isfile(full):
                return send_file(full)

        abort(404)

    from shared.gatekeeper import gatekeeper_check

    @app.before_request
    def docs_gatekeeper():
        if request.path.startswith('/assets/'):
            return
        return gatekeeper_check()

    return app
