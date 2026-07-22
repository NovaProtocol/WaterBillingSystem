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

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    from routes import webhook_bp
    app.register_blueprint(webhook_bp)

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    attach_sqlite_logging('webhook')

    import logging
    http_logger = logging.getLogger('http')

    @app.after_request
    def log_request(response):
        container = request.headers.get('X-Container-Name', '-')
        http_logger.info(
            f"{request.method} {request.path} {response.status_code}",
            extra={'http': {
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'remote_addr': request.remote_addr,
                'container': container,
            }}
        )
        return response

    return app
