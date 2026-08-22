from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from models import Billing, Customer
from sqlalchemy import func, or_
from sqlalchemy.orm import Session


def _ensure_penalty_sync(billing, session) -> float:
    from datetime import datetime, timedelta, timezone

    from pricing import DUE_DAYS, LATE_PENALTY

    if billing.is_paid:
        return float(billing.penalty or 0)
    reading_ts = (
        billing.reading.timestamp
        if billing.reading
        else (billing.date_created or datetime.now(tz=timezone.utc).replace(tzinfo=None))
    )
    due_dt = reading_ts + timedelta(days=DUE_DAYS)
    if (
        datetime.now(tz=timezone.utc).replace(tzinfo=None) > due_dt
        and float(billing.penalty or 0) == 0
    ):
        billing.penalty = LATE_PENALTY
        session.flush()
    return float(billing.penalty or 0)


def _is_name_query(s: str) -> bool:
    return bool(s) and all(c.isalpha() or c in " .-'" for c in s)


def get_customer_by_number(
    customer_number: int,
    *,
    session: Session | None = None,
) -> Customer | None:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    return session.query(Customer).filter_by(customer_number=customer_number).first()


def create_customer(
    data: dict, *, session: Session | None = None
) -> tuple[Customer | None, str | None]:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    customer_number = data.get("customer_number")
    name = data.get("name", "").strip()
    address = data.get("address", "").strip()
    contact_number = data.get("contact_number", "").strip()
    email = data.get("email", "").strip()

    if customer_number is None:
        return None, "Customer number is required"

    if session.query(Customer).filter_by(customer_number=customer_number).first():
        return None, "Customer number already exists"

    customer = Customer(
        customer_number=customer_number,
        name=name or None,
        address=address or None,
        contact_number=contact_number or None,
        email=email or None,
        phase=data.get("phase") or None,
        block=data.get("block") or None,
        street=data.get("street") or None,
        x_coordinate=data.get("x_coordinate"),
        y_coordinate=data.get("y_coordinate"),
        cumulative_balance=0.00,
        max_meter_value=data.get("max_meter_value", 99999.00),
    )
    session.add(customer)
    session.commit()
    return customer, None


def update_customer(
    customer: Customer,
    data: dict,
    *,
    session: Session | None = None,
) -> None:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    customer.name = data.get("name", customer.name) or None
    customer.address = data.get("address", customer.address) or None
    customer.contact_number = data.get("contact_number", customer.contact_number) or None
    customer.email = data.get("email", customer.email) or None
    customer.phase = data.get("phase", customer.phase) or None
    customer.block = data.get("block", customer.block) or None
    customer.street = data.get("street", customer.street) or None
    customer.x_coordinate = data.get("x_coordinate", customer.x_coordinate)
    customer.y_coordinate = data.get("y_coordinate", customer.y_coordinate)
    if "max_meter_value" in data:
        customer.max_meter_value = data.get("max_meter_value")
    session.commit()


def toggle_active(customer: Customer, *, session: Session | None = None) -> None:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    customer.is_active = not customer.is_active
    if not customer.is_active:
        customer.deleted_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    else:
        customer.deleted_at = None
    session.commit()


def _total_carryover(customer_number: int, session) -> float:
    return float(
        session.query(func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )


def compute_customer_due(
    customer: Customer,
    *,
    session: Session | None = None,
) -> float:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    unpaid_bills = (
        session.query(Billing)
        .filter_by(customer_number=customer.customer_number, is_paid=False)
        .all()
    )
    total_due = 0.0
    for bill in unpaid_bills:
        _ensure_penalty_sync(bill, session)
        bill_due = (
            float(bill.billed_amount or 0) + float(bill.penalty or 0) - float(bill.paid_amount or 0)
        )
        total_due += max(0, bill_due)
    balance = _total_carryover(customer.customer_number, session)
    return max(0, round(total_due - balance, 2))


def recalc_total_due(customer_number: int, *, session: Session | None = None) -> float:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    customer = session.query(Customer).filter_by(customer_number=customer_number).first()
    if not customer:
        return 0.0
    total = compute_customer_due(customer, session=session)
    customer.total_due = total
    session.commit()
    return total


def compute_batch_due(
    customers: list[Customer],
    *,
    session: Session | None = None,
) -> dict[int, float]:
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    if not customers:
        return {}
    cnums = [c.customer_number for c in customers]

    unpaid_bills = (
        session.query(Billing)
        .filter(
            Billing.customer_number.in_(cnums),
            Billing.is_paid.is_(False),
        )
        .all()
    )

    bills_by_cust: dict[int, list[Billing]] = defaultdict(list)
    for bill in unpaid_bills:
        bills_by_cust[bill.customer_number].append(bill)

    offset_rows = (
        session.query(
            Billing.customer_number,
            func.sum(Billing.carryover_offset).label("total_offset"),
        )
        .filter(Billing.customer_number.in_(cnums))
        .group_by(Billing.customer_number)
        .all()
    )
    offset_map: dict[int, float] = {r.customer_number: float(r.total_offset) for r in offset_rows}

    result: dict[int, float] = {}
    for c in customers:
        bills = bills_by_cust.get(c.customer_number, [])
        total_due = 0.0
        for bill in bills:
            bill_due = (
                float(bill.billed_amount or 0)
                + float(bill.penalty or 0)
                - float(bill.paid_amount or 0)
            )
            total_due += max(0, bill_due)
        balance = offset_map.get(c.customer_number, 0)
        result[c.customer_number] = max(0, round(total_due - balance, 2))
    return result


def list_customers(
    page: int = 1,
    per_page: int = 50,
    q: str | None = None,
    sort_by: str = "name",
    sort_dir: str = "asc",
    *,
    session: Session | None = None,
) -> tuple[list[Customer], int]:
    """Returns (items, total)."""
    if session is None:
        raise ValueError("session is required (Flask-SQLAlchemy db.session is gone)")
    per_page = min(max(per_page, 10), 200)
    query = session.query(Customer)

    if q:
        if q.isdigit():
            prefix = int(q)
            max_num = session.query(func.max(Customer.customer_number)).scalar() or 0
            multiplier = 1
            conditions = []
            while prefix * multiplier <= max_num:
                lower = prefix * multiplier
                upper = prefix * multiplier + (multiplier - 1)
                conditions.append(Customer.customer_number.between(lower, upper))
                multiplier *= 10
            if conditions:
                query = query.filter(or_(*conditions))
        elif _is_name_query(q):
            query = query.filter(Customer.name.like(f"{q}%"))

    if sort_by == "customer_number":
        order = Customer.customer_number
        order = order.asc() if sort_dir == "asc" else order.desc()
    elif sort_by == "total_due":
        col = Customer.total_due
        order = col.asc() if sort_dir == "asc" else col.desc()
    else:
        col = getattr(Customer, sort_by, Customer.name)
        order = col.asc() if sort_dir == "asc" else col.desc()

    total = query.count()
    items = query.order_by(order).offset((page - 1) * per_page).limit(per_page).all()
    return items, total
