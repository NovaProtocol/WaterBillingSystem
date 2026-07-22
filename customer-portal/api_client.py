import os, requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ.get('INTERNAL_API_KEY', '')

def _headers():
    h = {'User-Agent': 'customer-portal/1.0', 'X-Container-Name': 'customer-portal'}
    if INTERNAL_KEY:
        h['X-Internal-API-Key'] = INTERNAL_KEY
    return h

def customer_login(account_number: str, name: str, last_receipt: str = '') -> dict:
    r = requests.post(f'{API_BASE}/api/customer/login',
        json={'account_number': int(account_number), 'registered_name': name, 'last_receipt': last_receipt},
        headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_billing(customer_number: int) -> dict:
    r = requests.get(f'{API_BASE}/api/customer/{customer_number}',
        headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_readings(customer_number: int, page: int = 1) -> dict:
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

def get_payments(customer_number: int, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/customer/{customer_number}/billing',
        params={'page': page, 'size': 10},
        headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    items = []
    for b in data.get('data', []):
        if b.get('is_paid'):
            ts = b.get('payment_timestamp') or b.get('date_paid') or 0
            b['timestamp'] = ts
            items.append(b)
    return {
        'items': items,
        'page': data.get('meta', {}).get('current_page', page),
        'per_page': data.get('meta', {}).get('page_size', 10),
        'total': len(items),
        'pages': data.get('meta', {}).get('total_pages', 1),
    }

def get_billing_history(customer_number: int, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/customer/{customer_number}/billing',
        params={'page': page, 'size': 12},
        headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    items = []
    for b in data.get('data', []):
        items.append({
            'month': b.get('month') or '',
            'usage': b.get('consumption') or 0,
            'billed_amount': b.get('billed_amount', 0),
            'penalty': b.get('penalty', 0),
            'paid_amount': b.get('paid_amount') if b.get('is_paid') else None,
        })
    return {
        'items': items,
        'page': data.get('meta', {}).get('current_page', page),
        'per_page': data.get('meta', {}).get('page_size', 12),
        'total': data.get('meta', {}).get('total_items', 0),
        'pages': data.get('meta', {}).get('total_pages', 1),
    }

def create_xendit_invoice(customer_number: int, amount: float, payment_method: str = '',
                          success_url: str = '', cancel_url: str = '') -> dict:
    r = requests.post(f'{API_BASE}/api/customer/{customer_number}/invoice',
        json={'amount': amount, 'payment_method': payment_method,
              'success_url': success_url, 'cancel_url': cancel_url},
        headers=_headers(), timeout=15)
    r.raise_for_status(); return r.json()
