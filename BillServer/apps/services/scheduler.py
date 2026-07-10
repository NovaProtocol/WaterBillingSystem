from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from apps import db
from apps.models import XenditTransaction

scheduler = BackgroundScheduler(daemon=True)


def _reconcile_single(txn: XenditTransaction) -> None:
    from apps.billing.api import _process_xendit_payment, _reverse_xendit_payment, _init_xendit

    _init_xendit()

    key = os.environ.get("XENDIT_API_KEY", "")
    if not key or key == "your-xendit-secret-api-key":
        return

    import xendit
    from xendit.apis import PaymentRequestApi

    client = xendit.ApiClient()
    api_instance = PaymentRequestApi(client)

    try:
        response = api_instance.get_payment_request_by_id(txn.xendit_pr_id)
        status = getattr(response, "status", None)
        if not status:
            return
        status_str = str(status)

        if status_str in ("SUCCEEDED", "PAID", "SETTLED"):
            payment_id = getattr(response, "id", "")
            if payment_id:
                txn.xendit_payment_id = str(payment_id)
            db.session.commit()
            _process_xendit_payment(txn)
        elif status_str in ("FAILED", "EXPIRED"):
            txn.status = "FAILED"
            txn.error_message = f"Payment failed (reconciled: {status_str})"
            db.session.commit()
        elif status_str == "REVERSED":
            _reverse_xendit_payment(txn)
    except Exception:
        pass


def reconcile_next_pending(app: Flask) -> None:
    threshold = datetime.utcnow() - timedelta(hours=1)
    txn = (
        XenditTransaction.query.filter_by(status="PENDING")
        .filter(XenditTransaction.date_modified < threshold)
        .order_by(XenditTransaction.date_modified.asc())
        .first()
    )
    if not txn:
        return

    txn.date_modified = datetime.utcnow()
    db.session.commit()

    with app.app_context():
        _reconcile_single(txn)

    if txn.status == "PENDING":
        age = datetime.utcnow() - txn.date_created
        if age > timedelta(hours=24):
            txn.status = "EXPIRED"
            txn.error_message = "Payment link expired after 24 hours"
            db.session.commit()


def start_scheduler(app: Flask) -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        func=reconcile_next_pending,
        trigger="interval",
        minutes=5,
        id="xendit_reconcile",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        kwargs={"app": app},
    )
    scheduler.start()
    app.logger.info("Background scheduler started (reconcile every 5min)")
