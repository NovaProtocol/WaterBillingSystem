from __future__ import annotations

import os
import random
import threading
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import flask
from flask import Response, jsonify, render_template, request, session
from flask_login import current_user
from apps import db
from apps.models import BackgroundTask
from apps.staff import blueprint

BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "db_backups"

_last_restore_newest_time = 0.0
_restore_newest_lock = threading.Lock()


# ── Superuser guard ────────────────────────────────────────────────────

def superuser_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not current_user.is_authenticated:
            return jsonify({"error": "Not authenticated"}), 401
        if current_user.username != "superuser":
            return jsonify({"error": "Superuser only"}), 403
        if os.environ.get("DEBUG", "").lower() not in ("true", "1", "yes"):
            return jsonify({"error": "DEBUG mode not enabled"}), 403
        return f(*args, **kwargs)
    return wrapper


# ── Confirmation helpers ───────────────────────────────────────────────

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


# ── Flask routes ───────────────────────────────────────────────────────

@blueprint.route("/debug")
@superuser_required
def debug() -> str:
    backups = sorted(BACKUP_DIR.glob("backup_*.json")) if BACKUP_DIR.exists() else []
    backup_files = [b.name for b in backups]
    return render_template(
        "staff/debug.html",
        backup_files=backup_files,
    )


@blueprint.route("/debug/confirm", methods=["POST"])
@superuser_required
def confirm() -> Response:
    code = _generate_and_store_code()
    return jsonify({"code": code})


@blueprint.route("/debug/backup", methods=["POST"])
@superuser_required
def create_backup() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    task = BackgroundTask.enqueue(
        task_type="backup",
        params={},
        title="Backup Database",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Backup queued."})


@blueprint.route("/debug/backups")
@superuser_required
def list_backups() -> Response:
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


@blueprint.route("/debug/restore-newest", methods=["GET"])
def restore_newest() -> Response:
    global _last_restore_newest_time
    with _restore_newest_lock:
        now = time.time()
        if now - _last_restore_newest_time < 5:
            remaining = round(5 - (now - _last_restore_newest_time), 1)
            return jsonify({"error": f"Cooldown active. Try again in {remaining}s"}), 429
        _last_restore_newest_time = now

    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    if not backups:
        return jsonify({"error": "No backup files found"}), 404

    filename = backups[0].name
    task = BackgroundTask.enqueue(
        task_type="restore",
        params={"filename": filename},
        title=f"Restore newest: {filename}",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": f"Restoring from newest backup: {filename}"})


@blueprint.route("/debug/restore", methods=["POST"])
@superuser_required
def restore_backup() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    filename = request.form.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No backup file specified"}), 400

    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".sql"):
        return jsonify({"error": "Backup file not found"}), 404

    task = BackgroundTask.enqueue(
        task_type="restore",
        params={"filename": filename},
        title=f"Restore: {filename}",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Restore queued."})


@blueprint.route("/debug/clear", methods=["POST"])
@superuser_required
def clear_database() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    task = BackgroundTask.enqueue(
        task_type="clear",
        params={},
        title="Clear Database",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Clear queued."})


@blueprint.route("/debug/seed", methods=["POST"])
@superuser_required
def seed_data() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    try:
        n_customers = int(request.form.get("customers", "0"))
        n_months = int(request.form.get("months", "0"))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid customer count or months"}), 400

    if n_customers < 1 or n_customers > 10000:
        return jsonify({"error": "Customer count must be between 1 and 10000"}), 400
    if n_months < 1 or n_months > 240:
        return jsonify({"error": "Months must be between 1 and 240"}), 400

    task = BackgroundTask.enqueue(
        task_type="seed",
        params={"customers": n_customers, "months": n_months},
        title=f"Seed: {n_customers}c \u00d7 {n_months}m",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Seed queued."})


@blueprint.route("/debug/read-this-month", methods=["POST"])
@superuser_required
def route_read_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    task = BackgroundTask.enqueue(
        task_type="read-this-month",
        params={},
        title="Read This Month",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Read-this-month queued."})


@blueprint.route("/debug/unread-this-month", methods=["POST"])
@superuser_required
def route_unread_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    task = BackgroundTask.enqueue(
        task_type="unread-this-month",
        params={},
        title="Unread This Month",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Unread-this-month queued."})


@blueprint.route("/debug/pay-this-month", methods=["POST"])
@superuser_required
def route_pay_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    task = BackgroundTask.enqueue(
        task_type="pay-this-month",
        params={},
        title="Pay This Month",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Pay-this-month queued."})


@blueprint.route("/debug/remove-payment-this-month", methods=["POST"])
@superuser_required
def route_remove_payment_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    task = BackgroundTask.enqueue(
        task_type="remove-payment-this-month",
        params={},
        title="Remove Payment This Month",
    )
    return jsonify({"ok": True, "order_id": task.id, "message": "Remove-payment queued."})


@blueprint.route("/debug/tasks", methods=["GET"])
@superuser_required
def list_tasks() -> Response:
    current_task = BackgroundTask.query.filter_by(status="running").first()
    queue = BackgroundTask.query.filter_by(status="queued").order_by(BackgroundTask.created_at.asc()).all()
    history = BackgroundTask.query.filter(
        BackgroundTask.status.in_(["completed", "failed"])
    ).order_by(BackgroundTask.created_at.desc()).limit(20).all()

    def _to_dict(t):
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


@blueprint.route("/debug/tasks/<int:task_id>", methods=["GET"])
@superuser_required
def get_task(task_id: int) -> Response:
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
