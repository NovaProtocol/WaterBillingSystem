from __future__ import annotations

import logging
import secrets
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from apps import db
from models import Billing, Customer, Staff
from services.audit_service import log_action

logger = logging.getLogger('api')


def _generate_receipt(now: datetime) -> str:
    return "RCP-" + str(int(now.timestamp())) + "-" + secrets.token_hex(4).upper()


def _recalc_total_due(customer_number: int) -> None:
    total = 0.0
    unpaid_bills = (
        Billing.query
        .filter_by(customer_number=customer_number, is_paid=False)
        .all()
    )
    for bill in unpaid_bills:
        bill_due = (
            float(bill.billed_amount or 0)
            + float(bill.penalty or 0)
            - float(bill.paid_amount or 0)
        )
        total += max(0, bill_due)
    balance = float(
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar() or 0
    )
    total_due = max(0, round(total - balance, 2))
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if customer:
        customer.total_due = total_due


def recalc_cumulative_balance(
    customer_number: int, *, customer: Customer | None = None
) -> None:
    if customer is None:
        customer = (
            Customer.query
            .filter_by(customer_number=customer_number)
            .with_for_update()
            .first()
        )
    if not customer:
        return
    total = (
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )
    customer.cumulative_balance = round(float(total), 2)


def submit_payment(
    customer_number: int,
    amount: float,
    cashier_id: int,
) -> tuple[dict | None, str | None, int]:
    if customer_number is None or amount <= 0:
        return None, "Customer number and valid amount required", 400

    customer = (
        Customer.query
        .filter_by(customer_number=customer_number)
        .with_for_update()
        .first()
    )
    if not customer:
        return None, "Customer not found", 404

    unpaid_bills = (
        Billing.query
        .filter_by(customer_number=customer_number, is_paid=False)
        .order_by(Billing.date_created.asc())
        .with_for_update()
        .all()
    )

    total_carryover = float(
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    receipt = _generate_receipt(now)
    cash_remaining = amount
    carryover_used = 0.0
    last_paid_bill: Billing | None = None
    bills_paid = 0

    for bill in unpaid_bills:
        total_due = round(
            float(bill.billed_amount)
            + float(bill.penalty)
            - float(bill.paid_amount),
            2,
        )
        if total_due <= 0.01:
            continue

        available = round(cash_remaining + max(0, total_carryover - carryover_used), 2)
        if available < total_due:
            break

        bill.paid_amount = round(float(bill.paid_amount) + total_due, 2)
        bill.is_paid = True
        bill.receipt_number = receipt
        bill.cashier_id = cashier_id
        bill.payment_timestamp = now
        bill.date_paid = now
        bills_paid += 1
        last_paid_bill = bill

        if cash_remaining >= total_due:
            cash_remaining = round(cash_remaining - total_due, 2)
        else:
            carryover_used = round(carryover_used + total_due - cash_remaining, 2)
            cash_remaining = 0.0

    if carryover_used > 0.01 and last_paid_bill:
        last_paid_bill.carryover_offset = round(
            float(last_paid_bill.carryover_offset or 0) - carryover_used, 2
        )

    if cash_remaining > 0.01:
        if last_paid_bill:
            last_paid_bill.carryover_offset = round(
                float(last_paid_bill.carryover_offset or 0) + cash_remaining, 2
            )
        else:
            cumulative = float(customer.cumulative_balance or 0)
            customer.cumulative_balance = round(cumulative + cash_remaining, 2)

    recalc_cumulative_balance(customer_number, customer=customer)
    _recalc_total_due(customer_number)
    db.session.flush()

    return (
        {
            "message": f"Payment recorded — {bills_paid} bill(s) fully paid",
            "receipt_number": receipt if bills_paid > 0 else None,
            "receipts": [receipt] if bills_paid > 0 else [],
            "amount": amount,
        },
        None,
        201,
    )


def drop_payment(payment_id: int, staff_id: int, reason: str) -> dict | None:
    billing = Billing.query.with_for_update().get_or_404(payment_id)
    receipt = billing.receipt_number
    if not receipt:
        return {"error": "No receipt found", "message": "No receipt found"}

    group = Billing.query.filter_by(receipt_number=receipt).with_for_update().all()
    customer_number = billing.customer_number

    total_group_amount = sum(float(b.paid_amount) for b in group)
    details = (
        f"Undid receipt {receipt} ({customer_number}, "
        f"{len(group)} bill(s), amount={total_group_amount}). "
        f"Reason: {reason}"
    )
    log_action(
        staff_id=staff_id,
        action_type="drop",
        target_type="billing",
        target_id=payment_id,
        customer_number=customer_number,
        details=details,
    )

    for b in group:
        b.is_paid = False
        b.paid_amount = 0
        b.receipt_number = None
        b.cashier_id = None
        b.payment_timestamp = None
        b.date_paid = None
        b.carryover_offset = 0

    recalc_cumulative_balance(customer_number)
    _recalc_total_due(customer_number)
    db.session.commit()

    return {"message": f"Payment group ({receipt}) undone — {len(group)} bill(s) reverted"}


def parse_date_range(
    period: str,
    start_str: str | None,
    end_str: str | None,
    ref_date: datetime | None = None,
) -> tuple[datetime, datetime]:
    if ref_date is None:
        ref_date = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    if period == "custom":
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d") if start_str else ref_date
            end = (
                datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)
                if end_str
                else ref_date + timedelta(days=1)
            )
            return start, end
        except (ValueError, TypeError) as e:
            logger.exception(f"Invalid custom date range start={start_str} end={end_str}: {e}")
            start = datetime(ref_date.year, ref_date.month, ref_date.day)
            return start, start + timedelta(days=1)
    elif period == "weekly":
        try:
            ref = datetime.strptime(start_str, "%Y-%m-%d") if start_str else ref_date
        except ValueError as e:
            logger.exception(f"Invalid weekly date start={start_str}: {e}")
            ref = ref_date
        start = ref - timedelta(days=ref.weekday())
        start = datetime(start.year, start.month, start.day)
        return start, start + timedelta(days=7)
    elif period == "yearly":
        try:
            ref = datetime.strptime(start_str, "%Y-%m-%d") if start_str else ref_date
        except ValueError as e:
            logger.exception(f"Invalid yearly date start={start_str}: {e}")
            ref = ref_date
        start = datetime(ref.year, 1, 1)
        return start, datetime(ref.year + 1, 1, 1)
    elif period == "monthly":
        try:
            ref = datetime.strptime(start_str, "%Y-%m-%d") if start_str else ref_date
        except ValueError as e:
            logger.exception(f"Invalid monthly date start={start_str}: {e}")
            ref = ref_date
        start = datetime(ref.year, ref.month, 1)
        if ref.month == 12:
            return start, datetime(ref.year + 1, 1, 1)
        return start, datetime(ref.year, ref.month + 1, 1)
    else:
        try:
            ref = datetime.strptime(start_str, "%Y-%m-%d") if start_str else ref_date
        except ValueError as e:
            logger.exception(f"Invalid daily date start={start_str}: {e}")
            ref = ref_date
        start = datetime(ref.year, ref.month, ref.day)
        return start, start + timedelta(days=1)


