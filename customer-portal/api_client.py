import os, requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ.get('INTERNAL_API_KEY', '')

def _headers():
    h = {}
    if INTERNAL_KEY:
        h['X-Internal-API-Key'] = INTERNAL_KEY
    return h

def customer_login(account_number: str, name: str, last_receipt: str = '') -> dict:
    r = requests.post(f'{API_BASE}/api/customer/login',
        json={'account_number': account_number, 'registered_name': name, 'last_receipt': last_receipt},
        headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_billing(customer_number: str) -> dict:
    r = requests.get(f'{API_BASE}/api/customer/{customer_number}',
        headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_readings(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/customer/{customer_number}/reading',
        params={'page': page, 'size': 12},
        headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    return {
        'items': data.get('data', []),
        'page': data.get('meta', {}).get('current_page', page),
        'per_page': data.get('meta', {}).get('page_size', 12),
        'total': data.get('meta', {}).get('total_items', 0),
        'pages': data.get('meta', {}).get('total_pages', 1),
    }

def get_payments(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/customer/{customer_number}/billing',
        params={'page': page, 'size': 10},
        headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    items = [b for b in data.get('data', []) if b.get('is_paid')]
    return {
        'items': items,
        'page': data.get('meta', {}).get('current_page', page),
        'per_page': data.get('meta', {}).get('page_size', 10),
        'total': len(items),
        'pages': data.get('meta', {}).get('total_pages', 1),
    }

def get_billing_history(customer_number: str, page: int = 1) -> dict:
    return get_readings(customer_number, page=page)

def create_xendit_invoice(customer_number: str, amount: float) -> dict:
    r = requests.post(f'{API_BASE}/api/customer/{customer_number}/invoice',
        json={'amount': amount},
        headers=_headers(), timeout=15)
    r.raise_for_status(); return r.json()
