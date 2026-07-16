import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'developer-portal'))

os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')

import api_client

class TestApiClientFunctions:
    def test_all_functions_exist(self):
        expected = [
            'create_backup', 'list_backups',
            'restore_backup', 'restore_newest', 'clear_database',
            'seed_data', 'read_all_this_month', 'unread_this_month',
            'pay_all_this_month', 'remove_payments_this_month',
            'list_tasks', 'get_task',
        ]
        for name in expected:
            assert hasattr(api_client, name), f"Missing: {name}"
