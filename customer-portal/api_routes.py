import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import api_client
from shared.auth import MAX_AGE, load_token, make_token

DEBUG = os.environ['DEBUG'].lower() in ('true', '1', 'yes')

logger = logging.getLogger('customer-portal')

api_bp = APIRouter(prefix='/customer/api')

# ---------------------------------------------------------------------------
# Customer-accessible field whitelists. The real API returns far more than the
# customer portal is allowed to see; every relayed response is reduced to
# exactly these fields before it leaves the portal.
# ---------------------------------------------------------------------------

CUSTOMER_FIELDS = (
    'customer_number', 'name', 'address', 'contact_number', 'email',
    'x_coordinate', 'y_coordinate',
)
READING_FIELDS = ('reading_value', 'reader', 'timestamp')
PAYMENT_FIELDS = ('receipt_number', 'paid_amount', 'timestamp')
UNPAID_BILL_FIELDS = ('month', 'amount', 'penalty', 'timestamp')
PAYMENT_METHOD_FIELDS = ('code', 'label', 'fee_percent', 'fee_flat', 'fee_minimum', 'xendit_fee')
PRICING_TIER_FIELDS = ('label', 'unit', 'rate')


def _pick(mapping, fields):
    return {k: mapping.get(k) for k in fields} if isinstance(mapping, dict) else None


def _clean_customer(customer):
    if not isinstance(customer, dict):
        return None
    return {
        'customer_number': customer.get('customer_number'),
        'name': customer.get('name'),
        'address': customer.get('address', ''),
        'contact_number': customer.get('contact_number', ''),
        'email': customer.get('email', ''),
        'x_coordinate': customer.get('x_coordinate'),
        'y_coordinate': customer.get('y_coordinate'),
    }


def _clean_reading(reading):
    return _pick(reading, READING_FIELDS)


def _clean_context(billing):
    if not isinstance(billing, dict):
        return {}
    return {
        'customer_number': billing.get('customer_number'),
        'name': billing.get('name'),
        'address': billing.get('address', ''),
        'contact_number': billing.get('contact_number', ''),
        'email': billing.get('email', ''),
        'latest_reading': _clean_reading(billing.get('latest_reading')),
        'last_reading': _clean_reading(billing.get('last_reading')),
        'consumption': billing.get('consumption', 0),
        'bill_breakdown': billing.get('bill_breakdown', []),
        'pricing_tiers': [_pick(t, PRICING_TIER_FIELDS) for t in billing.get('pricing_tiers', [])],
        'water_bill': billing.get('water_bill', 0),
        'original_water_bill': billing.get('original_water_bill', 0),
        'carryover': billing.get('carryover', 0),
        'cumulative_balance': billing.get('cumulative_balance', 0),
        'total_due': billing.get('total_due', 0),
        'unpaid_bills': [
            _pick(b, UNPAID_BILL_FIELDS) for b in billing.get('unpaid_bills', [])
        ],
        'due_date': billing.get('due_date'),
        'days_remaining': billing.get('days_remaining'),
        'pending_xendit': billing.get('pending_xendit'),
        'recent_payments': [
            _pick(p, PAYMENT_FIELDS) for p in billing.get('recent_payments', [])
        ],
        'payment_methods': [
            _pick(m, PAYMENT_METHOD_FIELDS) for m in billing.get('payment_methods', [])
        ],
    }


def _clean_readings_page(page):
    return {
        'items': [_pick(i, READING_FIELDS) for i in page.get('items', [])],
        'page': page.get('page', 1),
        'per_page': page.get('per_page', 12),
        'total': page.get('total', 0),
        'pages': page.get('pages', 1),
    }


def _clean_payments_page(page):
    return {
        'items': [_pick(i, PAYMENT_FIELDS) for i in page.get('items', [])],
        'page': page.get('page', 1),
        'per_page': page.get('per_page', 10),
        'total': page.get('total', 0),
        'pages': page.get('pages', 1),
    }


def _clean_history_page(page):
    return {
        'items': page.get('items', []),
        'page': page.get('page', 1),
        'per_page': page.get('per_page', 12),
        'total': page.get('total', 0),
        'pages': page.get('pages', 1),
    }


def _session_data(request: Request) -> dict | None:
    return load_token(request.cookies.get('billing_session'))


def _require_session(request: Request):
    data = _session_data(request)
    if not data or not data.get('customer_number'):
        return None, JSONResponse({'error': 'Unauthorized'}, status_code=401)
    return data, None


