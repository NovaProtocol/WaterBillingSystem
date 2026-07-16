import os
from flask import Response, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from app import login_manager, cache, Staff
import api_client

from __init__ import staff_bp

def permission_required(*perms):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            session_data = session.get('staff_data', {})
            for perm in perms:
                if not session_data.get(perm, False):
                    return jsonify({"error": "Unauthorized"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def _rate_limited(ip: str) -> bool:
    key = f"login_{ip}"
    attempts = cache.get(key) or 0
    if attempts >= 10:
        return True
    cache.set(key, attempts + 1, timeout=60)
    return False

@staff_bp.route('/staff/', methods=['GET'])
def index():
    if current_user.is_authenticated:
        return redirect(url_for('staff_blueprint.dashboard'))
    return redirect(url_for('staff_blueprint.login'))

@staff_bp.route('/staff/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('staff_blueprint.dashboard'))
    from forms import LoginForm
    form = LoginForm()
    if form.validate_on_submit():
        if _rate_limited(request.remote_addr):
            return render_template('staff/login.html', form=form, error='Too many attempts. Try again later.')
        try:
            result = api_client.staff_login(form.username.data, form.password.data)
            if result.get('success'):
                staff_data = result['staff']
                session['staff_id'] = staff_data['id']
                session['staff_data'] = staff_data
                staff_obj = Staff(staff_data)
                login_user(staff_obj, remember=True)
                return redirect(url_for('staff_blueprint.dashboard'))
        except Exception:
            pass
        return render_template('staff/login.html', form=form, error='Invalid credentials')
    return render_template('staff/login.html', form=form)

@staff_bp.route('/staff/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('staff_blueprint.login'))

@staff_bp.route('/staff/dashboard')
@login_required
def dashboard():
    try:
        data = api_client.get_dashboard_data()
    except Exception:
        data = {}
    return render_template('staff/dashboard.html', data=data)

@staff_bp.route('/staff/customer-lookup')
@login_required
def customer_lookup():
    q = request.args.get('q', '')
    try:
        result = api_client.customer_lookup(q)
        return jsonify(result)
    except Exception as e:
        return jsonify({'customers': [], 'error': str(e)})

@staff_bp.route('/staff/customers', methods=['GET'])
@login_required
def customers():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    try:
        result = api_client.get_customers(page, per_page)
        return render_template('staff/customers.html', **result)
    except Exception:
        return render_template('staff/customers.html', customers=[], page=1, per_page=50, total=0, pages=0)

@staff_bp.route('/staff/customers/create', methods=['POST'])
@permission_required('can_enroll_customer')
def customer_create():
    data = request.get_json()
    try:
        result = api_client.create_customer(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/manage-customers', methods=['GET'])
@login_required
def manage_customers():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    q = request.args.get('q', '')
    sort_by = request.args.get('sort_by', 'name')
    sort_dir = request.args.get('sort_dir', 'asc')
    try:
        result = api_client.get_customers(page, per_page)
        ctx = {
            'customers': result.get('customers', []),
            'page': result.get('page', page),
            'per_page': result.get('per_page', per_page),
            'total': result.get('total', 0),
            'pages': result.get('pages', 0),
            'sort_by': sort_by,
            'sort_dir': sort_dir,
            'q': q,
        }
    except Exception:
        ctx = {'customers': [], 'page': 1, 'per_page': per_page, 'total': 0, 'pages': 0, 'sort_by': sort_by, 'sort_dir': sort_dir, 'q': q, 'nfc_tags': {}}
    return render_template('staff/manage_customers.html', **ctx)

@staff_bp.route('/staff/manage-customers/<int:customer_id>/edit', methods=['POST'])
@permission_required('can_enroll_customer')
def edit_customer(customer_id):
    data = request.get_json()
    try:
        result = api_client.edit_customer(customer_id, data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/manage-customers/<int:customer_id>/toggle-active', methods=['POST'])
@permission_required('can_enroll_customer')
def toggle_customer_active(customer_id):
    try:
        result = api_client.toggle_customer_active(customer_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/manage-customers/<int:customer_id>/clear-nfc', methods=['POST'])
@permission_required('can_enroll_customer')
def clear_customer_nfc(customer_id):
    try:
        result = api_client.clear_customer_nfc(customer_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/meter-reading')
@login_required
def meter_reading():
    try:
        keys_result = api_client.list_api_keys()
        keys = keys_result.get('keys', [])
    except Exception:
        keys = []
    return render_template('staff/meter_reading.html', keys=keys)

@staff_bp.route('/staff/meter-reading/generate', methods=['POST'])
@login_required
def generate_api_key():
    try:
        result = api_client.generate_api_key()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/meter-reading/revoke/<int:key_id>', methods=['POST'])
@login_required
def revoke_api_key(key_id):
    try:
        result = api_client.revoke_api_key(key_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/manage-reading')
@login_required
def manage_reading():
    try:
        result = api_client.get_reading_logs()
        return render_template('staff/manage_reading.html', **result)
    except Exception:
        return render_template('staff/manage_reading.html', logs=[], staff_list=[], tokens=[])

@staff_bp.route('/staff/manage-reading/drop-reading/<int:reading_id>', methods=['POST'])
@permission_required('can_drop_reading')
def drop_reading(reading_id):
    try:
        result = api_client.drop_reading(reading_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/manage-reading/edit-reading/<int:reading_id>', methods=['POST'])
@permission_required('can_drop_reading')
def edit_reading(reading_id):
    data = request.get_json()
    try:
        result = api_client.edit_reading(reading_id, data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/payments')
@login_required
def payments():
    return render_template('staff/payments.html')

@staff_bp.route('/staff/payments/submit', methods=['POST'])
@permission_required('can_accept_payment')
def submit_payment():
    data = request.get_json()
    try:
        result = api_client.submit_payment(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/cashier-tally')
@permission_required('can_accept_payment')
def cashier_tally():
    period = request.args.get('period', 'daily')
    try:
        data = api_client.get_cashier_tally(period)
        return render_template('staff/cashier_tally.html', **data)
    except Exception:
        return render_template('staff/cashier_tally.html', tally={}, period=period, display='', prev_date='', next_date='', start_date='', end_date='', group_days='', nav_date='', use_matrix='')

@staff_bp.route('/staff/manage-billing')
@login_required
def manage_billing():
    return render_template('staff/manage_billing.html')

@staff_bp.route('/staff/manage-billing/undo-payment/<int:payment_id>', methods=['POST'])
@permission_required('can_drop_payment')
def undo_payment(payment_id):
    try:
        result = api_client.undo_payment(payment_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/staff', methods=['GET'])
@login_required
def staff_list():
    try:
        result = api_client.list_staff()
        return render_template('staff/staff_list.html', **result)
    except Exception:
        return render_template('staff/staff_list.html', staff=[])

@staff_bp.route('/staff/staff/create', methods=['POST'])
@permission_required('can_enroll_staff')
def staff_create():
    data = request.get_json()
    try:
        result = api_client.create_staff(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@staff_bp.route('/staff/staff/<int:staff_id>', methods=['GET', 'POST'])
@permission_required('can_enroll_staff')
def staff_edit(staff_id):
    if request.method == 'POST':
        data = request.get_json()
        try:
            result = api_client.edit_staff(staff_id, data)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    try:
        result = api_client.get_staff(staff_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
