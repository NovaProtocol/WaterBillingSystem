from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Response, jsonify, request

from app import db
from blueprint import blueprint
from models import BackgroundTask, Config

logger = logging.getLogger('api')

BACKUP_DIR = Path("/app/db_backups")
_last_restore_newest_time = 0.0
_restore_newest_lock = threading.Lock()


def _superuser_only() -> None:
    if not BACKUP_DIR.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)


@blueprint.route("/debug/stats")
def debug_stats() -> Response:
    _superuser_only()
    from app import db
    from models import Customer, MeterReading, Billing, Staff, ApiKey, NfcTag, ManagementLog, XenditTransaction, PaymentMethod, BackgroundTask

    return jsonify({
        "customers": Customer.query.filter_by(is_active=True).count(),
        "customers_total": Customer.query.count(),
        "readings": MeterReading.query.count(),
        "billings": Billing.query.count(),
        "unpaid_bills": Billing.query.filter_by(is_paid=False).count(),
        "paid_bills": Billing.query.filter_by(is_paid=True).count(),
        "staff": Staff.query.count(),
        "api_keys": ApiKey.query.count(),
        "nfc_tags": NfcTag.query.count(),
        "management_logs": ManagementLog.query.count(),
        "xendit_transactions": XenditTransaction.query.count(),
        "payment_methods": PaymentMethod.query.filter_by(is_active=True).count(),
        "background_tasks": BackgroundTask.query.count(),
    })


@blueprint.route("/debug/backup", methods=["POST"])
def debug_backup() -> Response:
    _superuser_only()
    task = BackgroundTask.enqueue(task_type="backup", params={}, title="Backup Database")
    return jsonify({"ok": True, "order_id": task.id, "message": "Backup queued."})


@blueprint.route("/debug/backups")
def debug_backups() -> Response:
    _superuser_only()
    if not BACKUP_DIR.exists():
        return jsonify({"backups": []})
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    return jsonify({
        "backups": [
            {
                "name": b.name,
                "size": b.stat().st_size,
                "modified": datetime.fromtimestamp(b.stat().st_mtime).isoformat(),
            }
            for b in backups
        ]
    })


@blueprint.route("/debug/restore", methods=["POST"])
def debug_restore() -> Response:
    _superuser_only()
    filename = (request.get_json() or {}).get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No backup file specified"}), 400
    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".sql"):
        return jsonify({"error": "Backup file not found"}), 404
    task = BackgroundTask.enqueue(
        task_type="restore", params={"filename": filename}, title=f"Restore: {filename}"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Restore queued."})


@blueprint.route("/debug/restore-newest")
def debug_restore_newest() -> Response:
    global _last_restore_newest_time
    with _restore_newest_lock:
        now = time.time()
        if now - _last_restore_newest_time < 5:
            remaining = round(5 - (now - _last_restore_newest_time), 1)
            return jsonify({"error": f"Cooldown active. Try again in {remaining}s"}), 429
        _last_restore_newest_time = now
    _superuser_only()
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    if not backups:
        return jsonify({"error": "No backup files found"}), 404
    filename = backups[0].name
    task = BackgroundTask.enqueue(
        task_type="restore", params={"filename": filename}, title=f"Restore newest: {filename}"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": f"Restoring from newest backup: {filename}"})


@blueprint.route("/debug/clear", methods=["POST"])
def debug_clear() -> Response:
    _superuser_only()
    task = BackgroundTask.enqueue(task_type="clear", params={}, title="Clear Database")
    return jsonify({"ok": True, "order_id": task.id, "message": "Clear queued."})


@blueprint.route("/debug/seed", methods=["POST"])
def debug_seed() -> Response:
    _superuser_only()
    data = request.get_json() or {}
    try:
        n_customers = int(data.get("customers", "0"))
        n_months = int(data.get("months", "0"))
    except (ValueError, TypeError):
        logger.exception("Invalid seed parameters:")
        return jsonify({"error": "Invalid customer count or months"}), 400

    total_entries = n_customers * n_months
    if n_customers < 1 or n_months < 2 or total_entries > 10_000_000:
        return jsonify({"error": "Invalid range: customers × months must be between 1×2 and 10,000,000 total entries"}), 400

    n_cashiers = int(data.get("cashiers", "2"))
    n_readers = int(data.get("readers", "2"))
    read_current = data.get("read_current", "no")
    pay_last = data.get("pay_last", "random")
    randomize_months = data.get("randomize_months", "yes")
    allow_deactivation = data.get("allow_deactivation", "no")

    params = {
        "customers": n_customers, "months": n_months,
        "cashiers": n_cashiers, "readers": n_readers,
        "read_current": read_current, "pay_last": pay_last,
        "randomize_months": randomize_months,
        "allow_deactivation": allow_deactivation,
    }
    task = BackgroundTask.enqueue(
        task_type="seed",
        params=params,
        title=f"Seed: {n_customers}c × {n_months}m",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Seed queued."})


@blueprint.route("/debug/read-month", methods=["POST"])
def debug_read_month() -> Response:
    _superuser_only()
    task = BackgroundTask.enqueue(
        task_type="read-this-month", params={}, title="Read This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Read-this-month queued."})


@blueprint.route("/debug/unread-month", methods=["POST"])
def debug_unread_month() -> Response:
    _superuser_only()
    task = BackgroundTask.enqueue(
        task_type="unread-this-month", params={}, title="Unread This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Unread-this-month queued."})


@blueprint.route("/debug/pay-month", methods=["POST"])
def debug_pay_month() -> Response:
    _superuser_only()
    task = BackgroundTask.enqueue(
        task_type="pay-this-month", params={}, title="Pay This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Pay-this-month queued."})


@blueprint.route("/debug/remove-pay-month", methods=["POST"])
def debug_remove_pay_month() -> Response:
    _superuser_only()
    task = BackgroundTask.enqueue(
        task_type="remove-payment-this-month", params={}, title="Remove Payment This Month"
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Remove-payment queued."})


@blueprint.route("/debug/tasks")
def debug_tasks() -> Response:
    _superuser_only()
    current_task = BackgroundTask.query.filter_by(status="running").first()
    queue = BackgroundTask.query.filter_by(status="queued").order_by(BackgroundTask.created_at.asc()).all()
    history = (
        BackgroundTask.query.filter(BackgroundTask.status.in_(["completed", "failed"]))
        .order_by(BackgroundTask.created_at.desc())
        .limit(20)
        .all()
    )

    def _to_dict(t: BackgroundTask) -> dict:
        return {
            "id": str(t.id),
            "task_type": t.task_type,
            "title": t.title,
            "status": t.status,
            "progress": t.progress,
            "messages": t.messages or [],
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }

    return jsonify({
        "current": _to_dict(current_task) if current_task else None,
        "queue_depth": len(queue),
        "history": [_to_dict(t) for t in history],
    })


@blueprint.route("/debug/tasks/<int:task_id>")
def debug_task(task_id: int) -> Response:
    _superuser_only()
    task = BackgroundTask.query.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({
        "task": {
            "id": str(task.id),
            "task_type": task.task_type,
            "title": task.title,
            "status": task.status,
            "progress": task.progress,
            "messages": task.messages or [],
            "params": task.params,
            "result": task.result,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
    })
