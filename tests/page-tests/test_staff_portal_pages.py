"""Render every staff portal page and verify 200 status (no template crashes)."""

import os, sys, pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'staff-portal'))
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')


@pytest.fixture
def app():
    from app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestStaffPortalPages:
    """Every route that renders a template must return 200."""

    def _login(self, client):
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['staff_id'] = 1
            sess['staff_data'] = {
                'id': 1, 'username': 'superuser', 'name': 'Superuser',
                'is_active': True,
                'can_read_meters': True, 'can_accept_payment': True,
                'can_enroll_customer': True, 'can_drop_reading': True,
                'can_drop_payment': True, 'can_enroll_staff': True,
                'can_manage_billing': True,
            }

    def test_login_page(self, client):
        resp = client.get('/staff/login')
        assert resp.status_code == 200

    @patch('api_client.get_dashboard_data')
    def test_dashboard(self, mock_dashboard, client):
        mock_dashboard.return_value = {'total_customers': 5, 'total_staff': 3}
        self._login(client)
        resp = client.get('/staff/dashboard')
        assert resp.status_code == 200

    @patch('api_client.get_customers')
    def test_customers(self, mock_customers, client):
        mock_customers.return_value = {'customers': [], 'page': 1, 'per_page': 50, 'total': 0, 'pages': 1}
        self._login(client)
        resp = client.get('/staff/customers')
        assert resp.status_code == 200

    @patch('api_client.get_customers')
    def test_manage_customers(self, mock_customers, client):
        mock_customers.return_value = {'customers': [], 'page': 1, 'per_page': 50, 'total': 0, 'pages': 1}
        self._login(client)
        resp = client.get('/staff/manage-customers')
        assert resp.status_code == 200

    @patch('api_client.list_api_keys')
    def test_meter_reading(self, mock_keys, client):
        mock_keys.return_value = {'keys': [{'id': 1, 'key': 'CRDC-TEST', 'label': 'test', 'is_active': True, 'staff': {'name': 'Test', 'username': 'test'}, 'staff_name': 'Test', 'staff_id': 1, 'date_created': '2026-01-01'}]}
        self._login(client)
        resp = client.get('/staff/meter-reading')
        assert resp.status_code == 200

    @patch('api_client.get_reading_logs')
    @patch('api_client.list_staff')
    @patch('api_client.list_api_keys')
    def test_manage_reading(self, mock_keys, mock_staff, mock_logs, client):
        mock_logs.return_value = {'logs': [{'id': 1, 'staff_id': 1, 'staff_name': 'Test', 'action_type': 'drop', 'target_id': 1, 'customer_number': 'C-001', 'details': 'test', 'timestamp': '2026-01-15 10:30:00'}]}
        mock_staff.return_value = {'staff': [{'id': 1, 'name': 'Test', 'username': 'test'}]}
        mock_keys.return_value = {'keys': [{'id': 1, 'key': 'CRDC-TEST', 'label': 'test', 'is_active': True, 'staff': {'name': 'Test', 'username': 'test'}, 'staff_name': 'Test', 'staff_id': 1, 'date_created': '2026-01-01'}]}
        self._login(client)
        resp = client.get('/staff/manage-reading')
        assert resp.status_code == 200

    def test_payments(self, client):
        self._login(client)
        resp = client.get('/staff/payments')
        assert resp.status_code == 200

    @patch('api_client.get_cashier_tally')
    def test_cashier_tally(self, mock_tally, client):
        mock_tally.return_value = {
            'tally': {}, 'use_matrix': False, 'display': '',
            'prev_date': '', 'next_date': '', 'is_today': True,
            'period': 'daily', 'nav_date': '', 'group_days': 1,
            'start_date': '', 'end_date': '',
        }
        self._login(client)
        resp = client.get('/staff/cashier-tally')
        assert resp.status_code == 200

    def test_manage_billing(self, client):
        self._login(client)
        resp = client.get('/staff/manage-billing')
        assert resp.status_code == 200

    @patch('api_client.list_staff')
    def test_staff_list(self, mock_staff, client):
        mock_staff.return_value = {'staff': [{'id': 1, 'name': 'Test', 'username': 'test', 'email': 'test@test.com', 'is_active': True, 'can_read_meters': True, 'can_accept_payment': False, 'can_enroll_customer': False, 'can_drop_reading': False, 'can_drop_payment': False, 'can_manage_billing': False, 'can_enroll_staff': False}]}
        self._login(client)
        resp = client.get('/staff/staff')
        assert resp.status_code == 200
