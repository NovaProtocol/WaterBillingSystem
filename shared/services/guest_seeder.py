from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_guest_user(session: Session | None = None) -> None:
    """Provision the view-only 'guest' MySQL account used by phpMyAdmin's
    instant-login server entry. Idempotent; skipped when GUEST_DB_PASSWORD
    is not set."""
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    password = os.environ["GUEST_DB_PASSWORD"].strip()
    if not password:
        return

    db_name = os.environ["DB_NAME"]
    if not db_name or not db_name.replace("_", "").isalnum():
        db_name = ""

    session.execute(
        text("CREATE USER IF NOT EXISTS 'guest'@'%' IDENTIFIED BY :pw"),
        {"pw": password},
    )
    session.execute(text("ALTER USER 'guest'@'%' IDENTIFIED BY :pw"), {"pw": password})
    if db_name:
        session.execute(text(f"GRANT SELECT ON `{db_name}`.* TO 'guest'@'%'"))
    session.execute(text("FLUSH PRIVILEGES"))
    session.commit()
