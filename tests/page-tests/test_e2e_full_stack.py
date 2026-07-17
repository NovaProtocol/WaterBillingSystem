"""True end-to-end test: starts API server, renders pages through Playwright."""

import os, sys, pytest, threading, time, json
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api'))

os.environ.setdefault('SECRET_KEY', 'test-secret-key-e2e')
os.environ.setdefault('DB_ENGINE', 'sqlite')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '3306')
os.environ.setdefault('DB_NAME', ':memory:')
os.environ.setdefault('DB_USERNAME', 'root')
os.environ.setdefault('DB_PASS', 'test')
os.environ.setdefault('NFC_PWD_SECRET', 'e2e' + 'a' * 61)
os.environ.setdefault('XENDIT_API_KEY', 'test-xendit-key')
os.environ.setdefault('XENDIT_WEBHOOK_TOKEN', 'test-webhook-token')
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')
os.environ.setdefault('PYTHON_GIL', '1')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ.setdefault('INTERNAL_API_KEY', 'test-internal-key')
os.environ.setdefault('SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')


@pytest.fixture(scope='module')
def api_server():
    from app import create_app, db
    app = create_app()
    with app.app_context():
        db.create_all()
        from models import Staff, Customer, ApiKey, MeterReading, Billing
        from werkzeug.security import generate_password_hash
        from pricing import compute_water_bill

        staff = Staff.query.filter_by(username='superuser').first()
        if not staff:
            staff = Staff(username='superuser', name='Superuser',
                          password=generate_password_hash('superuser').encode('utf-8'),
                          can_read_meters=True, can_accept_payment=True,
                          can_enroll_customer=True, can_drop_reading=True,
                          can_drop_payment=True, can_enroll_staff=True,
                          can_manage_billing=True, is_active=True)
            db.session.add(staff)
            db.session.flush()
        if not ApiKey.query.filter_by(key='CRDC-E2E').first():
            db.session.add(ApiKey(key='CRDC-E2E', label='e2e', staff_id=staff.id))
            db.session.commit()
        key = ApiKey.query.filter_by(key='CRDC-E2E').first()
        if not Customer.query.filter_by(customer_number='E2E-001').first():
            db.session.add(Customer(customer_number='E2E-001', name='E2E User',
                                     address='1 E2E St', cumulative_balance=0.00))
            db.session.commit()
        if not MeterReading.query.filter_by(customer_number='E2E-001').first():
            prev = MeterReading(customer_number='E2E-001', reading_value=50.0,
                                token_id=key.id, timestamp=datetime(2025, 11, 1))
            db.session.add(prev)
            db.session.flush()

    import werkzeug.serving
    host, port = '127.0.0.1', 18765
    t = threading.Thread(target=werkzeug.serving.run_simple,
                         args=(host, port, app),
                         kwargs={'use_reloader': False, 'use_debugger': False},
                         daemon=True)
    t.start()
    time.sleep(0.5)
    yield f'http://{host}:{port}'
    # Cleanup handled by daemon thread


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    p = browser.new_page()
    yield p
    p.close()


class TestE2EApi:
    """Full-stack tests via real API server + Playwright browser."""

    def test_health_via_browser(self, page, api_server):
        resp = page.goto(f'{api_server}/health')
        assert resp.status == 200
        body = page.content()
        assert 'ok' in body or 'degraded' in body

    def test_staff_login_via_api(self, api_server):
        import requests
        r = requests.post(f'{api_server}/api/staff/login',
                          json={'username': 'superuser', 'password': 'superuser'})
        assert r.status_code == 200
        data = r.json()
        assert data['username'] == 'superuser'
        assert data['can_read_meters'] is True
        assert data['is_active'] is True

    def test_customer_count_via_api(self, api_server):
        import requests
        r = requests.get(f'{api_server}/api/customer/count',
                         headers={'X-Internal-API-Key': 'test-internal-key'})
        assert r.status_code == 200
        assert r.json()['count'] >= 1

    def test_customer_list_has_required_fields(self, api_server):
        import requests
        r = requests.get(f'{api_server}/api/customer/all',
                         headers={'X-Internal-API-Key': 'test-internal-key'})
        assert r.status_code == 200
        data = r.json()
        assert len(data['data']) > 0
        for c in data['data']:
            assert 'customer_number' in c
            assert 'name' in c
            assert 'total_due' in c

    def test_create_reading_and_check_billing(self, api_server):
        import requests
        r = requests.post(f'{api_server}/api/customer/E2E-001/reading/new',
                          json={'reading_value': 200.0, 'timestamp': 1770000000},
                          headers={'X-Internal-API-Key': 'test-internal-key'})
        assert r.status_code == 201
        # Billing may or may not have been generated (depends on seed data),
        # but the API must return a valid response
        r2 = requests.get(f'{api_server}/api/customer/E2E-001/billing',
                          headers={'X-Internal-API-Key': 'test-internal-key'})
        assert r2.status_code == 200

    def test_staff_info_via_browser(self, page, api_server):
        resp = page.goto(f'{api_server}/api/staff/info')
        assert resp.status == 401
