"""Render every staff portal page, scrape HTML, verify sample data appears."""

import os, sys, pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'staff-portal'))
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ['WTF_CSRF_ENABLED'] = 'False'


SAMPLE_CUSTOMERS = {
    'customers': [
        {
            'id': 1, 'customer_number': 'C001', 'name': 'Juan Dela Cruz',
            'address': '123 Rizal St, Manila', 'contact_number': '09171234567',
            'email': 'juan@email.com', 'phase': 'Phase 1', 'block': 'Block A',
            'street': 'Rizal St', 'x_coordinate': 120.0, 'y_coordinate': 14.0,
            'meter_serial_number': 'MTR-001', 'nfc_uid': 'A1B2C3D4',
            'cumulative_balance': 150.50, 'total_due': 450.75, 'is_active': True,
        },
        {
            'id': 2, 'customer_number': 'C002', 'name': 'Maria Santos',
            'address': '456 Mabini Ave', 'contact_number': '09179876543',
            'email': 'maria@email.com', 'phase': 'Phase 2', 'block': 'Block B',
            'street': 'Mabini Ave', 'x_coordinate': 121.0, 'y_coordinate': 14.5,
            'meter_serial_number': 'MTR-002', 'nfc_uid': None,
            'cumulative_balance': 0.00, 'total_due': 0.00, 'is_active': True,
        },
        {
            'id': 3, 'customer_number': 'C003', 'name': 'Pedro Reyes',
            'address': '789 Bonifacio St', 'contact_number': '09175551234',
            'email': 'pedro@email.com', 'phase': 'Phase 1', 'block': 'Block A',
            'street': 'Bonifacio St', 'x_coordinate': 120.5, 'y_coordinate': 14.2,
            'meter_serial_number': 'MTR-003', 'nfc_uid': 'E5F6G7H8',
            'cumulative_balance': 25.00, 'total_due': 125.50, 'is_active': False,
        },
    ],
    'page': 1, 'per_page': 50, 'total': 3, 'pages': 1,
}

SAMPLE_STAFF = {
    'staff': [
        {'id': 1, 'name': 'Superuser', 'username': 'superuser',
         'email': 'super@test.com', 'contact_number': '09170000001',
         'is_active': True,
         'can_read_meters': True, 'can_accept_payment': True,
         'can_enroll_customer': True, 'can_drop_reading': True,
         'can_drop_payment': True, 'can_enroll_staff': True,
         'can_manage_billing': True},
        {'id': 2, 'name': 'Cashier One', 'username': 'cashier1',
         'email': 'cashier@test.com', 'contact_number': '09170000002',
         'is_active': True,
         'can_read_meters': False, 'can_accept_payment': True,
         'can_enroll_customer': False, 'can_drop_reading': False,
         'can_drop_payment': False, 'can_enroll_staff': False,
         'can_manage_billing': False},
    ],
}


