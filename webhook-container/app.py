import os, sys
from flask import Flask

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'INTERNAL_API_KEY', 'API_BASE_URL', 'GATEKEEPER_INTERNAL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    from routes import webhook_bp
    app.register_blueprint(webhook_bp)

    from shared.gatekeeper import gatekeeper_check
    app.before_request(gatekeeper_check)

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
