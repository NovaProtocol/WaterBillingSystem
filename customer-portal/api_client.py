import os

from shared.http_client import make_client

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = make_client(os.environ['API_BASE_URL'], container_name='customer-portal')
    return _client


async def customer_login(account_number: str, name: str = '', last_receipt: str = '') -> dict:
    r = await _get_client().post('/api/customer/login',
        json={'account_number': int(account_number), 'registered_name': name, 'last_receipt': last_receipt})
    r.raise_for_status()
    return r.json()


async def get_billing(customer_number: int) -> dict:
    r = await _get_client().get(f'/api/customer/{customer_number}')
    r.raise_for_status()
    return r.json()


async def get_readings(customer_number: int, page: int = 1) -> dict:
    r = await _get_client().get(f'/api/customer/{customer_number}/reading',
        params={'page': page, 'size': 12})
    r.raise_for_status()
    data = r.json()
    return {
        'items': data.get('data', []),
        'page': data.get('meta', {}).get('current_page', page),
        'per_page': data.get('meta', {}).get('page_size', 12),
        'total': data.get('meta', {}).get('total_items', 0),
        'pages': data.get('meta', {}).get('total_pages', 1),
    }


async def get_payments(customer_number: int, page: int = 1) -> dict:
    r = await _get_client().get(f'/api/customer/{customer_number}/billing',
        params={'page': page, 'size': 10})
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


async def get_billing_history(customer_number: int, page: int = 1) -> dict:
    r = await _get_client().get(f'/api/customer/{customer_number}/billing',
        params={'page': page, 'size': 12})
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


async def create_xendit_invoice(customer_number: int, amount: float, payment_method: str = '',
                                success_url: str = '', cancel_url: str = '') -> dict:
    r = await _get_client().post(f'/api/customer/{customer_number}/invoice',
        json={'amount': amount, 'payment_method': payment_method,
              'success_url': success_url, 'cancel_url': cancel_url})
    r.raise_for_status()
    return r.json()