@pytest.fixture
def app():
    from app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestStaffPortalPagesRendered:
    """Render every page and verify sample data appears in the HTML."""

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

    @patch('api_client.get_customers')
    def test_customers_page_shows_customer_data(self, mock_customers, client):
        """Render /staff/customers with sample data and scrape HTML."""
        mock_customers.return_value = SAMPLE_CUSTOMERS
        self._login(client)
        resp = client.get('/staff/customers')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Juan Dela Cruz should appear with all details
        assert 'Juan Dela Cruz' in body
        assert 'C001' in body
        assert '123 Rizal St, Manila' in body
        assert '09171234567' in body
        assert 'juan@email.com' in body

        # Maria Santos should appear
        assert 'Maria Santos' in body
        assert 'C002' in body

        # Pedro Reyes appears but is inactive
        assert 'Pedro Reyes' in body
        assert 'C003' in body

    @patch('api_client.search_and_sort_customers')
    def test_manage_customers_shows_edit_data(self, mock_customers, client):
        """Render /staff/manage-customers and verify edit button data attributes."""
        mock_customers.return_value = SAMPLE_CUSTOMERS
        self._login(client)
        resp = client.get('/staff/manage-customers')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Juan Dela Cruz should have an edit button with his data
        assert 'data-number="C001"' in body
        assert 'data-name="Juan Dela Cruz"' in body
        assert 'data-address="123 Rizal St, Manila"' in body
        assert 'data-contact="09171234567"' in body
        assert 'data-phase="Phase 1"' in body
        assert 'data-block="Block A"' in body
        assert 'MTR-001' in body

        # NFC tag should appear
        assert 'data-nfc-tag-id="A1B2C3D4"' in body

        # Inactive customer should show different styling
        assert 'data-active="false"' in body

    @patch('api_client.search_and_sort_customers')
    def test_manage_customers_shows_pagination(self, mock_customers, client):
        mock_customers.return_value = SAMPLE_CUSTOMERS
        self._login(client)
        resp = client.get('/staff/manage-customers')
        body = resp.data.decode()
        assert '3 total' in body.lower() or '3</span>' in body

    @patch('api_client.list_api_keys')
    def test_meter_reading_shows_keys(self, mock_keys, client):
        """Verify API keys render on the meter reading page."""
        mock_keys.return_value = {
            'keys': [
                {'id': 1, 'key': 'CRDC-ABCDEF1234567890ABCDEF1234567890',
                 'label': 'Meter Reader App', 'is_active': True,
                 'staff': {'name': 'Superuser', 'username': 'superuser'},
                 'staff_name': 'Superuser', 'staff_id': 1,
                 'date_created': '2026-01-15T10:00:00'},
            ]
        }
        self._login(client)
        resp = client.get('/staff/meter-reading')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Full key should be visible (not truncated)
        assert 'CRDC-ABCDEF1234567890ABCDEF1234567890' in body
        assert 'Meter Reader App' in body

    @patch('api_client.get_reading_logs')
    @patch('api_client.list_staff')
    @patch('api_client.list_api_keys')
    def test_manage_reading_shows_logs(self, mock_keys, mock_staff, mock_logs, client):
        """Verify reading logs render correctly."""
        mock_logs.return_value = {
            'logs': [
                {'id': 1, 'staff_id': 1, 'staff_name': 'Superuser',
                 'action_type': 'drop', 'target_id': 1,
                 'customer_number': 'C001', 'details': 'Dropped reading #1 for C001',
                 'timestamp': '2026-01-15 10:30:00'},
            ]
        }
        mock_staff.return_value = {'staff': [{'id': 1, 'name': 'Superuser', 'username': 'superuser'}]}
        mock_keys.return_value = {'keys': []}
        self._login(client)
        resp = client.get('/staff/manage-reading')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Log details should appear
        assert 'Dropped reading #1 for C001' in body
        assert 'Superuser' in body

    @patch('api_client.list_staff')
    def test_staff_list_shows_staff_data(self, mock_staff, client):
        """Verify staff list renders with correct names and permissions."""
        mock_staff.return_value = SAMPLE_STAFF
        self._login(client)
        resp = client.get('/staff/staff')
        assert resp.status_code == 200
        body = resp.data.decode()

        # Both staff members should appear
        assert 'Superuser' in body
        assert 'Cashier One' in body
        assert 'super@test.com' in body
        assert 'cashier@test.com' in body
        assert '09170000001' in body

    @patch('api_client.get_dashboard_data')
    def test_dashboard_shows_welcome(self, mock_dash, client):
        """Dashboard shows the logged-in user's name."""
        mock_dash.return_value = {'total_customers': 10, 'total_staff': 3}
        self._login(client)
        resp = client.get('/staff/dashboard')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Superuser' in body
        assert 'Welcome' in body

    def test_payments_page_loads(self, client):
        self._login(client)
        resp = client.get('/staff/payments')
        assert resp.status_code == 200

    def test_manage_billing_page_loads(self, client):
        self._login(client)
        resp = client.get('/staff/manage-billing')
        assert resp.status_code == 200
