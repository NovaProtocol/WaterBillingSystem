import os, sys, pytest, threading, time

os.environ.setdefault('SECRET_KEY', 'test-secret-key-32-chars-min!!')
os.environ.setdefault('DB_ENGINE', 'sqlite')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '3306')
os.environ.setdefault('DB_NAME', ':memory:')
os.environ.setdefault('DB_USERNAME', 'root')
os.environ.setdefault('DB_PASS', 'test')
os.environ.setdefault('NFC_PWD_SECRET', 'a' * 64)
os.environ.setdefault('XENDIT_API_KEY', 'test-xendit-key')
os.environ.setdefault('XENDIT_WEBHOOK_TOKEN', 'test-webhook-token')
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')
os.environ.setdefault('PYTHON_GIL', '1')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ.setdefault('INTERNAL_API_KEY', 'test-internal-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('PMA_URL', 'http://test:80')
os.environ.setdefault('SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api'))


@pytest.fixture(scope='session')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture(scope='session')
def api_app():
    from app import create_app, db
    app = create_app()
    with app.app_context():
        db.create_all()
        from models import Staff
        from werkzeug.security import generate_password_hash
        if not Staff.query.filter_by(username='superuser').first():
            staff = Staff(
                username='superuser', name='Superuser',
                password=generate_password_hash('superuser').encode('utf-8'),
                can_read_meters=True, can_accept_payment=True,
                can_enroll_customer=True, can_drop_reading=True,
                can_drop_payment=True, can_enroll_staff=True,
                can_manage_billing=True, is_active=True,
            )
            db.session.add(staff)
            db.session.commit()
    return app


@pytest.fixture(scope='session')
def api_url(api_app):
    import werkzeug.serving
    host = '127.0.0.1'
    port = 8765
    threading.Thread(target=werkzeug.serving.run_simple,
                     args=(host, port, api_app),
                     kwargs={'use_reloader': False, 'use_debugger': False},
                     daemon=True).start()
    time.sleep(1)
    return f'http://{host}:{port}'
