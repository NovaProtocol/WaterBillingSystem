from __future__ import annotations

from datetime import datetime, timezone

from apps import db
from models import Billing, Customer, MeterReading
from pricing import compute_water_bill
from services.audit_service import log_action
from customer_service import recalc_total_due


def existing_this_month(
    customer_number: int, timestamp_dt: datetime, exclude_id: int | None = None
) -> MeterReading | None:
    query = MeterReading.query.filter(
        MeterReading.customer_number == customer_number,
        db.extract("year", MeterReading.timestamp) == timestamp_dt.year,
        db.extract("month", MeterReading.timestamp) == timestamp_dt.month,
    )
    if exclude_id:
        query = query.filter(MeterReading.id != exclude_id)
    return query.order_by(MeterReading.timestamp.desc()).first()


def log_duplicate_attempt(
    staff_id: int,
    staff_name: str,
    customer_number: int,
    existing: MeterReading,
    attempted_value: float,
    token_id: int | None = None,
) -> None:
    details = (
        f"Reader {staff_name} attempted duplicate reading for {customer_number}: "
        f"existing={existing.reading_value}, attempted={attempted_value}"
    )
    if token_id:
        details = f"[Token {token_id}] {details}"
    log_action(
        staff_id=staff_id,
        action_type="duplicate",
        target_type="reading",
        target_id=existing.id,
        customer_number=customer_number,
        details=details,
    )


def _create_billing_for_reading(
    reading: MeterReading, customer_number: int
) -> Billing | None:
    prev_reading = (
        MeterReading.query.filter(
            MeterReading.customer_number == customer_number,
            MeterReading.timestamp < reading.timestamp,
        )
        .order_by(MeterReading.timestamp.desc())
        .first()
    )
    if not prev_reading:
        return None

    consumption = float(float(reading.reading_value) - float(prev_reading.reading_value))
    water_bill, _ = compute_water_bill(consumption)

    billing = Billing(
        customer_number=customer_number,
        reading_id=reading.id,
        previous_reading_value=prev_reading.reading_value,
        current_reading_value=reading.reading_value,
        consumption=round(consumption, 2),
        billed_amount=round(water_bill, 2),
        penalty=0,
        paid_amount=0,
        is_paid=False,
    )
    db.session.add(billing)
    db.session.flush()
    return billing


def sync_readings(
    readings: list, token_id: int, staff_id: int, staff_name: str
) -> tuple[int, list, list]:
    recalc_customers: set[int] = set()
    synced = 0
    results = []
    errors = []
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    for i, entry in enumerate(readings):
        cust = entry.get("customer_number")
        value = entry.get("reading_value")
        ts = entry.get("timestamp", now.timestamp())

        if cust is None:
            errors.append({"index": i, "error": "customer_number is required"})
            continue
        if value is None:
            errors.append({"index": i, "error": "reading_value is required"})
            continue

        customer = Customer.query.filter_by(customer_number=cust).first()
        if not customer:
            errors.append({"index": i, "error": f"Customer {cust} not found"})
            continue

        try:
            reading_dt = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError, OverflowError, OSError):
            errors.append({"index": i, "error": "Invalid timestamp"})
            continue
        existing = existing_this_month(cust, reading_dt)
        if existing:
            log_duplicate_attempt(staff_id, staff_name, cust, existing, float(value), token_id)
            db.session.flush()
            errors.append(
                {"index": i, "error": "This meter has already been read this month"}
            )
            continue

        reading = MeterReading(
            customer_number=cust,
            reading_value=float(value),
            token_id=token_id,
            timestamp=reading_dt,
        )
        db.session.add(reading)
        db.session.flush()

        billing = _create_billing_for_reading(reading, cust)

        results.append(
            {
                "index": i,
                "reading_id": reading.id,
                "customer_number": cust,
                "billing": (
                    {
                        "id": billing.id,
                        "billed_amount": float(billing.billed_amount),
                        "consumption": float(billing.consumption) if billing.consumption else 0,
                    }
                    if billing
                    else None
                ),
            }
        )
        recalc_customers.add(cust)
        synced += 1

    db.session.commit()
    for cust in recalc_customers:
        try:
            recalc_total_due(cust)
        except Exception:
            pass
    return synced, results, errors


def upload_reading(
    customer_number: int,
    reading_value: float,
    timestamp: float,
    token_id: int,
    staff_id: int,
    staff_name: str,
) -> tuple[MeterReading | None, str | None, int | None]:
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if not customer:
        return None, f"Customer {customer_number} not found", 404

    try:
        reading_dt = datetime.fromtimestamp(float(timestamp))
    except (ValueError, TypeError, OverflowError, OSError):
        return None, "Invalid timestamp", 400
    existing = existing_this_month(customer_number, reading_dt)
    if existing:
        log_duplicate_attempt(
            staff_id, staff_name, customer_number, existing, reading_value, token_id
        )
        db.session.commit()
        return None, "This meter has already been read this month", 409

    reading = MeterReading(
        customer_number=customer_number,
        reading_value=float(reading_value),
        token_id=token_id,
        timestamp=reading_dt,
    )
    db.session.add(reading)
    db.session.flush()

    _create_billing_for_reading(reading, customer_number)
    db.session.commit()

    recalc_total_due(customer_number)
    return reading, None, 201


def drop_reading(reading_id: int, staff_id: int, reason: str) -> MeterReading | None:
    reading = MeterReading.query.get_or_404(reading_id)

    billing = Billing.query.filter_by(reading_id=reading_id).first()
    if billing and billing.is_paid:
        raise ValueError(
            f"Cannot drop reading #{reading_id}: the associated bill "
            f"has already been paid. Undo the payment first."
        )

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    if reading.timestamp.year < now.year or (
        reading.timestamp.year == now.year and reading.timestamp.month < now.month
    ):
        raise ValueError(
            f"Cannot drop reading #{reading_id}: it belongs to a previous "
            f"billing cycle. Only current-month readings can be dropped."
        )

    log_action(
        staff_id=staff_id,
        action_type="drop",
        target_type="reading",
        target_id=reading_id,
        customer_number=reading.customer_number,
        details=f"Dropped reading #{reading_id} for {reading.customer_number}. Reason: {reason}",
    )
    Billing.query.filter_by(reading_id=reading_id).delete()
    db.session.delete(reading)
    db.session.commit()
    recalc_total_due(reading.customer_number)
    return reading


def edit_reading(
    reading_id: int, new_value: float, staff_id: int
) -> MeterReading | None:
    reading = MeterReading.query.get_or_404(reading_id)
    old_value = float(reading.reading_value)
    log_action(
        staff_id=staff_id,
        action_type="edit",
        target_type="reading",
        target_id=reading_id,
        customer_number=reading.customer_number,
        details=f"Edited reading #{reading_id}: value {old_value} -> {new_value}",
    )
    reading.reading_value = new_value
    # Recompute billing for this reading
    billing = Billing.query.filter_by(reading_id=reading_id).first()
    if billing:
        prev_reading = (
            MeterReading.query.filter(
                MeterReading.customer_number == reading.customer_number,
                MeterReading.timestamp < reading.timestamp,
            )
            .order_by(MeterReading.timestamp.desc())
            .first()
        )
        if prev_reading:
            consumption = float(new_value - float(prev_reading.reading_value))
            water_bill, _ = compute_water_bill(consumption)
            billing.consumption = round(consumption, 2)
            billing.current_reading_value = new_value
            billing.billed_amount = round(water_bill, 2)
    db.session.commit()
    recalc_total_due(reading.customer_number)
    return reading
