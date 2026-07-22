import os, sys
from flask import Flask, send_file, abort, request
from shared.logger import attach_sqlite_logging

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

    attach_sqlite_logging('documentation')

    import logging
    http_logger = logging.getLogger('http')

    @app.after_request
    def log_request(response):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).strftime('%d/%b/%Y:%H:%M:%S %z')
        referrer = request.headers.get('Referer', '-')
        ua = request.headers.get('User-Agent', '-')
        msg = f'{request.remote_addr} - - [{now}] "{request.method} {request.path} {request.environ.get("SERVER_PROTOCOL", "HTTP/1.1")}" {response.status_code} {response.content_length or "-"} "{referrer}" "{ua}"'
        http_logger.info(msg, extra={
            'http': {
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'remote_addr': request.remote_addr,
                'container': request.headers.get('X-Container-Name', '-'),
            }
        })
        return response

    return app
