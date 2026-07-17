import logging
logger = logging.getLogger('developer-portal')
import os, random
from functools import wraps
from typing import Any, Callable

import requests as http_requests
from flask import Response, jsonify, render_template, request, session
from flask_login import current_user

import api_client
from __init__ import debug_bp


def superuser_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        staff = session.get('staff_data')
        if not staff or staff.get('username') != 'superuser':
            return jsonify({"error": "Superuser only"}), 403
        return f(*args, **kwargs)
    return wrapper


def _confirm_check() -> str | None:
    code = request.form.get("confirm_code", "").strip()
    expected = session.pop("debug_confirm", None)
    if not expected or code != expected:
        return None
    return code


def _generate_and_store_code() -> str:
    code = str(random.randint(10_000_000, 99_999_999))
    session["debug_confirm"] = code
    return code


@debug_bp.route('/phpmyadmin/')
@debug_bp.route('/phpmyadmin/<path:rest>')
@superuser_required
def phpmyadmin(rest=''):
    """Proxy to phpMyAdmin with superuser auth check."""
    pma_host = os.environ.get('PMA_HOST', 'phpmyadmin')
    target = f'http://{pma_host}:80/{rest}'
    if request.query_string:
        target += f'?{request.query_string.decode()}'

    headers = {k: v for k, v in request.headers
               if k.lower() not in ('host', 'content-length', 'transfer-encoding')}

    try:
        resp = http_requests.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            timeout=60,
        )
        resp_headers = {k: v for k, v in resp.headers.items()
                        if k.lower() not in ('content-encoding', 'transfer-encoding',
                                              'content-length')}
        flask_resp = Response(
            resp.content,
            status=resp.status_code,
            headers=resp_headers,
        )
        return flask_resp
    except http_requests.exceptions.ConnectionError as e:
        return jsonify({"error": f"Cannot reach phpMyAdmin: {e}"}), 502


@debug_bp.route('/')
@superuser_required
def dashboard():
    return render_template('debug/debug.html', backup_files=[])


@debug_bp.route('/auth')
@superuser_required
def auth():
    return jsonify({"authenticated": True, "superuser": True})


@debug_bp.route('/confirm', methods=['POST'])
@superuser_required
def confirm():
    code = _generate_and_store_code()
    return jsonify({"code": code})


@debug_bp.route('/backup', methods=['POST'])
@superuser_required
def create_backup():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.create_backup()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/backups')
@superuser_required
def list_backups():
    try:
        result = api_client.list_backups()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/restore', methods=['POST'])
@superuser_required
def restore_backup():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    filename = request.form.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No backup file specified"}), 400
    try:
        result = api_client.restore_backup(filename)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/restore-newest', methods=['POST'])
@superuser_required
def restore_newest():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.restore_newest()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/clear', methods=['POST'])
@superuser_required
def clear_database():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.clear_database()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/seed', methods=['POST'])
@superuser_required
def seed_data():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        customers = int(request.form.get("customers", "0"))
        months = int(request.form.get("months", "0"))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid customer count or months"}), 400
    if customers < 1 or customers > 10000:
        return jsonify({"error": "Customer count must be between 1 and 10000"}), 400
    if months < 1 or months > 240:
        return jsonify({"error": "Months must be between 1 and 240"}), 400
    try:
        result = api_client.seed_data(customers, months)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/read-month', methods=['POST'])
@superuser_required
def read_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.read_all_this_month()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/unread-month', methods=['POST'])
@superuser_required
def unread_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.unread_this_month()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/pay-month', methods=['POST'])
@superuser_required
def pay_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.pay_all_this_month()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/remove-pay-month', methods=['POST'])
@superuser_required
def remove_payment_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.remove_payments_this_month()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/tasks')
@superuser_required
def list_tasks():
    try:
        result = api_client.list_tasks()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/tasks/<task_id>')
@superuser_required
def get_task(task_id):
    try:
        result = api_client.get_task(task_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route('/phpmyadmin')
@debug_bp.route('/phpmyadmin/<path:path>')
@superuser_required
def phpmyadmin_proxy(path=''):
    pma_url = os.environ['PMA_URL'].rstrip('/')
    target = f"{pma_url}/{path}"
    query = request.query_string.decode() if request.query_string else ''
    if query:
        target += '?' + query

    headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length', 'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host')}

    try:
        resp = http_requests.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            stream=True,
            timeout=60,
        )
    except Exception as e:
        return jsonify({"error": f"Proxy error: {str(e)}"}), 502

    excluded = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
    response_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]

    return Response(resp.content, resp.status_code, response_headers)
