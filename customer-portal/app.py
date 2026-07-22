import os, sys
from flask import Flask, request
from shared.logger import attach_sqlite_logging

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE', 'GATEKEEPER_INTERNAL')

    app = Flask(__name__, template_folder='templates', static_url_path='/customer/static')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    from routes import customer_bp
    app.register_blueprint(customer_bp)

    @app.template_filter('timestamp_to_date')
    def timestamp_to_date(ts):
        if ts is None:
            return ''
        from datetime import datetime
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        s = str(ts).replace('T', ' ')[:19]
        try:
            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
        except ValueError:
            return s

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    from shared.gatekeeper import gatekeeper_check
    app.before_request(gatekeeper_check)

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
