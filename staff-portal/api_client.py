import os, time, re
import requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ.get('INTERNAL_API_KEY', '')

# Lightweight customer cache: stores only {customer_number, name} for fast local search
_customer_cache = []
_customer_cache_time = 0
CACHE_TTL = 300       # Full refresh every 5 min
CHANGED_CHECK_INTERVAL = 30  # Check for changes every 30s

def refresh_customer_cache(force=False) -> list:
    """Fetch ALL customers from API and cache locally."""
    global _customer_cache, _customer_cache_time
    now = time.time()

    # If cache is fresh enough, return immediately — no API calls
    if not force and _customer_cache and (now - _customer_cache_time) < CHANGED_CHECK_INTERVAL:
        return _customer_cache

    # Cache exists but may be stale — check if anything changed
    if _customer_cache and not force:
        try:
            changed = _get('/api/customers/changed', {'since': int(_customer_cache_time or 0)})
            if not changed.get('customer_numbers'):
                _customer_cache_time = now
                return _customer_cache
        except Exception:
            if (now - _customer_cache_time) < CACHE_TTL:
                return _customer_cache

    # Need to refresh — fetch from API
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
        for c in data:
            all_customers.append({
                'customer_number': c.get('customer_number', ''),
                'name': c.get('name', ''),
                'address': c.get('address', '') or '',
            })
        meta = r.get('meta', {})
        if page >= meta.get('total_pages', 1):
            break
        page += 1

    _customer_cache = all_customers
    _customer_cache_time = now
    return _customer_cache


def _is_pure_digits(s: str) -> bool:
    return bool(s) and all(c.isdigit() for c in s)

def _is_pure_name(s: str) -> bool:
    """Letters, spaces, dots, hyphens, apostrophes — no digits."""
    return bool(s) and all(c.isalpha() or c in ' .-\'' for c in s)


def search_cached_customers(query: str = '') -> list:
    """Smart search: digits-only searches by customer_number, letters-only by name.
    Returns list of {customer_number, name} matches, or error dict for mixed input."""
    if not query:
        return refresh_customer_cache()[:50]

    q = query.strip()
    if not q:
        return []

    if _is_pure_digits(q):
        field = 'customer_number'
        is_prefix = True
    elif _is_pure_name(q):
        field = 'name'
        is_prefix = False
    else:
        return [{'error': 'mixed_input',
                 'message': 'Search by customer number (digits only) or name (letters only).'}]

    customers = refresh_customer_cache()
    ql = q.lower()
    results = []

    for c in customers:
        val = c.get(field, '').lower()
        if is_prefix:
            if val == ql:
                results.insert(0, c)
            elif val.startswith(ql):
                results.append(c)
        else:
            if val.startswith(ql):
                results.insert(0, c)
            elif ql in val:
                results.append(c)

    # Sort by number: numerically ascending (1, 2, 10, 1550, 2320)
    if is_prefix:
        results.sort(key=lambda x: (
            0 if x.get('customer_number') == q else 1,
            int(x.get('customer_number', '0') or '0'),
        ))
    # Sort by name: exact match first, then alphabetical
    else:
        results.sort(key=lambda x: (
            0 if x.get('name', '').lower() == ql else 1,
            x.get('name', '').lower(),
        ))

    return results[:50]


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
