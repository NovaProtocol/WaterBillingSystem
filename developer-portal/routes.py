import logging
logger = logging.getLogger('developer-portal')
import os, random, re
from functools import wraps
from typing import Any, Callable

import requests as http_requests
from flask import Response, jsonify, render_template, request, session, redirect, url_for
from flask_login import current_user
from werkzeug.datastructures import Headers

import api_client
from __init__ import dev_bp

_PMA_PREFIX = '/developer/phpmyadmin'


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


@dev_bp.route('/phpmyadmin/', methods=['GET', 'POST'])
@dev_bp.route('/phpmyadmin/<path:rest>', methods=['GET', 'POST'])
def phpmyadmin(rest=''):
    staff = session.get('staff_data')
    if not staff or staff.get('username') != 'superuser':
        return jsonify({"error": "Superuser only"}), 403

    pma_host = os.environ.get('PMA_HOST', 'phpmyadmin')
    target = f'http://{pma_host}:80/{rest}'
    if request.query_string:
        target += f'?{request.query_string.decode()}'

    headers = {k: v for k, v in request.headers
               if k.lower() not in ('host', 'content-length', 'transfer-encoding')}

    headers['X-Forwarded-Proto'] = 'https'
    headers['X-Forwarded-Scheme'] = 'https'

    try:
        resp = http_requests.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            timeout=60,
        )

        response_headers = Headers()
        for key, value in resp.raw.headers.items():
            kl = key.lower()
            if kl in ('content-encoding', 'transfer-encoding', 'content-length'):
                continue

            if kl == 'location' and value.startswith('/') and not value.startswith(_PMA_PREFIX):
                value = _PMA_PREFIX + value

            if kl == 'set-cookie':
                value = re.sub(
                    r'\bpath\s*=\s*/',
                    f'path={_PMA_PREFIX}/',
                    value,
                    flags=re.IGNORECASE,
                )

            response_headers.add(key, value)

        return Response(resp.content, resp.status_code, response_headers)
    except http_requests.exceptions.ConnectionError as e:
        logger.exception(f"Cannot reach phpMyAdmin: {e}")
        return jsonify({"error": f"Cannot reach phpMyAdmin: {e}"}), 502
    except Exception as e:
        logger.exception(f"phpMyAdmin proxy error: {e}")
        return jsonify({"error": f"Proxy error: {str(e)}"}), 502


# --- Page routes ---

@dev_bp.route('/')
@superuser_required
def index():
    return redirect(url_for('dev.backup'))


@dev_bp.route('/backup')
@superuser_required
def backup():
    backup_files = api_client.list_backups().get('backups', [])
    return render_template('dev/backup.html', backup_files=backup_files)


@dev_bp.route('/seed')
@superuser_required
def seed():
    return render_template('dev/seed.html')


@dev_bp.route('/clear')
@superuser_required
def clear():
    stats = api_client.get_stats()
    return render_template('dev/clear.html', stats=stats)


@dev_bp.route('/history')
@superuser_required
def task_logs():
    return render_template('dev/tasks.html')


# --- API routes ---

@dev_bp.route('/auth')
@superuser_required
def auth():
    return jsonify({"authenticated": True, "superuser": True})


@dev_bp.route('/confirm', methods=['POST'])
@superuser_required
def confirm():
    code = _generate_and_store_code()
    return jsonify({"code": code})


@dev_bp.route('/backup', methods=['POST'])
@superuser_required
def create_backup():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.create_backup()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Backup creation failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/backups')
@superuser_required
def list_backups():
    try:
        result = api_client.list_backups()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"List backups failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/restore', methods=['POST'])
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
        logger.exception(f"Restore backup failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/restore-newest', methods=['POST'])
@superuser_required
def restore_newest():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.restore_newest()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Restore newest failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/clear', methods=['POST'])
@superuser_required
def clear_database():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.clear_database()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Clear database failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/seed', methods=['POST'])
@superuser_required
def seed_data():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        customers = int(request.form.get("customers", "0"))
        months = int(request.form.get("months", "0"))
    except (ValueError, TypeError):
        logger.exception("Seed data validation failed:")
        return jsonify({"error": "Invalid customer count or months"}), 400
    if customers < 1 or customers > 10000:
        return jsonify({"error": "Customer count must be between 1 and 10000"}), 400
    if months < 1 or months > 240:
        return jsonify({"error": "Months must be between 1 and 240"}), 400
    try:
        result = api_client.seed_data(customers, months)
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Seed data failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/read-month', methods=['POST'])
@superuser_required
def read_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.read_all_this_month()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Read this month failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/unread-month', methods=['POST'])
@superuser_required
def unread_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.unread_this_month()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Unread this month failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/pay-month', methods=['POST'])
@superuser_required
def pay_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.pay_all_this_month()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Pay this month failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/remove-pay-month', methods=['POST'])
@superuser_required
def remove_payment_this_month():
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    try:
        result = api_client.remove_payments_this_month()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Remove payment this month failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/tasks')
@superuser_required
def list_tasks():
    try:
        result = api_client.list_tasks()
        return jsonify(result)
    except Exception as e:
        logger.exception(f"List tasks failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/tasks/<task_id>')
@superuser_required
def get_task(task_id):
    try:
        result = api_client.get_task(task_id)
        return jsonify(result)
    except Exception as e:
        logger.exception(f"Get task {task_id} failed:")
        return jsonify({"error": str(e)}), 500


@dev_bp.route('/logs')
@superuser_required
def logs():
    return render_template('dev/logs.html')


@dev_bp.route('/api/logs')
@superuser_required
def api_logs():
    from shared.logger import query_logs
    service = request.args.get('service') or None
    level = request.args.get('level') or None
    q = request.args.get('q') or None
    limit = min(int(request.args.get('limit', 200)), 1000)
    offset = int(request.args.get('offset', 0))
    results = query_logs(service=service, level=level, q=q, limit=limit, offset=offset)
    return jsonify({'data': results, 'total': len(results)})


@dev_bp.route('/api/logs/clear', methods=['POST'])
@superuser_required
def api_logs_clear():
    import glob, os as os_mod
    for path in glob.glob('/var/log/app/*.db'):
        try:
            os_mod.remove(path)
        except Exception as e:
            logger.exception(f"Failed to remove log file {path}: {e}")
    return jsonify({'message': 'Logs cleared'})
