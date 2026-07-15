import os
import requests

API_BASE = os.environ['API_BASE_URL']

def _post(path, data=None):
    r = requests.post(f'{API_BASE}{path}', json=data or {}, headers={}, timeout=15)
    r.raise_for_status()
    return r.json()

def _get(path, params=None):
    r = requests.get(f'{API_BASE}{path}', params=params or {}, headers={}, timeout=15)
    r.raise_for_status()
    return r.json()

def staff_login(username: str, password: str) -> dict:
    return _post('/api/staff/login', {'username': username, 'password': password})

def customer_lookup(query: str) -> dict:
    return _get('/api/staff/customer-lookup', {'q': query})

def get_customers(page: int = 1, per_page: int = 50) -> dict:
    return _get('/api/staff/customers', {'page': page, 'per_page': per_page})

def get_dashboard_data() -> dict:
    return _get('/api/staff/dashboard')

def create_customer(data: dict) -> dict:
    return _post('/api/staff/customer/create', data)

def edit_customer(customer_id: int, data: dict) -> dict:
    return _post(f'/api/staff/customer/{customer_id}/edit', data)

def toggle_customer_active(customer_id: int) -> dict:
    return _post(f'/api/staff/customer/{customer_id}/toggle-active')

def clear_customer_nfc(customer_id: int) -> dict:
    return _post(f'/api/staff/customer/{customer_id}/clear-nfc')

def submit_payment(data: dict) -> dict:
    return _post('/api/staff/payment/submit', data)

def get_cashier_tally(period: str) -> dict:
    return _get('/api/staff/1/cashier-tally', {'period': period})

def drop_reading(reading_id: int) -> dict:
    return _post('/api/staff/reading/drop', {'reading_id': reading_id})

def edit_reading(reading_id: int, data: dict) -> dict:
    return _post('/api/staff/reading/edit', {'reading_id': reading_id, **data})

def undo_payment(billing_id: int) -> dict:
    return _post('/api/staff/billing/undo', {'billing_id': billing_id})

def generate_api_key() -> dict:
    return _post('/api/staff/1/api-key/generate')

def revoke_api_key(key_id: int) -> dict:
    return _post('/api/staff/1/api-key/revoke', {'key_id': key_id})

def list_api_keys() -> dict:
    return _get('/api/staff/1/api-keys')

def get_reading_logs() -> dict:
    return _get('/api/staff/1/reading-logs')

def list_staff() -> dict:
    return _get('/api/staff/all')

def get_staff(staff_id: int) -> dict:
    return _get(f'/api/staff/{staff_id}')

def create_staff(data: dict) -> dict:
    return _post('/api/staff/new', data)

def edit_staff(staff_id: int, data: dict) -> dict:
    return _post(f'/api/staff/{staff_id}/edit', data)
