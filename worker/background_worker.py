"""
Dedicated background worker process.

A FastAPI app run by granian (--workers 1 — exactly one claim loop).
Polls the background_tasks table for queued tasks, executes handlers,
and updates progress in the DB. Claims exactly ONE job at a time;
concurrency happens only inside a job (bounded by WORKER_JOB_CONCURRENCY).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.orm.exc import ObjectDeletedError

from db_async import init_db, init_engine, session, session_factory, sync_session
from shared.logger import attach_sqlite_logging

logger = logging.getLogger("background_worker")

POLL_INTERVAL = 1.0
PROGRESS_PERSIST_INTERVAL = 0.5


def require_env(*names):
    for name in names:
        if not os.environ.get(name):
            print(f"FATAL: Environment variable {name} is required but not set.")
            sys.exit(1)


require_env('DEPLOYMENT_TYPE', 'DB_ENGINE', 'DB_HOST', 'DB_PORT', 'DB_NAME',
            'DB_USERNAME', 'DB_PASS', 'XENDIT_API_KEY')

logging.basicConfig(level=logging.INFO, format="%(message)s")
attach_sqlite_logging('worker')


class TaskState:
    """Shared mutable progress state for the running task. The claim loop
    persists it to the DB on a timer; handlers only mutate it in memory
    (safe to touch from concurrent gather tasks)."""

    def __init__(self) -> None:
        self.task_id: int | None = None
        self.task_type: str = ""
        self.title: str = ""
        self.progress: float = 0.0
        self.messages: list[str] = []
        self.dirty: bool = False


_state = TaskState()


def _report(pct: float, msg: str) -> None:
    _state.progress = pct
    _state.messages.append(msg)
    _state.dirty = True


async def _persist_progress() -> None:
    if not _state.dirty or _state.task_id is None:
        return
    try:
        from models import BackgroundTask
        async with session_factory()() as s:
            task = (
                await s.execute(
                    select(BackgroundTask).where(BackgroundTask.id == _state.task_id)
                )
            ).scalar_one_or_none()
            if task is None:
                return
            task.progress = _state.progress
            task.messages = list(_state.messages)
            await s.commit()
            _state.dirty = False
    except Exception as e:
        logger.warning("[background_worker] progress persist failed: %s", e)


async def _mark_stale_failed() -> None:
    async with session_factory()() as s:
        from models import BackgroundTask
        stale = (
            await s.execute(
                select(BackgroundTask).where(
                    BackgroundTask.status == "running",
                    BackgroundTask.started_at
                    < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5),
                )
            )
        ).scalars().all()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for t in stale:
            logger.warning("[background_worker] Found stale running task #%s (%s) — marking as failed",
                           t.id, t.task_type)
            t.status = "failed"
            t.finished_at = now
        if stale:
            await s.commit()


async def _claim_task() -> Any | None:
    from models import BackgroundTask

    await _mark_stale_failed()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with session_factory()() as s:
        task = (
            await s.execute(
                select(BackgroundTask)
                .where(
                    BackgroundTask.status == "queued",
                    (BackgroundTask.scheduled_at.is_(None))
                    | (BackgroundTask.scheduled_at <= now),
                )
                .order_by(BackgroundTask.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if task is None:
            return None
        task.status = "running"
        task.started_at = now
        await s.commit()
        await s.refresh(task)
        return task


# ── Temporary compatibility shim ─────────────────────────────────────────
# Handlers in task_handlers.py are still sync and use `apps.db.session`
# (Flask-SQLAlchemy). Run them in a thread with a Flask app context until
# Task 3 rewrites them to async. Then this block is deleted.
from flask import Flask  # noqa: E402  (removed in Task 3)
from apps import db  # noqa: E402  (removed in Task 3)

_flask_shim_app = Flask(__name__)
_flask_shim_app.config.from_object("config.DebugConfig" if os.environ.get("DEPLOYMENT_TYPE") == "DEBUG" else "config.ProductionConfig")
db.init_app(_flask_shim_app)
# ─────────────────────────────────────────────────────────────────────────


async def _execute_task(task: Any) -> None:
    from task_handlers import HANDLERS

    handler = HANDLERS.get(task.task_type)
    _state.task_id = task.id
    _state.task_type = task.task_type
    _state.title = task.title or task.task_type
    _state.progress = 0.0
    _state.messages = []
    _state.dirty = False

    if not handler:
        logger.error("[background_worker] Unknown task type: %s", task.task_type)
        async with session_factory()() as s:
            row = (await s.execute(
                select(type(task)).where(type(task).id == task.id))).scalar_one_or_none()
            if row is not None:
                row.status = "failed"
                row.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await s.commit()
        return

    task_id = task.id
    task_title = task.title or task.task_type
    logger.info("[background_worker] Starting: %s", task_title)

    # TEMP shim: run the sync handler under a Flask app context in a thread.
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _run_handler_shim(handler, task.params or {}))

    # Persist final state (handler may have deleted the row, e.g. restore).
    async with session_factory()() as s:
        from models import BackgroundTask
        row = (await s.execute(
            select(BackgroundTask).where(BackgroundTask.id == task_id))).scalar_one_or_none()
        if row is None:
            logger.warning("[background_worker] Task #%s row unavailable (restore?)", task_id)
            return
        row.status = "completed"
        row.progress = 100.0
        row.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await s.commit()
    logger.info("[background_worker] Completed: %s", task_title)


def _run_handler_shim(handler, params: dict) -> None:
    """TEMP: wraps the sync handler in a Flask app context. Deleted in Task 3."""
    with _flask_shim_app.app_context():
        try:
            handler(params, _report)
        except Exception as e:
            logger.error("[background_worker] Error: %s", e)


async def claim_loop() -> None:
    logger.info("[background_worker] Worker ready. Polling for tasks...")
    while True:
        task = await _claim_task()
        if task is None:
            await asyncio.sleep(POLL_INTERVAL)
            continue
        persist_task = asyncio.create_task(_progress_persister())
        try:
            await _execute_task(task)
        finally:
            persist_task.cancel()
            await asyncio.gather(persist_task, return_exceptions=True)


async def _progress_persister() -> None:
    try:
        while True:
            await asyncio.sleep(PROGRESS_PERSIST_INTERVAL)
            await _persist_progress()
    except asyncio.CancelledError:
        await _persist_progress()
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    await init_db()
    from models import BackgroundTask
    await BackgroundTask.enqueue_unique(
        task_type="xendit_reconcile",
        title="Xendit Reconciliation",
    )
    loop_task = asyncio.create_task(claim_loop())
    yield
    loop_task.cancel()
    await asyncio.gather(loop_task, return_exceptions=True)


app = FastAPI(title="Cotta Water Billing Worker", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mode": "idle" if _state.task_id is None else "working",
        "current_task": _state.task_type or None,
        "progress": _state.progress,
        "last_message": _state.messages[-1] if _state.messages else None,
    }
