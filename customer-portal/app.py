import os, sys
from flask import Flask

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

    return app
