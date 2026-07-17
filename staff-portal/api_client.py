import os
import requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ.get('INTERNAL_API_KEY', '')

def _headers():
    headers = {}
    if INTERNAL_KEY:
        headers['X-Internal-API-Key'] = INTERNAL_KEY
    return headers

def _post(path, data=None):
    r = requests.post(f'{API_BASE}{path}', json=data or {}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

def _get(path, params=None):
    r = requests.get(f'{API_BASE}{path}', params=params or {}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

def _put(path, data=None):
    r = requests.put(f'{API_BASE}{path}', json=data or {}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

def _delete(path):
    r = requests.delete(f'{API_BASE}{path}', headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

def staff_login(username: str, password: str) -> dict:
    data = _post('/api/staff/login', {'username': username, 'password': password})
    return {'success': True, 'staff': data}

def get_dashboard_data() -> dict:
    customers = _get('/api/customer/count')
    staff_list = _get('/api/staff/all')
    return {
        'total_customers': customers.get('count', 0),
        'total_staff': len(staff_list.get('staff', [])),
    }

def get_customer(customer_number: str) -> dict:
    return _get(f'/api/customer/{customer_number}')

def customer_lookup(query: str) -> dict:
    r = _get('/api/customer/all', {'q': query, 'size': 10})
    return r.get('data', [])

def get_customers(page: int = 1, per_page: int = 50) -> dict:
    r = _get('/api/customer/all', {'page': page, 'size': per_page})
    return {
        'customers': r.get('data', []),
        'page': r.get('meta', {}).get('current_page', page),
        'per_page': r.get('meta', {}).get('page_size', per_page),
        'total': r.get('meta', {}).get('total_items', 0),
        'pages': r.get('meta', {}).get('total_pages', 1),
    }

def create_customer(data: dict) -> dict:
    return _post('/api/customer/new', data)

def edit_customer(customer_id: int, data: dict) -> dict:
    customer_number = data.get('customer_number', str(customer_id))
    return _put(f'/api/customer/update/{customer_number}', data)

def toggle_customer_active(customer_number: str) -> dict:
    return _delete(f'/api/customer/delete/{customer_number}')

def clear_customer_nfc(customer_number: str) -> dict:
    return _post(f'/api/customer/{customer_number}/nfc/delete')

def submit_payment(data: dict) -> dict:
    customer_number = data.get('customer_number', '')
    return _post(f'/api/customer/{customer_number}/billing/new', data)

def get_cashier_tally(period: str, staff_id: int = 1) -> dict:
    return _get(f'/api/staff/{staff_id}/cashier-tally', {'period': period})

def drop_reading(reading_id: int, data: dict) -> dict:
    customer_number = data.get('customer_number', '')
    return _post(f'/api/customer/{customer_number}/reading/drop', {'reading_id': reading_id, 'reason': 'Staff drop'})

def edit_reading(reading_id: int, data: dict) -> dict:
    customer_number = data.get('customer_number', '')
    reading_value = data.get('reading_value', 0)
    return _post(f'/api/customer/{customer_number}/reading/edit', {'reading_id': reading_id, 'reading_value': reading_value})

def undo_payment(billing_id: int) -> dict:
    return _post(f'/api/customer/{billing_id}/billing/drop', {'billing_id': billing_id})

def generate_api_key(staff_id: int = 1) -> dict:
    return _post(f'/api/staff/{staff_id}/api-key/generate')

def revoke_api_key(staff_id: int, key_id: int) -> dict:
    return _post(f'/api/staff/{staff_id}/api-key/{key_id}/revoke')

def list_api_keys(staff_id: int = 1) -> dict:
    return _get(f'/api/staff/{staff_id}/api-keys')

def get_reading_logs(staff_id: int = 1) -> dict:
    return _get(f'/api/staff/{staff_id}/reading-logs')

def list_staff() -> dict:
    return _get('/api/staff/all')

def get_staff(staff_id: int) -> dict:
    return _get(f'/api/staff/{staff_id}')

def create_staff(data: dict) -> dict:
    return _post('/api/staff/new', data)

def edit_staff(staff_id: int, data: dict) -> dict:
    return _post(f'/api/staff/{staff_id}/edit', data)
