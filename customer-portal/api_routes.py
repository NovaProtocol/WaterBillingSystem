import os
from flask import Blueprint, jsonify, request

import api_client
from auth import load_session, serializer, MAX_AGE

DEBUG = os.environ.get('DEBUG', '').lower() in ('true', '1', 'yes')

api_bp = Blueprint('api', __name__, url_prefix='/customer/api')

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


def _require_session():
    data = load_session()
    if not data or not data.get('customer_number'):
        return None, (jsonify({'error': 'Unauthorized'}), 401)
    return data, None


def _no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api_bp.route('/verify', methods=['POST'])
def verify():
    body = request.get_json(silent=True) or {}
    account_number = body.get('account_number')
    if not account_number:
        return jsonify({'error': 'Account number is required'}), 400
    try:
        result = api_client.customer_login(
            account_number,
            body.get('name', ''),
            body.get('last_receipt', ''),
        )
    except Exception as e:
        return _relay_error(e)
    return jsonify({'customer': _clean_customer(result.get('customer', {}))})


@api_bp.route('/login', methods=['POST'])
def login():
    body = request.get_json(silent=True) or {}
    account_number = body.get('account_number')
    if not account_number:
        return jsonify({'error': 'Account number is required'}), 400
    if not DEBUG:
        if not body.get('name') and not body.get('last_receipt'):
            return jsonify({'error': 'Registered name or last receipt number is required'}), 400
    try:
        result = api_client.customer_login(
            account_number,
            '' if DEBUG else body.get('name', ''),
            '' if DEBUG else body.get('last_receipt', ''),
        )
    except Exception as e:
        return _relay_error(e)
    customer_number = result.get('customer_number')
    if not customer_number:
        return jsonify({'error': 'Verification failed'}), 500
    customer = _clean_customer(result.get('customer', {}))
    token = serializer.dumps({'customer_number': customer_number, 'customer': customer})
    resp = jsonify({'ok': True, 'redirect': '/customer/', 'customer': customer})
    resp.set_cookie('billing_session', token, max_age=MAX_AGE, httponly=True,
                    samesite='Lax', path='/customer/')
    return _no_cache(resp)


@api_bp.route('/context')
def context():
    data, err = _require_session()
    if err:
        return err
    try:
        billing = api_client.get_billing(data['customer_number'])
    except Exception as e:
        return _relay_error(e)
    return _no_cache(jsonify({
        'customer': data.get('customer', {}),
        'billing': _clean_context(billing),
    }))


@api_bp.route('/readings')
def readings():
    data, err = _require_session()
    if err:
        return err
    page = request.args.get('page', 1, type=int)
    try:
        result = api_client.get_readings(data['customer_number'], page=page)
    except Exception as e:
        return _relay_error(e)
    return _no_cache(jsonify(_clean_readings_page(result)))


@api_bp.route('/payments')
def payments():
    data, err = _require_session()
    if err:
        return err
    page = request.args.get('page', 1, type=int)
    try:
        result = api_client.get_payments(data['customer_number'], page=page)
    except Exception as e:
        return _relay_error(e)
    return _no_cache(jsonify(_clean_payments_page(result)))


@api_bp.route('/history')
def billing_history():
    data, err = _require_session()
    if err:
        return err
    page = request.args.get('page', 1, type=int)
    try:
        result = api_client.get_billing_history(data['customer_number'], page=page)
    except Exception as e:
        return _relay_error(e)
    return _no_cache(jsonify(_clean_history_page(result)))


@api_bp.route('/invoice', methods=['POST'])
def create_invoice():
    data, err = _require_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    if 'amount' not in body:
        return jsonify({'error': 'Amount is required'}), 400
    try:
        result = api_client.create_xendit_invoice(
            data['customer_number'],
            float(body['amount']),
            payment_method=body.get('payment_method', ''),
            success_url=body.get('success_url', ''),
            cancel_url=body.get('cancel_url', ''),
        )
    except Exception as e:
        return _relay_error(e)
    return _no_cache(jsonify({
        'redirect_url': result.get('redirect_url'),
    }))


def _relay_error(e):
    from flask import current_app
    error_code = 'ERR0001'
    error_msg = str(e)
    status = 502
    try:
        resp = getattr(e, 'response', None)
        if resp is not None:
            body = resp.json()
            error_code = body.get('error_code', error_code)
            error_msg = body.get('error', error_msg)
            if 400 <= resp.status_code < 500:
                status = resp.status_code
    except Exception:
        current_app.logger.error('Failed to parse error response', exc_info=True)
    current_app.logger.error('[%s] %s', error_code, error_msg)
    return jsonify({'error': 'Verification failed. Please contact support with this code.', 'error_code': error_code}), status
