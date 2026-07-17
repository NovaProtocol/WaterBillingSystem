"""Render customer portal pages, scrape HTML, verify sample data."""

import os, sys, pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'customer-portal'))
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ['WTF_CSRF_ENABLED'] = 'False'
os.environ['DEBUG'] = 'true'


SAMPLE_BILLING = {
    'customer_number': 'C001',
    'name': 'Juan Dela Cruz',
    'address': '123 Rizal St, Manila',
    'contact_number': '09171234567',
    'email': 'juan@email.com',
    'meter_serial_number': 'MTR-001',
    'phase': 'Phase 1', 'block': 'Block A', 'street': 'Rizal St',
    'x_coordinate': 120.0, 'y_coordinate': 14.0,
    'consumption': 75.5,
    'original_water_bill': 450.75,
    'bill_breakdown': [
        {'label': 'First 10 m³', 'units': 10.0, 'charge': 150.00},
        {'label': '11-20 m³', 'units': 10.0, 'charge': 250.00},
        {'label': '21-30 m³', 'units': 55.5, 'charge': 50.75},
    ],
    'pricing_tiers': [
        {'rate': 150.00, 'type': 'flat', 'from_unit': 0, 'to_unit': 10},
        {'rate': 25.00, 'type': 'per_unit', 'from_unit': 10, 'to_unit': 20},
        {'rate': 30.00, 'type': 'per_unit', 'from_unit': 20, 'to_unit': 30},
    ],
    'unpaid_bills': [
        {'month': 'January 2026', 'amount': 450.75, 'penalty': 15.00},
    ],
    'total_due': 465.75,
    'carryover': 0.00,
    'cumulative_balance': 0.00,
    'due_date': '02-15-2026',
    'days_remaining': 5,
    'latest_reading': {
        'id': 2, 'reading_value': 175.5, 'reader': 'Superuser',
        'timestamp': '2026-02-15 10:30:00',
    },
    'last_reading': {
        'id': 1, 'reading_value': 100.0, 'reader': 'Superuser',
        'timestamp': '2026-01-15 10:30:00',
    },
    'recent_payments': [
        {'receipt_number': 'RCP-001', 'paid_amount': 500.00, 'timestamp': '2026-02-15 10:30:00'},
    ],
    'latest_unpaid': {'month': 'January 2026', 'amount': 450.75, 'penalty': 15.00},
    'payment_methods': [
        {'code': 'gcash', 'label': 'GCash', 'sort_order': 1,
         'fee_percent': 2.0, 'fee_flat': 0.0, 'fee_minimum': 10.0, 'xendit_fee': 11.0},
    ],
}


@pytest.fixture
def app():
    from app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestCustomerPortalPagesRendered:
    """Render customer portal pages and verify sample data in HTML."""

    def test_identify_page(self, client):
        resp = client.get('/customer/')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Account Number' in body or 'account' in body.lower()

    @patch('api_client.customer_login')
    def test_identify_post_with_debug(self, mock_login, client):
        """With DEBUG=true, submitting creates a session and redirects."""
        mock_login.return_value = {
            'customer_number': 'C001',
            'customer': {'customer_number': 'C001', 'name': 'Test', 'address': '123 St'},
        }
        resp = client.post('/customer/', data={'account_number': 'C001'},
                          follow_redirects=False)
        assert resp.status_code == 302

    def test_billing_page_shows_customer_data(self, client):
        """Render billing page and verify customer data appears."""
        from itsdangerous import URLSafeTimedSerializer
        s = URLSafeTimedSerializer(os.environ['SECRET_KEY'], salt='billing-session')
        token = s.dumps({
            'customer_number': 'C001',
            'customer_data': {
                'customer_number': 'C001', 'name': 'Juan Dela Cruz',
                'address': '123 Rizal St, Manila',
            }
        })
        client.set_cookie('billing_session', token)
        with patch('api_client.get_billing') as mock:
            mock.return_value = SAMPLE_BILLING
            resp = client.get('/customer/billing/C001')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Customer name and address should appear
        assert 'Juan Dela Cruz' in body
        assert '123 Rizal St' in body or '123 Rizal St, Manila' in body

        # Consumption should appear
        assert '75.5' in body or '75.50' in body

        # Unpaid bill amount should appear
        assert '450.75' in body or '450' in body

        # Due date should appear
        assert '02-15-2026' in body

        # Reader name should appear (using flat 'reader' field)
        assert 'Superuser' in body

    def test_billing_page_shows_bill_breakdown(self, client):
        """Verify bill breakdown table renders with tier details."""
        from itsdangerous import URLSafeTimedSerializer
        s = URLSafeTimedSerializer(os.environ['SECRET_KEY'], salt='billing-session')
        token = s.dumps({
            'customer_number': 'C001',
            'customer_data': {'customer_number': 'C001', 'name': 'Test'},
        })
        client.set_cookie('billing_session', token)
        with patch('api_client.get_billing') as mock:
            mock.return_value = SAMPLE_BILLING
            resp = client.get('/customer/billing/C001')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Pricing tier labels should appear
        assert 'First 10' in body
        assert '11-20' in body

        # Total water bill should appear
        assert '450.75' in body or '450' in body

    def test_billing_redirects_without_cookie(self, client):
        resp = client.get('/customer/billing/C001')
        assert resp.status_code == 302

    def test_billing_shows_error_on_api_failure(self, client):
        """When API call fails, error should propagate."""
        from itsdangerous import URLSafeTimedSerializer
        s = URLSafeTimedSerializer(os.environ['SECRET_KEY'], salt='billing-session')
        token = s.dumps({
            'customer_number': 'C001',
            'customer_data': {'customer_number': 'C001', 'name': 'Test'},
        })
        client.set_cookie('billing_session', token)
        resp = client.get('/customer/billing/C001')
        # Should get 500 because the real API isn't running
        assert resp.status_code == 500
