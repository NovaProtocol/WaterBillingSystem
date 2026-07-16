import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'customer-portal'))

os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')

import api_client

class TestApiClientFunctions:
    def test_all_functions_exist(self):
        expected = [
            'customer_login', 'get_billing', 'get_readings',
            'get_payments', 'get_billing_history', 'create_xendit_invoice',
        ]
        for name in expected:
            assert hasattr(api_client, name), f"Missing: {name}"
