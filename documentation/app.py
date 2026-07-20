import os, sys
from flask import Flask, send_from_directory, abort, request

SITE_DIR = os.path.join(os.path.dirname(__file__), 'site')

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'DEPLOYMENT_TYPE', 'GATEKEEPER_INTERNAL')

    app = Flask(__name__, static_folder=SITE_DIR, static_url_path='')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    @app.route('/', defaults={'path': 'index.html'})
    @app.route('/<path:path>')
    def serve_docs(path):
        safe = os.path.join(SITE_DIR, path)
        if os.path.isfile(safe):
            return send_from_directory(SITE_DIR, path)

        index_path = os.path.join(path, 'index.html')
        if os.path.isfile(os.path.join(SITE_DIR, index_path)):
            return send_from_directory(SITE_DIR, index_path)

        html_path = path + '.html'
        if os.path.isfile(os.path.join(SITE_DIR, html_path)):
            return send_from_directory(SITE_DIR, html_path)

        abort(404)

    from shared.gatekeeper import gatekeeper_check

    @app.before_request
    def docs_gatekeeper():
        if request.path.startswith('/assets/'):
            return
        return gatekeeper_check()

    return app