def compute_intervals(
    start: datetime, end: datetime, group_days: int
) -> list[tuple[datetime, datetime]]:
    if group_days > 1:
        intervals = []
        cursor = start
        while cursor < end:
            interval_end = min(cursor + timedelta(days=group_days), end)
            intervals.append((cursor, interval_end))
            cursor = interval_end
        return intervals
    return [(start, end)]


def compute_cashier_tally(
    start: datetime, end: datetime, staff_id: int | None, group_days: int
) -> tuple[list, bool]:
    intervals = compute_intervals(start, end, group_days)

    tally_data = []
    for i_start, i_end in intervals:
        query = db.session.query(
            Billing.cashier_id,
            db.func.sum(Billing.paid_amount).label("total"),
        ).filter(
            Billing.payment_timestamp >= i_start,
            Billing.payment_timestamp < i_end,
            Billing.is_paid.is_(True),
        )
        if staff_id is not None:
            query = query.filter(Billing.cashier_id == staff_id)
        rows = query.group_by(Billing.cashier_id).all()

        staff_map = {s.id: s for s in Staff.query.all()}
        for row in rows:
            s = staff_map.get(row.cashier_id)
            if s and float(row.total or 0) > 0:
                tally_data.append(
                    {
                        "username": s.name or s.username,
                        "total": round(float(row.total), 2),
                        "interval_start": i_start.strftime("%b %d"),
                        "interval_end": (i_end - timedelta(days=1)).strftime("%b %d"),
                        "interval_label": (
                            i_start.strftime("%b %d")
                            if group_days <= 1 or len(intervals) <= 1
                            else f"{i_start.strftime('%b %d')}–{(i_end - timedelta(days=1)).strftime('%b %d')}"
                        ),
                    }
                )

    if group_days > 1 and len(intervals) > 1:
        matrix = defaultdict(lambda: defaultdict(float))
        for row in tally_data:
            matrix[row["username"]][row["interval_label"]] += row["total"]
        all_intervals = sorted(set(r["interval_label"] for r in tally_data))
        tally = []
        for username, intervals_dict in sorted(matrix.items()):
            row = {"username": username}
            row["total"] = round(sum(intervals_dict.values()), 2)
            row["intervals"] = {k: round(intervals_dict[k], 2) for k in all_intervals}
            row["interval_list"] = all_intervals
            if row["total"] > 0:
                tally.append(row)
        return tally, True
    else:
        tally = []
        seen = {}
        for row in tally_data:
            if row["username"] in seen:
                seen[row["username"]] += row["total"]
            else:
                seen[row["username"]] = row["total"]
        for username, total in sorted(seen.items()):
            if total > 0:
                tally.append({"username": username, "total": round(total, 2)})
        return tally, False


