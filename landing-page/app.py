import os, sys
from flask import Flask, render_template, request
from shared.logger import attach_sqlite_logging

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'DEPLOYMENT_TYPE')

    from shared.config import shared_static_dir
    app = Flask(__name__, template_folder='templates', static_folder=shared_static_dir(), static_url_path='/static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-not-secure')

    from routes import landing_blueprint
    app.register_blueprint(landing_blueprint)

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    @app.route('/404')
    def not_found_page():
        return render_template('landing/404.html'), 404

    @app.errorhandler(404)
    def not_found(e):
        return render_template('landing/404.html'), 404

    attach_sqlite_logging('landing-page')

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
