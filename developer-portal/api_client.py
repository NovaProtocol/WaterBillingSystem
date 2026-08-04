import os

from shared.http_client import make_client

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = make_client(os.environ['API_BASE_URL'], container_name='developer-portal')
    return _client


async def create_backup():
    r = await _get_client().post('/api/debug/backup')
    r.raise_for_status()
    return r.json()


async def list_backups():
    r = await _get_client().get('/api/debug/backups')
    r.raise_for_status()
    return r.json()


async def restore_backup(filename: str):
    r = await _get_client().post('/api/debug/restore', json={'filename': filename})
    r.raise_for_status()
    return r.json()


async def restore_newest():
    r = await _get_client().get('/api/debug/restore-newest')
    r.raise_for_status()
    return r.json()


async def clear_database():
    r = await _get_client().post('/api/debug/clear')
    r.raise_for_status()
    return r.json()


async def seed_data(customers: int, months: int, cashiers: int = 2, readers: int = 2,
                    read_current: str = 'no', pay_last: str = 'random',
                    randomize_months: str = 'yes', allow_deactivation: str = 'no'):
    r = await _get_client().post('/api/debug/seed', json={
        'customers': customers, 'months': months,
        'cashiers': cashiers, 'readers': readers,
        'read_current': read_current, 'pay_last': pay_last,
        'randomize_months': randomize_months,
        'allow_deactivation': allow_deactivation,
    })
    r.raise_for_status()
    return r.json()


async def read_all_this_month():
    r = await _get_client().post('/api/debug/read-month')
    r.raise_for_status()
    return r.json()


async def unread_this_month():
    r = await _get_client().post('/api/debug/unread-month')
    r.raise_for_status()
    return r.json()


async def pay_all_this_month():
    r = await _get_client().post('/api/debug/pay-month')
    r.raise_for_status()
    return r.json()


async def remove_payments_this_month():
    r = await _get_client().post('/api/debug/remove-pay-month')
    r.raise_for_status()
    return r.json()


async def list_tasks():
    r = await _get_client().get('/api/debug/tasks')
    r.raise_for_status()
    return r.json()


async def get_task(task_id):
    r = await _get_client().get(f'/api/debug/tasks/{task_id}')
    r.raise_for_status()
    return r.json()


async def get_stats():
    r = await _get_client().get('/api/debug/stats')
    r.raise_for_status()
    return r.json()
