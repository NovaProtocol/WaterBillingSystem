import os
from flask import Flask

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-not-secure')

    from routes import landing_blueprint
    app.register_blueprint(landing_blueprint)

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
