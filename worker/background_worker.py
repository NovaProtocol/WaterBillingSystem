"""
Dedicated background worker process.

Launched as a subprocess from run.py. Polls the background_tasks table
for queued tasks, executes handlers, and updates progress in the DB.

Runs independently of Gunicorn workers — the DB is the shared state.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask
from sqlalchemy.orm.exc import ObjectDeletedError

from apps import db
from config import config_dict
from models import BackgroundTask
from services.task_handlers import HANDLERS



def create_worker_app():
    dep_type = os.environ.get("DEPLOYMENT_TYPE", "PRODUCTION")
    app = Flask(__name__)
    app.config.from_object(config_dict[dep_type])
    db.init_app(app)
    return app

POLL_INTERVAL = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("background_worker")

os.environ.setdefault("DEPLOYMENT_TYPE", "DEBUG")


def _claim_task() -> BackgroundTask | None:
    # Clean stale running tasks (crashed worker, abandoned)
    stale = BackgroundTask.query.filter(
        BackgroundTask.status == "running",
        BackgroundTask.started_at < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5),
    ).all()
    for s in stale:
        logger.warning("[background_worker] Found stale running task #%s (%s) — marking as failed", s.id, s.task_type)
        s.status = "failed"
        s.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if stale:
        db.session.commit()

    task = (
        BackgroundTask.query
        .filter(
            BackgroundTask.status == "queued",
            (BackgroundTask.scheduled_at.is_(None)) | (BackgroundTask.scheduled_at <= datetime.now(timezone.utc).replace(tzinfo=None)),
        )
        .order_by(BackgroundTask.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .one_or_none()
    )
    if task is None:
        db.session.commit()
        return None
    task.status = "running"
    task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    db.session.refresh(task)
    return task


def _execute_task(task: BackgroundTask) -> None:
    handler = HANDLERS.get(task.task_type)
    if not handler:
        logger.error("[background_worker] Unknown task type: %s", task.task_type)
        task.status = "failed"
        task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        return

    # Cache values before handler runs — restore may delete the row mid-execution
    task_id = task.id
    task_type = task.task_type
    task_title = task.title or task.task_type

    def _report(pct: float, msg: str) -> None:
        try:
            task.progress = pct
            messages = list(task.messages or [])
            messages.append(msg)
            task.messages = messages
            db.session.commit()
        except (ObjectDeletedError, Exception):
            db.session.rollback()

    logger.info("[background_worker] Starting: %s", task_title)
    try:
        handler(task.params or {}, _report)
        logger.info("[background_worker] Completed: %s", task_title)
    except Exception as e:
        logger.error("[background_worker] Error: %s: %s", task_title, e)

    # Try to update task status, but don't crash if row was deleted (e.g. restore)
    try:
        task.status = "completed"
        task.progress = 100.0
        task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
    except (ObjectDeletedError, Exception) as e:
        db.session.rollback()
        logger.warning("[background_worker] Task #%s row unavailable (restore?) — %s", task_id, e)


def main() -> None:
    logger.info("[background_worker] Starting background worker...")

    app = create_worker_app()

    with app.app_context():
        db.create_all()

    logger.info("[background_worker] Worker ready. Polling for tasks...")

    with app.app_context():
        BackgroundTask.enqueue_unique(
            task_type="xendit_reconcile",
            title="Xendit Reconciliation",
        )

        while True:
            task = _claim_task()
            if task:
                _execute_task(task)
            else:
                time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
