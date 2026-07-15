from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, func

from apps import db
from models import Billing, Customer
from billing_service import ensure_penalty


def get_customer_or_404(customer_id: int) -> Customer:
    return Customer.query.get_or_404(customer_id)


def get_customer_by_number(customer_number: str) -> Customer | None:
    return Customer.query.filter_by(customer_number=customer_number).first()


def create_customer(data: dict) -> tuple[Customer | None, str | None]:
    customer_number = data.get("customer_number", "").strip()
    name = data.get("name", "").strip()
    address = data.get("address", "").strip()
    contact_number = data.get("contact_number", "").strip()
    email = data.get("email", "").strip()

    if not customer_number:
        return None, "Customer number is required"

    if Customer.query.filter_by(customer_number=customer_number).first():
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
    db.session.add(customer)
    db.session.commit()
    return customer, None


def update_customer(customer: Customer, data: dict) -> None:
    customer.name = data.get("name", customer.name) or None
    customer.address = data.get("address", customer.address) or None
    customer.contact_number = (
        data.get("contact_number", customer.contact_number) or None
    )
    customer.email = data.get("email", customer.email) or None
    customer.phase = data.get("phase", customer.phase) or None
    customer.block = data.get("block", customer.block) or None
    customer.street = data.get("street", customer.street) or None
    customer.x_coordinate = data.get("x_coordinate", customer.x_coordinate)
    customer.y_coordinate = data.get("y_coordinate", customer.y_coordinate)
    if "max_meter_value" in data:
        customer.max_meter_value = data.get("max_meter_value")
    db.session.commit()


def toggle_active(customer: Customer) -> None:
    customer.is_active = not customer.is_active
    if not customer.is_active:
        customer.deleted_at = datetime.utcnow()
    else:
        customer.deleted_at = None
    db.session.commit()


def _total_carryover(customer_number: str) -> float:
    return float(
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )


def compute_customer_due(customer: Customer) -> float:
    unpaid_bills = (
        Billing.query
        .filter_by(customer_number=customer.customer_number, is_paid=False)
        .all()
    )
    total_due = 0.0
    for bill in unpaid_bills:
        ensure_penalty(bill)
        bill_due = (
            float(bill.billed_amount or 0)
            + float(bill.penalty or 0)
            - float(bill.paid_amount or 0)
        )
        total_due += max(0, bill_due)
    balance = _total_carryover(customer.customer_number)
    return max(0, round(total_due - balance, 2))


def compute_batch_due(customers: list[Customer]) -> dict[str, float]:
    if not customers:
        return {}
    cnums = [c.customer_number for c in customers]

    unpaid_bills = (
        Billing.query
        .filter(
            Billing.customer_number.in_(cnums),
            Billing.is_paid.is_(False),
        )
        .all()
    )

    bills_by_cust: dict[str, list[Billing]] = defaultdict(list)
    for bill in unpaid_bills:
        bills_by_cust[bill.customer_number].append(bill)

    offset_rows = (
        db.session.query(
            Billing.customer_number,
            db.func.sum(Billing.carryover_offset).label("total_offset"),
        )
        .filter(Billing.customer_number.in_(cnums))
        .group_by(Billing.customer_number)
        .all()
    )
    offset_map: dict[str, float] = {
        r.customer_number: float(r.total_offset) for r in offset_rows
    }

    result: dict[str, float] = {}
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
) -> Any:
    per_page = min(max(per_page, 10), 200)
    query = Customer.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            Customer.customer_number.like(like)
            | Customer.name.like(like)
            | Customer.contact_number.like(like)
        )
    if sort_by == "customer_number":
        order = func.cast(func.substring(Customer.customer_number, 2), Integer)
        order = order.asc() if sort_dir == "asc" else order.desc()
    elif sort_by == "total_due":
        order = None
    else:
        col = getattr(Customer, sort_by, Customer.name)
        order = col.asc() if sort_dir == "asc" else col.desc()
    if order is not None:
        return query.order_by(order).paginate(
            page=page, per_page=per_page, error_out=False
        )
    return query.paginate(page=page, per_page=per_page, error_out=False)
