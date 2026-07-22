import os, sys, logging
from flask import Flask, request
from shared.logger import attach_sqlite_logging
from apps import db, cache

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('api')

def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)

def create_app():
    require_env('SECRET_KEY',
                'NFC_PWD_SECRET', 'XENDIT_API_KEY', 'XENDIT_WEBHOOK_TOKEN',
                'CACHE_TYPE', 'PYTHON_GIL', 'DEPLOYMENT_TYPE')
    if not os.environ.get('SQLALCHEMY_DATABASE_URI'):
        require_env('DB_ENGINE', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USERNAME', 'DB_PASS')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'SQLALCHEMY_DATABASE_URI',
        f"{os.environ['DB_ENGINE']}://{os.environ['DB_USERNAME']}:{os.environ['DB_PASS']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )
    if 'sqlite' not in app.config['SQLALCHEMY_DATABASE_URI']:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_size': 30, 'max_overflow': 30, 'pool_recycle': 3600,
        }

    db.init_app(app)
    cache.init_app(app, config={'CACHE_TYPE': os.environ['CACHE_TYPE']})

    app.config['NFC_PWD_SECRET'] = os.environ['NFC_PWD_SECRET']

    import routes.customer, routes.staff, routes.config, routes.debug, routes.system, routes.webhooks
    from __init__ import blueprint as api_bp
    from routes.webhooks import webhook_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(webhook_bp)

    with app.app_context():
        db.create_all()
        try:
            from migrate import run_migrations
            run_migrations()
        except Exception as e:
            logger.error(f"Migration failed: {e}")

        try:
            from services.staff_seeder import ensure_prereq_staff
            ensure_prereq_staff()
        except Exception as e:
            logger.error(f"Staff seeder failed: {e}")

        try:
            from fee_service import seed_payment_methods
            seed_payment_methods()
        except Exception as e:
            logger.error(f"Payment method seeder failed: {e}")

    @app.route('/health')
    def health():
        try:
            db.session.execute(db.text('SELECT 1'))
            return {'status': 'ok', 'db': 'connected'}
        except Exception as e:
            return {'status': 'degraded', 'db': str(e)}, 503

    attach_sqlite_logging('api')

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
