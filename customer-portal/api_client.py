import os, requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ['INTERNAL_API_KEY']

def _headers():
    return {'X-Internal-Key': INTERNAL_KEY}

def verify_identity(account_number: str, name: str, last_receipt: str = '') -> dict:
    r = requests.post(f'{API_BASE}/api/internal/customer/verify', json={'account_number': account_number, 'registered_name': name, 'last_receipt': last_receipt}, headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_billing(customer_number: str) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/billing', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_readings(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/readings', params={'page': page}, headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_payments(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/payments', params={'page': page}, headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_billing_history(customer_number: str, page: int = 1) -> dict:
    r = requests.get(f'{API_BASE}/api/internal/customer/{customer_number}/history', params={'page': page}, headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def create_xendit_invoice(customer_number: str, amount: float) -> dict:
    r = requests.post(f'{API_BASE}/api/internal/customer/{customer_number}/invoice', json={'amount': amount}, headers=_headers(), timeout=15)
    r.raise_for_status(); return r.json()
