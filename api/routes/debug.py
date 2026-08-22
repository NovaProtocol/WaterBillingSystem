from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

router = APIRouter(prefix="/api")
from db_async import session
from models import (
    ApiKey,
    BackgroundTask,
    Billing,
    Customer,
    ManagementLog,
    MeterReading,
    NfcTag,
    PaymentMethod,
    Staff,
    XenditTransaction,
)

logger = logging.getLogger("api")

BACKUP_DIR = Path("/app/db_backups")
_last_restore_newest_time = 0.0
_restore_newest_lock = threading.Lock()


def _superuser_only() -> None:
    if not BACKUP_DIR.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)


async def _enqueue(
    task_type: str, params: dict | None = None, title: str | None = None
) -> BackgroundTask:
    task = BackgroundTask(
        task_type=task_type,
        params=params or {},
        title=title or task_type,
        status="queued",
    )
    session().add(task)
    await session().commit()
    return task


@router.get("/debug/stats")
async def debug_stats():
    _superuser_only()
    counts = {}

    async def _count(model, where=None):
        stmt = select(func.count()).select_from(model)
        if where is not None:
            stmt = stmt.where(where)
        return (await session().execute(stmt)).scalar() or 0

    counts["customers"] = await _count(Customer, Customer.is_active.is_(True))
    counts["customers_total"] = await _count(Customer)
    counts["readings"] = await _count(MeterReading)
    counts["billings"] = await _count(Billing)
    counts["unpaid_bills"] = await _count(Billing, Billing.is_paid.is_(False))
    counts["paid_bills"] = await _count(Billing, Billing.is_paid.is_(True))
    counts["staff"] = await _count(Staff)
    counts["api_keys"] = await _count(ApiKey)
    counts["nfc_tags"] = await _count(NfcTag)
    counts["management_logs"] = await _count(ManagementLog)
    counts["xendit_transactions"] = await _count(XenditTransaction)
    counts["payment_methods"] = await _count(PaymentMethod, PaymentMethod.is_active.is_(True))
    counts["background_tasks"] = await _count(BackgroundTask)
    return counts


@router.post("/debug/backup")
async def debug_backup():
    _superuser_only()
    task = await _enqueue(task_type="backup", params={}, title="Backup Database")
    return {"ok": True, "order_id": task.id, "message": "Backup queued."}


@router.get("/debug/backups")
async def debug_backups():
    _superuser_only()
    if not BACKUP_DIR.exists():
        return {"backups": []}
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    return {
        "backups": [
            {
                "name": b.name,
                "size": b.stat().st_size,
                "modified": datetime.fromtimestamp(b.stat().st_mtime).isoformat(),
            }
            for b in backups
        ]
    }


@router.post("/debug/restore")
async def debug_restore(request: Request):
    _superuser_only()
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    filename = str(data.get("filename", "") or "").strip()
    if not filename:
        return JSONResponse({"error": "No backup file specified"}, status_code=400)
    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".sql"):
        return JSONResponse({"error": "Backup file not found"}, status_code=404)
    task = await _enqueue(
        task_type="restore", params={"filename": filename}, title=f"Restore: {filename}"
    )
    return {"ok": True, "order_id": task.id, "message": "Restore queued."}


@router.get("/debug/restore-newest")
async def debug_restore_newest():
    global _last_restore_newest_time
    with _restore_newest_lock:
        now = time.time()
        if now - _last_restore_newest_time < 5:
            remaining = round(5 - (now - _last_restore_newest_time), 1)
            return JSONResponse(
                {"error": f"Cooldown active. Try again in {remaining}s"},
                status_code=429,
            )
        _last_restore_newest_time = now
    _superuser_only()
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), reverse=True)
    if not backups:
        return JSONResponse({"error": "No backup files found"}, status_code=404)
    filename = backups[0].name
    task = await _enqueue(
        task_type="restore",
        params={"filename": filename},
        title=f"Restore newest: {filename}",
    )
    return {
        "ok": True,
        "order_id": task.id,
        "message": f"Restoring from newest backup: {filename}",
    }


