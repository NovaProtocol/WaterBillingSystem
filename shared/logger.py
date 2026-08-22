from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone

_LOG_DIR = "/var/log/app"
_PRUNE_LIMIT = 5000
_local = threading.local()


def _get_db(name: str) -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        path = os.path.join(_LOG_DIR, f"logs_{name}.db")
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                logger TEXT NOT NULL,
                message TEXT NOT NULL,
                traceback TEXT,
                method TEXT,
                path TEXT,
                status_code INTEGER,
                remote_addr TEXT,
                container TEXT
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
        _local.conn = conn
    return _local.conn


class SQLiteLogHandler(logging.Handler):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def emit(self, record: logging.LogRecord) -> None:
        try:
            conn = _get_db(self.name)
            ts = (
                datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                )[:-3]
                + "Z"
            )
            tb = None
            if record.exc_info and record.exc_info[0]:
                tb = self.format(record)

            extra = getattr(record, "http", {})
            conn.execute(
                """INSERT INTO logs (timestamp, level, logger, message, traceback,
                                    method, path, status_code, remote_addr, container)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts,
                    record.levelname,
                    record.name,
                    record.getMessage(),
                    tb,
                    extra.get("method"),
                    extra.get("path"),
                    extra.get("status_code"),
                    extra.get("remote_addr"),
                    extra.get("container"),
                ),
            )
            conn.execute(
                f"DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT {_PRUNE_LIMIT})"
            )
            conn.commit()
        except Exception:
            self.handleError(record)


def attach_sqlite_logging(name: str) -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)
    handler = SQLiteLogHandler(name)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def query_logs(
    service: str | None = None,
    level: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    import glob

    os.makedirs(_LOG_DIR, exist_ok=True)
    pattern = os.path.join(_LOG_DIR, f"logs_{service or '*'}.db")
    files = sorted(glob.glob(pattern))
    results: list[dict] = []

    for path in files:
        svc = os.path.splitext(os.path.basename(path))[0].replace("logs_", "", 1)
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            parts = [
                "SELECT id, timestamp, level, logger, message, traceback, "
                "method, path, status_code, remote_addr, container FROM logs"
            ]
            wheres: list[str] = []
            params: list = []
            if level:
                wheres.append("level = ?")
                params.append(level.upper())
            if q:
                wheres.append("message LIKE ?")
                params.append(f"%{q}%")
            if wheres:
                parts.append("WHERE " + " AND ".join(wheres))
            parts.append("ORDER BY id DESC LIMIT ? OFFSET ?")
            params.extend([limit, offset])
            for row in conn.execute(" ".join(parts), params).fetchall():
                results.append(
                    {
                        "service": svc,
                        "id": row[0],
                        "timestamp": row[1],
                        "level": row[2],
                        "logger": row[3],
                        "message": row[4],
                        "traceback": row[5],
                        "method": row[6],
                        "path": row[7],
                        "status_code": row[8],
                        "remote_addr": row[9],
                        "container": row[10],
                    }
                )
            conn.close()
        except Exception as e:
            logging.getLogger("api").exception(f"Failed to query logs from {path}: {e}")

    return results
