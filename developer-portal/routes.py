import logging
logger = logging.getLogger('developer-portal')
import random
from functools import wraps
from typing import Any, Callable

from flask import jsonify, render_template, request, session, redirect, url_for
from flask_login import current_user

import api_client
from __init__ import dev_bp


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
    return redirect('/phpmyadmin/')


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
        form = request.form
        customers = int(form.get("customers", "0"))
        months = int(form.get("months", "0"))
    except (ValueError, TypeError):
        logger.exception("Seed data validation failed:")
        return jsonify({"error": "Invalid customer count or months"}), 400
    if customers < 1 or months < 2 or customers * months > 10_000_000:
        return jsonify({"error": "Invalid range: customers × months must be between 1×2 and 10M entries"}), 400
    try:
        result = api_client.seed_data(
            customers=customers, months=months,
            cashiers=int(form.get("cashiers", 2)),
            readers=int(form.get("readers", 2)),
            read_current=form.get("read_current", "no"),
            pay_last=form.get("pay_last", "random"),
            randomize_months=form.get("randomize_months", "yes"),
            allow_deactivation=form.get("allow_deactivation", "no"),
        )
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
