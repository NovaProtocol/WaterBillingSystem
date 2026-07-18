import os, time, re
import requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ.get('INTERNAL_API_KEY', '')

# Customer cache: stores ALL customers for fast local search
_customer_cache = []
_customer_cache_time = 0
CACHE_TTL = 300  # 5 minutes

def refresh_customer_cache(force=False) -> list:
    """Fetch ALL customers from API and cache locally.
    Uses /api/customers/changed to skip full refresh if nothing changed."""
    global _customer_cache, _customer_cache_time
    now = time.time()

    if _customer_cache:
        # Check if anything changed since our last refresh
        try:
            changed = _get('/api/customers/changed', {'since': int(_customer_cache_time or 0)})
            if not changed.get('customer_numbers'):
                _customer_cache_time = now  # Extend TTL, cache still fresh
                return _customer_cache
        except Exception:
            pass  # On error, fall through to full refresh

    if not force and _customer_cache and (now - _customer_cache_time) < CACHE_TTL:
        return _customer_cache

    all_customers = []
    page = 1
    while True:
        try:
            r = _get('/api/customer/all', {'page': page, 'size': 200})
        except Exception:
            break
        data = r.get('data', [])
        if not data:
            break
        all_customers.extend(data)
        meta = r.get('meta', {})
        if page >= meta.get('total_pages', 1):
            break
        page += 1

    _customer_cache = all_customers
    _customer_cache_time = now
    return _customer_cache

def _relevance(customer: dict, q: str) -> int:
    """Score 0-100: higher = better match."""
    num = customer.get('customer_number', '').lower()
    name = customer.get('name', '').lower()
    addr = customer.get('address', '').lower()
    phone = customer.get('contact_number', '')

    if num == q:
        return 100
    if num.startswith(q):
        return 90
    if q in num:
        return 80
    if name.startswith(q):
        return 70
    if q in name:
        return 60
    if q in addr:
        return 40
    if phone and q in phone:
        return 20
    return 0


def search_cached_customers(query: str = '') -> list:
    """Search locally cached customers by number, name, or address.
    Results sorted by relevance: exact number match first, then prefix,
    then contains, then name matches, then address/phone."""
    customers = refresh_customer_cache()
    if not query:
        return customers[:50]
    q = query.lower().strip()

    scored = []
    for c in customers:
        score = _relevance(c, q)
        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:50]]

def get_cache_status() -> dict:
    return {
        'size': len(_customer_cache),
        'age': time.time() - _customer_cache_time if _customer_cache else None,
        'ttl': CACHE_TTL,
    }

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

def get_customer(customer_number: str, params: dict = None) -> dict:
    return _get(f'/api/customer/{customer_number}', params)

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

def generate_api_key(staff_id: int = 1, data: dict = None) -> dict:
    return _post(f'/api/staff/{staff_id}/api-key/generate', data or {})

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