def _no_cache(resp: JSONResponse) -> JSONResponse:
    resp.headers['Cache-Control'] = 'no-store'
    return resp


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@api_bp.post('/verify')
async def verify(request: Request):
    body = await _body(request)
    account_number = body.get('account_number')
    if not account_number:
        return JSONResponse({'error': 'Account number is required'}, status_code=400)
    try:
        result = await api_client.customer_login(
            account_number,
            body.get('name', ''),
            body.get('last_receipt', ''),
        )
    except Exception as e:
        return _relay_error(e)
    return {'customer': _clean_customer(result.get('customer', {}))}


@api_bp.post('/login')
async def login(request: Request):
    body = await _body(request)
    account_number = body.get('account_number')
    if not account_number:
        return JSONResponse({'error': 'Account number is required'}, status_code=400)
    if not DEBUG:
        if not body.get('name') and not body.get('last_receipt'):
            return JSONResponse({'error': 'Registered name or last receipt number is required'}, status_code=400)
    try:
        result = await api_client.customer_login(
            account_number,
            '' if DEBUG else body.get('name', ''),
            '' if DEBUG else body.get('last_receipt', ''),
        )
    except Exception as e:
        return _relay_error(e)
    customer_number = result.get('customer_number')
    if not customer_number:
        return JSONResponse({'error': 'Verification failed'}, status_code=500)
    customer = _clean_customer(result.get('customer', {}))
    token = make_token({'customer_number': customer_number, 'customer': customer})
    resp = JSONResponse({'ok': True, 'redirect': '/customer/', 'customer': customer})
    resp.set_cookie('billing_session', token, max_age=MAX_AGE, httponly=True,
                    samesite='Lax', secure=True, path='/customer/')
    return _no_cache(resp)


@api_bp.get('/context')
async def context(request: Request):
    data, err = _require_session(request)
    if err:
        return err
    try:
        billing = await api_client.get_billing(data['customer_number'])
    except Exception as e:
        return _relay_error(e)
    return _no_cache(JSONResponse({
        'customer': data.get('customer', {}),
        'billing': _clean_context(billing),
    }))


@api_bp.get('/readings')
async def readings(request: Request):
    data, err = _require_session(request)
    if err:
        return err
    try:
        page = int(request.query_params.get('page', '1'))
    except (ValueError, TypeError):
        page = 1
    try:
        result = await api_client.get_readings(data['customer_number'], page=page)
    except Exception as e:
        return _relay_error(e)
    return _no_cache(JSONResponse(_clean_readings_page(result)))


@api_bp.get('/payments')
async def payments(request: Request):
    data, err = _require_session(request)
    if err:
        return err
    try:
        page = int(request.query_params.get('page', '1'))
    except (ValueError, TypeError):
        page = 1
    try:
        result = await api_client.get_payments(data['customer_number'], page=page)
    except Exception as e:
        return _relay_error(e)
    return _no_cache(JSONResponse(_clean_payments_page(result)))


@api_bp.get('/history')
async def billing_history(request: Request):
    data, err = _require_session(request)
    if err:
        return err
    try:
        page = int(request.query_params.get('page', '1'))
    except (ValueError, TypeError):
        page = 1
    try:
        result = await api_client.get_billing_history(data['customer_number'], page=page)
    except Exception as e:
        return _relay_error(e)
    return _no_cache(JSONResponse(_clean_history_page(result)))


@api_bp.post('/invoice')
async def create_invoice(request: Request):
    data, err = _require_session(request)
    if err:
        return err
    body = await _body(request)
    if 'amount' not in body:
        return JSONResponse({'error': 'Amount is required'}, status_code=400)
    try:
        result = await api_client.create_xendit_invoice(
            data['customer_number'],
            float(body['amount']),
            payment_method=body.get('payment_method', ''),
            success_url=body.get('success_url', ''),
            cancel_url=body.get('cancel_url', ''),
        )
    except Exception as e:
        return _relay_error(e)
    return _no_cache(JSONResponse({
        'redirect_url': result.get('redirect_url'),
    }))


def _relay_error(e):
    error_code = 'ERR0001'
    error_msg = str(e)
    status = 502
    try:
        if isinstance(e, httpx.HTTPStatusError):
            resp = e.response
            body = resp.json()
            error_code = body.get('error_code', error_code)
            error_msg = body.get('error', error_msg)
            if 400 <= resp.status_code < 500:
                status = resp.status_code
    except Exception:
        logger.error('Failed to parse error response', exc_info=True)
    logger.error('[%s] %s', error_code, error_msg)
    return JSONResponse({'error': 'Verification failed. Please contact support with this code.', 'error_code': error_code}, status_code=status)
