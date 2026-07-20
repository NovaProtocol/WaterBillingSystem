from __future__ import annotations

from datetime import datetime, timezone

from apps import db
from models import ManagementLog


def log_action(
    staff_id: int,
    action_type: str,
    target_type: str,
    target_id: int,
    details: str,
    customer_number: int | None = None,
) -> ManagementLog:
    log = ManagementLog(
        staff_id=staff_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        customer_number=customer_number,
        details=details,
        timestamp=datetime.now(tz=timezone.utc).replace(tzinfo=None),
    )
    db.session.add(log)
    return log
