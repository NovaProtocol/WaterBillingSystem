from __future__ import annotations

import os

from apps import db


def ensure_guest_user() -> None:
    """Provision the view-only 'guest' MySQL account used by phpMyAdmin's
    instant-login server entry. Idempotent; skipped when GUEST_DB_PASSWORD
    is not set."""
    password = os.environ.get("GUEST_DB_PASSWORD", "").strip()
    if not password:
        return

    db_name = os.environ.get("DB_NAME", "")
    if not db_name or not db_name.replace("_", "").isalnum():
        db_name = ""

    db.session.execute(db.text(
        "CREATE USER IF NOT EXISTS 'guest'@'%' IDENTIFIED BY :pw"
    ), {"pw": password})
    db.session.execute(db.text(
        "ALTER USER 'guest'@'%' IDENTIFIED BY :pw"
    ), {"pw": password})
    if db_name:
        db.session.execute(db.text(
            f"GRANT SELECT ON `{db_name}`.* TO 'guest'@'%'"
        ))
    db.session.execute(db.text("FLUSH PRIVILEGES"))
    db.session.commit()
