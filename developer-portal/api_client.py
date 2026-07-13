import os, requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ['INTERNAL_API_KEY']

def _headers():
    return {'X-Internal-Key': INTERNAL_KEY}

def create_backup():
    r = requests.post(f'{API_BASE}/api/internal/debug/backup', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def list_backups():
    r = requests.get(f'{API_BASE}/api/internal/debug/backups', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def restore_backup(filename: str):
    r = requests.post(f'{API_BASE}/api/internal/debug/restore', json={'filename': filename}, headers=_headers(), timeout=60)
    r.raise_for_status(); return r.json()

def restore_newest():
    r = requests.get(f'{API_BASE}/api/internal/debug/restore-newest', headers=_headers(), timeout=60)
    r.raise_for_status(); return r.json()

def clear_database():
    r = requests.post(f'{API_BASE}/api/internal/debug/clear', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def seed_data(customers: int, months: int):
    r = requests.post(f'{API_BASE}/api/internal/debug/seed', json={'customers': customers, 'months': months}, headers=_headers(), timeout=120)
    r.raise_for_status(); return r.json()

def read_all_this_month():
    r = requests.post(f'{API_BASE}/api/internal/debug/read-this-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def unread_this_month():
    r = requests.post(f'{API_BASE}/api/internal/debug/unread-this-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def pay_all_this_month():
    r = requests.post(f'{API_BASE}/api/internal/debug/pay-this-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def remove_payments_this_month():
    r = requests.post(f'{API_BASE}/api/internal/debug/remove-payment-this-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def list_tasks():
    r = requests.get(f'{API_BASE}/api/internal/debug/tasks', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_task(task_id):
    r = requests.get(f'{API_BASE}/api/internal/debug/tasks/{task_id}', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()
