import os, sys
from flask import Flask

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY', 'GATEKEEPER_INTERNAL', 'DEPLOYMENT_TYPE')

    app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-not-secure')

    from routes import landing_blueprint
    app.register_blueprint(landing_blueprint)

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    from shared.gatekeeper import gatekeeper_check
    app.before_request(gatekeeper_check)

    return app
