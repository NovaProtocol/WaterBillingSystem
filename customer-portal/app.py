import os, sys
from flask import Flask

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__, template_folder='templates')
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    from routes import customer_bp
    app.register_blueprint(customer_bp)

    @app.template_filter('timestamp_to_date')
    def timestamp_to_date(ts):
        if ts:
            s = str(ts).replace('T', ' ')[:19]
            from datetime import datetime
            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
        return ''

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