@router.post("/debug/clear")
async def debug_clear():
    _superuser_only()
    task = await _enqueue(task_type="clear", params={}, title="Clear Database")
    return {"ok": True, "order_id": task.id, "message": "Clear queued."}


@router.post("/debug/seed")
async def debug_seed(request: Request):
    _superuser_only()
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    try:
        n_customers = int(data.get("customers", "0"))
        n_months = int(data.get("months", "0"))
    except (ValueError, TypeError):
        logger.exception("Invalid seed parameters:")
        return JSONResponse({"error": "Invalid customer count or months"}, status_code=400)

    total_entries = n_customers * n_months
    if n_customers < 1 or n_months < 2 or total_entries > 10_000_000:
        return JSONResponse(
            {
                "error": "Invalid range: customers × months must be between 1×2 and 10,000,000 total entries"
            },
            status_code=400,
        )

    n_cashiers = int(data.get("cashiers", "2"))
    n_readers = int(data.get("readers", "2"))
    read_current = data.get("read_current", "no")
    pay_last = data.get("pay_last", "random")
    randomize_months = data.get("randomize_months", "yes")
    allow_deactivation = data.get("allow_deactivation", "no")

    params = {
        "customers": n_customers,
        "months": n_months,
        "cashiers": n_cashiers,
        "readers": n_readers,
        "read_current": read_current,
        "pay_last": pay_last,
        "randomize_months": randomize_months,
        "allow_deactivation": allow_deactivation,
    }
    task = await _enqueue(
        task_type="seed",
        params=params,
        title=f"Seed: {n_customers}c × {n_months}m",
    )
    return {"ok": True, "order_id": task.id, "message": "Seed queued."}


@router.post("/debug/read-month")
async def debug_read_month():
    _superuser_only()
    task = await _enqueue(task_type="read-this-month", params={}, title="Read This Month")
    return {"ok": True, "order_id": task.id, "message": "Read-this-month queued."}


@router.post("/debug/unread-month")
async def debug_unread_month():
    _superuser_only()
    task = await _enqueue(task_type="unread-this-month", params={}, title="Unread This Month")
    return {"ok": True, "order_id": task.id, "message": "Unread-this-month queued."}


@router.post("/debug/pay-month")
async def debug_pay_month():
    _superuser_only()
    task = await _enqueue(task_type="pay-this-month", params={}, title="Pay This Month")
    return {"ok": True, "order_id": task.id, "message": "Pay-this-month queued."}


@router.post("/debug/remove-pay-month")
async def debug_remove_pay_month():
    _superuser_only()
    task = await _enqueue(
        task_type="remove-payment-this-month",
        params={},
        title="Remove Payment This Month",
    )
    return {"ok": True, "order_id": task.id, "message": "Remove-payment queued."}


@router.get("/debug/tasks")
async def debug_tasks():
    _superuser_only()
    current_result = await session().execute(
        select(BackgroundTask).where(BackgroundTask.status == "running").limit(1)
    )
    current_task = current_result.scalar_one_or_none()
    queue_result = await session().execute(
        select(BackgroundTask)
        .where(BackgroundTask.status == "queued")
        .order_by(BackgroundTask.created_at.asc())
    )
    queue = queue_result.scalars().all()
    history_result = await session().execute(
        select(BackgroundTask)
        .where(BackgroundTask.status.in_(["completed", "failed"]))
        .order_by(BackgroundTask.created_at.desc())
        .limit(20)
    )
    history = history_result.scalars().all()

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

    return {
        "current": _to_dict(current_task) if current_task else None,
        "queue_depth": len(queue),
        "history": [_to_dict(t) for t in history],
    }


@router.get("/debug/tasks/{task_id}")
async def debug_task(task_id: int):
    _superuser_only()
    task = await session().get(BackgroundTask, task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return {
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
    }
