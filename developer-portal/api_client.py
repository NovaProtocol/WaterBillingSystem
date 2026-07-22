import os, requests

API_BASE = os.environ['API_BASE_URL']
INTERNAL_KEY = os.environ.get('INTERNAL_API_KEY', '')

def _headers():
    h = {'User-Agent': 'developer-portal/1.0', 'X-Container-Name': 'developer-portal'}
    if INTERNAL_KEY:
        h['X-Internal-API-Key'] = INTERNAL_KEY
    return h

def create_backup():
    r = requests.post(f'{API_BASE}/api/debug/backup', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def list_backups():
    r = requests.get(f'{API_BASE}/api/debug/backups', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def restore_backup(filename: str):
    r = requests.post(f'{API_BASE}/api/debug/restore', json={'filename': filename}, headers=_headers(), timeout=60)
    r.raise_for_status(); return r.json()

def restore_newest():
    r = requests.get(f'{API_BASE}/api/debug/restore-newest', headers=_headers(), timeout=60)
    r.raise_for_status(); return r.json()

def clear_database():
    r = requests.post(f'{API_BASE}/api/debug/clear', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def seed_data(customers: int, months: int, cashiers: int = 2, readers: int = 2,
              read_current: str = 'no', pay_last: str = 'random',
              randomize_months: str = 'yes', allow_deactivation: str = 'no'):
    r = requests.post(f'{API_BASE}/api/debug/seed', json={
        'customers': customers, 'months': months,
        'cashiers': cashiers, 'readers': readers,
        'read_current': read_current, 'pay_last': pay_last,
        'randomize_months': randomize_months,
        'allow_deactivation': allow_deactivation,
    }, headers=_headers(), timeout=120)
    r.raise_for_status(); return r.json()

def read_all_this_month():
    r = requests.post(f'{API_BASE}/api/debug/read-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def unread_this_month():
    r = requests.post(f'{API_BASE}/api/debug/unread-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def pay_all_this_month():
    r = requests.post(f'{API_BASE}/api/debug/pay-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def remove_payments_this_month():
    r = requests.post(f'{API_BASE}/api/debug/remove-pay-month', headers=_headers(), timeout=30)
    r.raise_for_status(); return r.json()

def list_tasks():
    r = requests.get(f'{API_BASE}/api/debug/tasks', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_task(task_id):
    r = requests.get(f'{API_BASE}/api/debug/tasks/{task_id}', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()

def get_stats():
    r = requests.get(f'{API_BASE}/api/debug/stats', headers=_headers(), timeout=10)
    r.raise_for_status(); return r.json()
