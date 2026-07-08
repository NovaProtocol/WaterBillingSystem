"""
Background worker for debug tasks.

Launched as a subprocess from run.py. Polls to_bg.json for orders,
processes them one at a time, and writes status to from_bg.json.

Runs independently of Gunicorn workers — the JSON files are the
shared state, protected by fcntl.flock.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

# Ensure the project root is on sys.path so we can import from apps
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT.parent / ".env")

import fcntl

from apps import create_app, db
from apps.config import config_dict

BACKUP_DIR = _PROJECT_ROOT / "db_backups"
TO_BG = BACKUP_DIR / "to_bg.json"
FROM_BG = BACKUP_DIR / "from_bg.json"
POLL_INTERVAL = 0.5
FLUSH_INTERVAL = 0.4
MAX_HISTORY = 20


# ── File utilities ─────────────────────────────────────────────────────

def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = None
            fcntl.flock(f, fcntl.LOCK_UN)
        return data
    except OSError:
        return None


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass


def _pop_order() -> dict[str, Any] | None:
    orders = _read_json(TO_BG)
    if not isinstance(orders, list) or not orders:
        return None
    order = orders.pop(0)
    _write_json(TO_BG, orders)
    return order


def _queue_depth() -> int:
    orders = _read_json(TO_BG)
    return len(orders) if isinstance(orders, list) else 0


# ── Status file management ─────────────────────────────────────────────

def _write_idle() -> None:
    _write_json(FROM_BG, {"current": None, "queue_depth": _queue_depth(), "history": []})


def _write_running(reporter: ProgressReporter) -> None:
    data = _read_json(FROM_BG)
    if not isinstance(data, dict):
        data = {"current": None, "queue_depth": 0, "history": []}
    data["current"] = reporter.to_dict("running")
    data["queue_depth"] = _queue_depth()
    _write_json(FROM_BG, data)


def _move_to_history(reporter: ProgressReporter, status: str) -> None:
    data = _read_json(FROM_BG)
    if not isinstance(data, dict):
        data = {"current": None, "queue_depth": 0, "history": []}
    entry = reporter.to_dict(status)
    data["current"] = None
    data["queue_depth"] = _queue_depth()
    data["history"].insert(0, entry)
    data["history"] = data["history"][:MAX_HISTORY]
    _write_json(FROM_BG, data)


# ── Progress reporter ──────────────────────────────────────────────────

class ProgressReporter:
    def __init__(self, order_id: str, title: str) -> None:
        self._order_id = order_id
        self._title = title
        self._progress = 0.0
        self._messages: list[str] = []
        self._started_at = time.time()
        self._ended_at: float | None = None
        self._last_flush = 0.0

    def progress(self, pct: float, msg: str) -> None:
        self._progress = pct
        self._messages.append(msg)
        now = time.time()
        if now - self._last_flush >= FLUSH_INTERVAL:
            self._flush_status("running")
            self._last_flush = now

    def flush(self) -> None:
        self._flush_status("running")

    def _flush_status(self, status: str) -> None:
        data = _read_json(FROM_BG)
        if not isinstance(data, dict):
            data = {"current": None, "queue_depth": 0, "history": []}
        data["current"] = self.to_dict(status)
        _write_json(FROM_BG, data)

    def to_dict(self, status: str) -> dict[str, Any]:
        return {
            "id": self._order_id,
            "title": self._title,
            "status": status,
            "progress": round(self._progress, 1),
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "messages": list(self._messages),
        }


# ── Order execution ────────────────────────────────────────────────────

def execute_order(app: Any, order: dict[str, Any]) -> None:
    from apps.staff.debug import HANDLERS

    order_type = order.get("type", "")
    handler = HANDLERS.get(order_type)
    if not handler:
        print(f"[debug_worker] Unknown order type: {order_type}", flush=True)
        return

    reporter = ProgressReporter(order["id"], order.get("title", order_type))
    _write_running(reporter)

    print(f"[debug_worker] Starting: {order.get('title', order_type)}", flush=True)

    try:
        with app.app_context():
            handler(order.get("params", {}), reporter.progress)
        reporter._ended_at = time.time()
        _move_to_history(reporter, "completed")
        print(f"[debug_worker] Completed: {order.get('title', order_type)}", flush=True)
    except Exception as e:
        reporter._ended_at = time.time()
        reporter._messages.append(f"ERROR: {e}")
        _move_to_history(reporter, "error")
        print(f"[debug_worker] Error: {order.get('title', order_type)}: {e}", flush=True)


# ── Main loop ──────────────────────────────────────────────────────────

def main() -> None:
    print("[debug_worker] Starting background worker...", flush=True)

    os.environ.setdefault("DEPLOYMENT_TYPE", "DEBUG")
    get_config_mode = "Debug" if os.environ.get("DEPLOYMENT_TYPE") == "DEBUG" else "Production"
    app_config = config_dict[get_config_mode.capitalize()]
    app = create_app(app_config)

    with app.app_context():
        db.create_all()

    # Clear queue and status on fresh start
    _write_json(TO_BG, [])
    _write_idle()

    print("[debug_worker] Worker ready. Polling for orders...", flush=True)

    while True:
        order = _pop_order()
        if order:
            execute_order(app, order)
            _write_idle()
        else:
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
