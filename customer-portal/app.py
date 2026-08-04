import os, sys
from flask import Flask, request
from shared.logger import attach_sqlite_logging

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE')

    from shared.config import shared_static_dir, shared_templates_dir
    from jinja2 import ChoiceLoader, FileSystemLoader
    app = Flask(__name__, template_folder='templates', static_folder=shared_static_dir(), static_url_path='/static')
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(app.template_folder),
        FileSystemLoader(shared_templates_dir()),
    ])
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    from pages import pages_bp
    from api_routes import api_bp
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    @app.route('/health')
    def health():
        return {'status': 'ok'}


    attach_sqlite_logging('customer-portal')

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