def compute_nav_dates(
    period: str, start: datetime, end: datetime, today: datetime
) -> dict:
    nav = {}
    if period == "daily":
        nav["prev_date"] = (start - timedelta(days=1)).strftime("%Y-%m-%d")
        nav["next_date"] = (start + timedelta(days=1)).strftime("%Y-%m-%d")
        nav["display"] = start.strftime("%B %d, %Y")
        nav["is_today"] = start.date() == today.date()
        nav["nav_date"] = start.strftime("%Y-%m-%d")
    elif period == "weekly":
        nav["prev_date"] = (start - timedelta(days=7)).strftime("%Y-%m-%d")
        nav["next_date"] = (start + timedelta(days=7)).strftime("%Y-%m-%d")
        nav["display"] = (
            f"{start.strftime('%b %d')} – {(end - timedelta(days=1)).strftime('%b %d, %Y')}"
        )
        nav["is_today"] = start.date() <= today.date() < end.date()
        nav["nav_date"] = start.strftime("%Y-%m-%d")
    elif period == "yearly":
        nav["prev_date"] = datetime(start.year - 1, 1, 1).strftime("%Y-%m-%d")
        nav["next_date"] = datetime(start.year + 1, 1, 1).strftime("%Y-%m-%d")
        nav["display"] = start.strftime("%Y")
        nav["is_today"] = start.date() <= today.date() < end.date()
        nav["nav_date"] = start.strftime("%Y-06-15")
    elif period == "monthly":
        prev_start = (start - timedelta(days=1)).replace(day=1)
        nav["prev_date"] = prev_start.strftime("%Y-%m-%d")
        nav["next_date"] = end.strftime("%Y-%m-%d")
        nav["display"] = start.strftime("%B %Y")
        nav["is_today"] = start.date() <= today.date() < end.date()
        nav["nav_date"] = start.strftime("%Y-%m-%d")
    else:
        nav["prev_date"] = None
        nav["next_date"] = None
        nav["display"] = (
            f"{start.strftime('%b %d, %Y')} – {(end - timedelta(days=1)).strftime('%b %d, %Y')}"
        )
        nav["is_today"] = False
        nav["nav_date"] = None
    return nav
