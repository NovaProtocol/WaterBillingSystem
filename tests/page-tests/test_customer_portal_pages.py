"""Render every customer portal page and verify 200 status."""

import os, sys, pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'customer-portal'))
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ['WTF_CSRF_ENABLED'] = 'False'
os.environ['DEBUG'] = 'true'


@pytest.fixture
def app():
    from app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestCustomerPortalPages:
    def test_identify_page(self, client):
        resp = client.get('/customer/')
        assert resp.status_code == 200

    def test_identify_page_post_no_data(self, client):
        resp = client.post('/customer/', data={})
        assert resp.status_code == 200

    @patch('api_client.customer_login')
    def test_identify_page_post_valid(self, mock_login, client):
        mock_login.return_value = {
            'customer_number': 'TEST-001',
            'customer': {'customer_number': 'TEST-001', 'name': 'Test', 'address': '123 St'},
        }
        resp = client.post('/customer/', data={'account_number': 'TEST-001'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_billing_redirects_when_no_cookie(self, client):
        resp = client.get('/customer/billing/TEST-001')
        assert resp.status_code == 302

    @patch('api_client.get_billing')
    def test_billing_page_requires_login(self, mock_billing, client):
        mock_billing.return_value = {
            'customer_number': 'TEST-001', 'customer': {'name': 'Test'},
            'consumption': 0, 'unpaid_bills': [], 'recent_payments': [],
            'bill_breakdown': [], 'pricing_tiers': [], 'due_date': None,
            'total_due': 0, 'carryover': 0, 'original_water_bill': 0,
            'cumulative_balance': 0, 'pending_xendit': None,
            'recent_readings': [], 'payment_methods': [],
        }
        from itsdangerous import URLSafeTimedSerializer
        s = URLSafeTimedSerializer(os.environ['SECRET_KEY'], salt='billing-session')
        token = s.dumps({'customer_number': 'TEST-001', 'customer_data': {'name': 'Test'}})
        client.set_cookie('billing_session', token)
        resp = client.get('/customer/billing/TEST-001')
        assert resp.status_code == 200
