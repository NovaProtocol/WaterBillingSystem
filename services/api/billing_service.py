from __future__ import annotations

from datetime import datetime, timedelta

from apps import db
from models import Billing
from pricing import DUE_DAYS, LATE_PENALTY


def ensure_penalty(billing: Billing) -> float:
    """Check if a bill is overdue and calculate penalty.

    If the bill is unpaid, past its due date, and penalty hasn't been written yet,
    permanently add the penalty to the DB. Returns the current penalty amount.
    """
    if billing.is_paid:
        return float(billing.penalty or 0)

    # Use reading timestamp if available, else billing creation date
    if billing.reading:
        reading_ts = billing.reading.timestamp
    else:
        reading_ts = billing.date_created or datetime.utcnow()

    due_dt = reading_ts + timedelta(days=DUE_DAYS)
    if datetime.utcnow() > due_dt and float(billing.penalty or 0) == 0:
        billing.penalty = LATE_PENALTY
        db.session.flush()

    return float(billing.penalty or 0)



