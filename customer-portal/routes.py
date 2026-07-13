from flask import request, render_template, redirect, url_for, make_response, jsonify
from itsdangerous import URLSafeTimedSerializer
from __init__ import customer_bp
import api_client
import os

DEBUG = os.environ.get('DEBUG', '').lower() in ('true', '1', 'yes')
serializer = URLSafeTimedSerializer(os.environ['SECRET_KEY'], salt='billing-session')

@customer_bp.route('/customer/', methods=['GET', 'POST'])
def identify():
    ctx = {'debug': DEBUG}
    if request.method == 'POST':
        account_number = request.form.get('account_number')
        name = request.form.get('name', '')
        last_receipt = request.form.get('last_receipt', '').strip()
        if not account_number:
            ctx['error'] = 'Account number is required.'
            return render_template('customer/identify.html', **ctx)
        if DEBUG:
            name = ''
            last_receipt = ''
        else:
            if not name:
                ctx['error'] = 'Registered name is required.'
                return render_template('customer/identify.html', **ctx)
            if not last_receipt:
                ctx['error'] = 'Last receipt number is required.'
                return render_template('customer/identify.html', **ctx)
        try:
            result = api_client.verify_identity(account_number, name, last_receipt)
        except Exception as e:
            msg = str(e)
            try:
                import json as _json
                msg = _json.loads(getattr(e, 'response', None).text if hasattr(e, 'response') else '{}').get('error', msg)
            except Exception:
                pass
            ctx['error'] = msg or 'Verification failed. Please try again.'
            return render_template('customer/identify.html', **ctx)
        customer_number = result.get('customer_number')
        customer_data = result.get('customer', {})
        if not customer_number:
            ctx['error'] = 'Verification failed. No customer number returned.'
            return render_template('customer/identify.html', **ctx)
        token = serializer.dumps({'customer_number': customer_number, 'customer_data': customer_data})
        resp = make_response(redirect(url_for('customer.billing', customer_number=customer_number)))
        resp.set_cookie('billing_session', token, max_age=3600, httponly=True, samesite='Lax')
        return resp
    return render_template('customer/identify.html', **ctx)

@customer_bp.route('/customer/billing/<customer_number>')
def billing(customer_number):
    token = request.cookies.get('billing_session')
    if not token:
        return redirect(url_for('customer.identify'))
    try:
        data = serializer.loads(token, max_age=3600)
    except Exception:
        return redirect(url_for('customer.identify'))
    if data.get('customer_number') != customer_number:
        return redirect(url_for('customer.identify'))
    try:
        billing = api_client.get_billing(customer_number)
    except Exception as e:
        return render_template('customer/error.html', error='Unable to load billing information.')
    customer_data = data.get('customer_data', {})
    ctx = {'billing': billing, 'customer': customer_data, 'customer_number': customer_number}
    if isinstance(billing, dict):
        ctx.update(billing)
    ctx.setdefault('PRICING_TIERS', [])
    ctx.setdefault('payment_methods', [])
    ctx.setdefault('pending_xendit', None)
    ctx.setdefault('recent_payments', [])
    ctx.setdefault('recent_readings', [])
    ctx.setdefault('unpaid_bills', [])
    ctx.setdefault('latest_reading', {})
    ctx.setdefault('bill_breakdown', [])
    return render_template('customer/billing.html', **ctx)

@customer_bp.route('/customer/billing/<customer_number>/readings')
def readings(customer_number):
    token = request.cookies.get('billing_session')
    if not token:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        serializer.loads(token, max_age=3600)
    except Exception:
        return jsonify({'error': 'Unauthorized'}), 401
    page = request.args.get('page', 1, type=int)
    try:
        data = api_client.get_readings(customer_number, page=page)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch readings'}), 500

@customer_bp.route('/customer/billing/<customer_number>/payments')
def payments(customer_number):
    token = request.cookies.get('billing_session')
    if not token:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        serializer.loads(token, max_age=3600)
    except Exception:
        return jsonify({'error': 'Unauthorized'}), 401
    page = request.args.get('page', 1, type=int)
    try:
        data = api_client.get_payments(customer_number, page=page)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch payments'}), 500

@customer_bp.route('/customer/billing/<customer_number>/history')
def billing_history(customer_number):
    token = request.cookies.get('billing_session')
    if not token:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        serializer.loads(token, max_age=3600)
    except Exception:
        return jsonify({'error': 'Unauthorized'}), 401
    page = request.args.get('page', 1, type=int)
    try:
        data = api_client.get_billing_history(customer_number, page=page)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch billing history'}), 500

@customer_bp.route('/customer/billing/<customer_number>/invoice', methods=['POST'])
def create_invoice(customer_number):
    token = request.cookies.get('billing_session')
    if not token:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        serializer.loads(token, max_age=3600)
    except Exception:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    if not data or 'amount' not in data:
        return jsonify({'error': 'Amount is required'}), 400
    try:
        result = api_client.create_xendit_invoice(customer_number, float(data['amount']))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': 'Failed to create invoice'}), 500
