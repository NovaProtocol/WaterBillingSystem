import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'staff-portal'))

os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')

import api_client

class TestApiClientFunctions:
    def test_all_functions_exist(self):
        """Every function in api_client must exist and be callable."""
        expected = [
            'staff_login', 'get_dashboard_data', 'customer_lookup',
            'get_customers', 'create_customer', 'edit_customer',
            'toggle_customer_active', 'clear_customer_nfc',
            'submit_payment', 'get_cashier_tally',
            'drop_reading', 'edit_reading', 'undo_payment',
            'generate_api_key', 'revoke_api_key', 'list_api_keys',
            'get_reading_logs', 'list_staff', 'get_staff',
            'create_staff', 'edit_staff',
        ]
        for name in expected:
            assert hasattr(api_client, name), f"Missing: {name}"
