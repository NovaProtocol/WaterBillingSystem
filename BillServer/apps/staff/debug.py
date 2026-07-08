from __future__ import annotations

import fcntl
import json
import math
import os
import random
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import flask
from flask import Response, jsonify, render_template, request, session
from flask_login import current_user
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError

from apps import db
from apps.models import (
    ApiKey,
    Billing,
    Config,
    Customer,
    ManagementLog,
    MeterReading,
    NfcTag,
    Staff,
)
from apps.pricing import compute_water_bill
from apps.staff import blueprint

BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "db_backups"
TO_BG = BACKUP_DIR / "to_bg.json"
FROM_BG = BACKUP_DIR / "from_bg.json"
MAX_HISTORY = 20

ALL_TABLES = [
    Staff, Customer, MeterReading, Billing,
    ApiKey, NfcTag, ManagementLog, Config,
]

TABLE_NAMES = [
    "customers", "meter_readings",
    "billings", "api_keys", "nfc_tags", "management_logs", "app_config",
]


# ── File utilities (shared across Flask routes and worker) ──────────────

def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = None
            fcntl.flock(f, fcntl.LOCK_UN)
        return data
    except OSError:
        return None


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass


def _next_order_id() -> str:
    orders = _read_json(TO_BG)
    if not isinstance(orders, list):
        return "order_1"
    max_id = 0
    for o in orders:
        oid = o.get("id", "")
        if oid.startswith("order_"):
            try:
                max_id = max(max_id, int(oid[6:]))
            except ValueError:
                pass
    return f"order_{max_id + 1}"


def _append_order(order: dict[str, Any]) -> None:
    orders = _read_json(TO_BG)
    if not isinstance(orders, list):
        orders = []
    orders.append(order)
    _write_json(TO_BG, orders)


def _read_status() -> dict[str, Any]:
    data = _read_json(FROM_BG)
    if isinstance(data, dict):
        return data
    return {"current": None, "queue_depth": 0, "history": []}


# ── Superuser guard ────────────────────────────────────────────────────

def superuser_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not current_user.is_authenticated:
            return jsonify({"error": "Not authenticated"}), 401
        if current_user.username != "superuser":
            return jsonify({"error": "Superuser only"}), 403
        if os.environ.get("DEBUG", "").lower() not in ("true", "1", "yes"):
            return jsonify({"error": "DEBUG mode not enabled"}), 403
        return f(*args, **kwargs)
    return wrapper


# ── Confirmation helpers ───────────────────────────────────────────────

def _confirm_check() -> str | None:
    code = request.form.get("confirm_code", "").strip()
    expected = session.pop("debug_confirm", None)
    if not expected or code != expected:
        return None
    return code


def _generate_and_store_code() -> str:
    code = str(random.randint(10_000_000, 99_999_999))
    session["debug_confirm"] = code
    return code


# ── Serialization helpers ──────────────────────────────────────────────

def _serialize_value(v: Any) -> Any:
    if isinstance(v, (datetime, timedelta)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, float):
        return round(v, 2)
    return v


def _serialize_row(row: db.Model) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for col in sa_inspect(row).mapper.column_attrs:
        data[col.key] = _serialize_value(getattr(row, col.key))
    return data


def _deserialize_row(row_data: dict[str, Any], model_cls: type[db.Model]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in row_data.items():
        if k in ("id",):
            cleaned[k] = v
            continue
        col = getattr(model_cls, k, None)
        if col is None:
            continue
        col_type = str(col.type)
        if "BLOB" in col_type.upper() or "binary" in col_type.lower() or "LargeBinary" in col_type:
            cleaned[k] = bytes.fromhex(v) if isinstance(v, str) else v
        elif "DateTime" in col_type or "TIMESTAMP" in col_type.upper():
            cleaned[k] = datetime.fromisoformat(v) if v else None
        else:
            cleaned[k] = v
    return cleaned


# ── Bootstrap helpers ──────────────────────────────────────────────────

def _ensure_superuser() -> None:
    import binascii
    import hashlib
    existing = Staff.query.filter_by(username="superuser").first()
    if existing:
        return
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
    pwdhash = hashlib.pbkdf2_hmac("sha512", b"superuser", salt, 100000)
    supper = Staff(
        username="superuser",
        name="Superuser",
        password=salt + binascii.hexlify(pwdhash),
        can_read_meters=True, can_accept_payment=True,
        can_enroll_customer=True, can_drop_reading=True,
        can_drop_payment=True, can_enroll_staff=True,
        can_manage_billing=True,
        is_active=True,
    )
    db.session.add(supper)


def _clear_all_tables() -> None:
    import time as _time
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 0"))
            for table_name in reversed(TABLE_NAMES):
                db.session.execute(db.text(f"TRUNCATE TABLE {table_name}"))
            Staff.query.filter(Staff.username != "superuser").delete(
                synchronize_session="fetch"
            )
            db.session.commit()
            return
        except Exception as e:
            db.session.rollback()
            if "1213" in str(e):
                last_err = e
                _time.sleep(0.5 * (attempt + 1))
                continue
            raise
        finally:
            db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1"))
    if last_err:
        raise last_err


def _recalc_cumulative_balance(customer_number: str) -> None:
    total = (
        db.session.query(db.func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )
    customer = Customer.query.filter_by(customer_number=customer_number).first()
    if customer:
        customer.cumulative_balance = round(float(total), 2)


# ── Task handler functions (called by debug_worker.py) ─────────────────

def handle_backup(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    try:
        report(0, "Starting backup...")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = BACKUP_DIR / f"backup_{datetime.utcnow():%Y%m%d_%H%M%S}.json"
        data: dict[str, list[dict[str, Any]]] = {}
        for i, table_name in enumerate(TABLE_NAMES):
            pct = round((i / len(TABLE_NAMES)) * 90, 1)
            report(pct, f"Reading {table_name}...")
            model_cls = next(m for m in ALL_TABLES if m.__tablename__ == table_name)
            rows: list[db.Model] = model_cls.query.order_by(model_cls.id).all()
            data[table_name] = [_serialize_row(r) for r in rows]
            report(pct, f"  {len(rows)} rows from {table_name}")
        report(92, "Writing JSON file...")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        report(100, f"Backup saved: {path.name}")
    except SQLAlchemyError:
        db.session.rollback()
        raise


def handle_restore(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    filename = params.get("filename", "")
    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".json"):
        raise FileNotFoundError(f"Backup file not found: {filename}")

    with open(path) as f:
        data: dict[str, list[dict[str, Any]]] = json.load(f)

    report(5, f"Loaded {path.name}, clearing tables...")
    _clear_all_tables()
    _ensure_superuser()
    db.session.commit()
    report(10, "Tables cleared. Restoring data...")

    insert_order = [
        ("customers", Customer), ("nfc_tags", NfcTag),
        ("meter_readings", MeterReading), ("billings", Billing),
        ("api_keys", ApiKey), ("management_logs", ManagementLog),
        ("app_config", Config),
    ]
    total_rows = sum(len(data.get(t, [])) for t, _ in insert_order)
    processed = 0
    for table_name, model_cls in insert_order:
        rows = data.get(table_name, [])
        if not rows:
            continue
        pct = 10 + round(60 * processed / max(total_rows, 1))
        report(pct, f"Restoring {table_name} ({len(rows)} rows)...")
        for row_data in rows:
            cleaned = _deserialize_row(row_data, model_cls)
            db.session.add(model_cls(**cleaned))
            processed += 1
            if processed % 500 == 0:
                db.session.commit()
                report(10 + round(60 * processed / max(total_rows, 1)),
                       f"  {processed}/{total_rows} rows restored")
    db.session.commit()
    report(100, f"Restored from {path.name} ({total_rows} rows)")


def handle_clear(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    report(0, "Clearing tables...")
    _clear_all_tables()
    report(50, "Recreating superuser...")
    _ensure_superuser()
    db.session.commit()
    report(100, "All tables cleared. Superuser preserved.")


def handle_seed(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    n_customers = int(params.get("customers", 0))
    n_months = int(params.get("months", 0))
    report(0, "Clearing existing data...")
    _clear_all_tables()
    report(2, f"Seeding {n_customers} customers \u00d7 {n_months} months...")
    _seed_data(n_customers, n_months, report)
    _ensure_superuser()
    db.session.commit()
    report(100, f"Seeded {n_customers} customers \u00d7 {n_months} months")


def _get_customers_without_reading_this_month(now: datetime) -> list[str]:
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    subq = (
        db.session.query(MeterReading.customer_number)
        .filter(MeterReading.timestamp >= first_of_month)
        .subquery()
    )
    customers = (
        Customer.query
        .filter(Customer.is_active.is_(True))
        .filter(~Customer.customer_number.in_(subq))
        .all()
    )
    return [c.customer_number for c in customers]


def handle_read_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    report(0, "Finding customers without a reading this month...")
    now = datetime.utcnow()
    customers = _get_customers_without_reading_this_month(now)
    total = len(customers)
    report(5, f"Found {total} customers to read")
    if not total:
        report(100, "All customers already have a reading this month.")
        return
    rng = random.Random(now.year * 12 + now.month)
    created = 0
    skipped = 0
    for i, cnum in enumerate(customers):
        prev = (
            MeterReading.query
            .filter_by(customer_number=cnum)
            .order_by(MeterReading.timestamp.desc())
            .first()
        )
        if not prev:
            skipped += 1
            continue
        consumption = max(5.0, round(
            abs(rng.gauss(20, 10)) * (
                1.1 if now.month in (3, 4, 5) else
                0.95 if now.month in (6, 7, 8, 9, 10) else 0.90
            ) * rng.uniform(0.92, 1.08), 1
        ))
        new_value = round(float(prev.reading_value) + consumption, 1)
        reading_dt = now.replace(hour=rng.randint(8, 17), minute=rng.randint(0, 59))
        mr = MeterReading(
            customer_number=cnum,
            reading_value=new_value,
            token_id=1,
            timestamp=reading_dt,
            date_created=now,
            date_modified=now,
        )
        db.session.add(mr)
        db.session.flush()
        water_bill, _ = compute_water_bill(consumption)
        bill = Billing(
            customer_number=cnum,
            reading_id=mr.id,
            previous_reading_value=float(prev.reading_value),
            current_reading_value=new_value,
            consumption=consumption,
            billed_amount=water_bill,
            is_paid=False,
            date_created=now,
            date_modified=now,
        )
        db.session.add(bill)
        created += 1
        if created % 50 == 0:
            db.session.commit()
        pct = 5 + round(90 * (i + 1) / total, 1)
        report(pct, f"Read customer {i + 1}/{total} ({created} created, {skipped} skipped)")
    db.session.commit()
    report(100, f"Done. {created} readings created, {skipped} skipped.")


def handle_unread_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    report(0, "Finding this month's readings...")
    now = datetime.utcnow()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    readings = (
        MeterReading.query
        .filter(MeterReading.timestamp >= first_of_month)
        .all()
    )
    total = len(readings)
    report(5, f"Found {total} readings")
    removed = 0
    skipped_paid = 0
    for i, r in enumerate(readings):
        bill = Billing.query.filter_by(reading_id=r.id).first()
        if bill and bill.is_paid:
            skipped_paid += 1
            continue
        if bill:
            db.session.delete(bill)
        db.session.delete(r)
        removed += 1
        if removed % 100 == 0:
            db.session.commit()
        pct = 5 + round(90 * (i + 1) / max(total, 1), 1)
        report(pct, f"Unread {i + 1}/{total} ({removed} removed, {skipped_paid} skipped \u2014 already paid)")
    db.session.commit()
    report(100, f"Done. {removed} readings removed, {skipped_paid} skipped (paid).")


def handle_pay_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    import secrets
    report(0, "Finding unpaid this-month bills...")
    now = datetime.utcnow()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    unpaid_bills = (
        Billing.query
        .outerjoin(MeterReading, Billing.reading_id == MeterReading.id)
        .filter(MeterReading.timestamp >= first_of_month)
        .filter(Billing.is_paid.is_(False))
        .all()
    )
    total = len(unpaid_bills)
    report(5, f"Found {total} unpaid bills")
    paid = 0
    for i, bill in enumerate(unpaid_bills):
        bill.is_paid = True
        bill.paid_amount = round(float(bill.billed_amount) + float(bill.penalty), 2)
        bill.receipt_number = "MONTHLY-" + secrets.token_hex(4).upper()
        bill.cashier_id = 1
        bill.payment_timestamp = now
        bill.date_paid = now
        paid += 1
        if paid % 100 == 0:
            db.session.commit()
        report(5 + round(90 * (i + 1) / max(total, 1), 1),
               f"Paid {i + 1}/{total}")
    db.session.commit()
    report(100, f"Done. {paid} bills paid.")


def handle_remove_payment_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    report(0, "Finding paid this-month bills...")
    now = datetime.utcnow()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    paid_bills = (
        Billing.query
        .outerjoin(MeterReading, Billing.reading_id == MeterReading.id)
        .filter(MeterReading.timestamp >= first_of_month)
        .filter(Billing.is_paid.is_(True))
        .all()
    )
    total = len(paid_bills)
    report(5, f"Found {total} paid bills")
    undone = 0
    for i, bill in enumerate(paid_bills):
        bill.is_paid = False
        bill.paid_amount = 0
        bill.receipt_number = None
        bill.cashier_id = None
        bill.payment_timestamp = None
        bill.date_paid = None
        bill.carryover_offset = 0
        undone += 1
        if undone % 100 == 0:
            db.session.commit()
        report(5 + round(90 * (i + 1) / max(total, 1), 1),
               f"Reverted {i + 1}/{total}")
    db.session.commit()
    seen: set[str] = set()
    for bill in paid_bills:
        if bill.customer_number not in seen:
            seen.add(bill.customer_number)
            _recalc_cumulative_balance(bill.customer_number)
    report(100, f"Done. {undone} bills reverted.")


HANDLERS: dict[str, Callable[[dict[str, Any], Callable[[float, str], None]], None]] = {
    "backup": handle_backup,
    "restore": handle_restore,
    "clear": handle_clear,
    "seed": handle_seed,
    "read-this-month": handle_read_this_month,
    "unread-this-month": handle_unread_this_month,
    "pay-this-month": handle_pay_this_month,
    "remove-payment-this-month": handle_remove_payment_this_month,
}


# ── Flask routes ───────────────────────────────────────────────────────

@blueprint.route("/debug")
@superuser_required
def debug() -> str:
    backups = sorted(BACKUP_DIR.glob("backup_*.json")) if BACKUP_DIR.exists() else []
    backup_files = [b.name for b in backups]
    return render_template(
        "staff/debug.html",
        backup_files=backup_files,
    )


@blueprint.route("/debug/confirm", methods=["POST"])
@superuser_required
def confirm() -> Response:
    code = _generate_and_store_code()
    return jsonify({"code": code})


@blueprint.route("/debug/backup", methods=["POST"])
@superuser_required
def create_backup() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400
    order = {
        "id": _next_order_id(),
        "type": "backup",
        "params": {},
        "title": "Backup Database",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Backup queued."})


@blueprint.route("/debug/backups")
@superuser_required
def list_backups() -> Response:
    if not BACKUP_DIR.exists():
        return jsonify({"backups": []})
    backups = sorted(BACKUP_DIR.glob("backup_*.json"), reverse=True)
    return jsonify({
        "backups": [
            {
                "name": b.name,
                "size": b.stat().st_size,
                "modified": datetime.fromtimestamp(b.stat().st_mtime).isoformat(),
            }
            for b in backups
        ]
    })


@blueprint.route("/debug/restore", methods=["POST"])
@superuser_required
def restore_backup() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    filename = request.form.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No backup file specified"}), 400

    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".json"):
        return jsonify({"error": "Backup file not found"}), 404

    order = {
        "id": _next_order_id(),
        "type": "restore",
        "params": {"filename": filename},
        "title": f"Restore: {filename}",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Restore queued."})


@blueprint.route("/debug/clear", methods=["POST"])
@superuser_required
def clear_database() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    order = {
        "id": _next_order_id(),
        "type": "clear",
        "params": {},
        "title": "Clear Database",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Clear queued."})


@blueprint.route("/debug/seed", methods=["POST"])
@superuser_required
def seed_data() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    try:
        n_customers = int(request.form.get("customers", "0"))
        n_months = int(request.form.get("months", "0"))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid customer count or months"}), 400

    if n_customers < 1 or n_customers > 10000:
        return jsonify({"error": "Customer count must be between 1 and 10000"}), 400
    if n_months < 1 or n_months > 240:
        return jsonify({"error": "Months must be between 1 and 240"}), 400

    order = {
        "id": _next_order_id(),
        "type": "seed",
        "params": {"customers": n_customers, "months": n_months},
        "title": f"Seed: {n_customers}c \u00d7 {n_months}m",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Seed queued."})


@blueprint.route("/debug/read-this-month", methods=["POST"])
@superuser_required
def route_read_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    order = {
        "id": _next_order_id(),
        "type": "read-this-month",
        "params": {},
        "title": "Read This Month",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Read-this-month queued."})


@blueprint.route("/debug/unread-this-month", methods=["POST"])
@superuser_required
def route_unread_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    order = {
        "id": _next_order_id(),
        "type": "unread-this-month",
        "params": {},
        "title": "Unread This Month",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Unread-this-month queued."})


@blueprint.route("/debug/pay-this-month", methods=["POST"])
@superuser_required
def route_pay_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    order = {
        "id": _next_order_id(),
        "type": "pay-this-month",
        "params": {},
        "title": "Pay This Month",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Pay-this-month queued."})


@blueprint.route("/debug/remove-payment-this-month", methods=["POST"])
@superuser_required
def route_remove_payment_this_month() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    order = {
        "id": _next_order_id(),
        "type": "remove-payment-this-month",
        "params": {},
        "title": "Remove Payment This Month",
        "created_at": time.time(),
    }
    _append_order(order)
    return jsonify({"ok": True, "order_id": order["id"], "message": "Remove-payment queued."})


@blueprint.route("/debug/tasks", methods=["GET"])
@superuser_required
def list_tasks() -> Response:
    status = _read_status()
    orders = _read_json(TO_BG)
    status["queue_depth"] = len(orders) if isinstance(orders, list) else 0
    return jsonify(status)


@blueprint.route("/debug/tasks/<task_id>", methods=["GET"])
@superuser_required
def get_task(task_id: str) -> Response:
    status = _read_status()
    current = status.get("current")
    if current and current.get("id") == task_id:
        return jsonify({"task": current})
    for t in status.get("history", []):
        if t.get("id") == task_id:
            return jsonify({"task": t})
    return jsonify({"error": "Task not found"}), 404


# ── Seed data ──────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Juan", "Maria", "Jose", "Ana", "Pedro", "Rosa", "Antonio", "Luz",
    "Francisco", "Dolores", "Manuel", "Carmen", "Ramon", "Teresa", "Eduardo",
    "Gloria", "Emilio", "Feliza", "Ricardo", "Elena", "Alfredo", "Consuelo",
    "Benito", "Corazon", "Arturo", "Aurora", "Carlos", "Natividad", "Diego",
    "Imelda", "Felipe", "Ligaya", "Miguel", "Perlita", "Roberto", "Remedios",
    "Vicente", "Salud", "Andres", "Trinidad", "Domingo", "Leonila", "Esteban",
    "Milagros", "Fernando", "Beatriz", "Guillermo", "Ester", "Hilario",
    "Concepcion", "Jaime", "Angelita", "Lorenzo", "Fe", "Nestor", "Purita",
    "Orlando", "Zenaida", "Rolando", "Natividad",
]
LAST_NAMES = [
    "dela Cruz", "Garcia", "Reyes", "Ramos", "Mendoza", "Santos", "Flores",
    "Gonzales", "Bautista", "Villanueva", "Fernandez", "Rivera", "Aquino",
    "Castro", "Lopez", "Torres", "Domingo", "Martinez", "Gutierrez", "Rosario",
    "Salvador", "Navarro", "Padilla", "Marquez", "Estrada", "Velasco",
    "Pascual", "Soriano", "Dizon", "Manuel", "De Leon", "Enriquez", "Tolentino",
    "Santiago", "Luna", "Mercado", "Agustin", "Hernandez", "Alvarez",
    "Pineda", "Cabrera", "Cruz", "Alcantara", "Magbanua", "Macaraeg",
    "Bacani", "Dela Peña", "Capili", "Aguilar", "Jacinto", "Laxamana",
]
PHASE_DATA = [
    {"phase": "Phase L-1 (St. Jude Village)", "block": f"Block {i}", "street": s}
    for s in ["St. Peregrine St", "St. Peter Lane", "St. Jude Ave", "San Lorenzo Ruiz St"]
    for i in range(1, 15)
] + [
    {"phase": "Phase L-2A (St. Jude Village)", "block": f"Block {i}", "street": s}
    for s in ["St. Paul St", "St. John St", "St. Matthew St", "Immaculate Conception Drive"]
    for i in range(1, 15)
] + [
    {"phase": "Phase L-2C (St. Jude East)", "block": f"Block {i}", "street": s}
    for s in ["St. Thomas St", "St. Luke St", "St. Mark St", "San Pedro Calungsod St"]
    for i in range(1, 35)
] + [
    {"phase": "Phase L-3D (St. Jude East)", "block": f"Block {i}", "street": s}
    for s in ["St. Joseph St", "St. Mary St", "St. Anne St", "St. Therese St"]
    for i in range(1, 25)
] + [
    {"phase": "Phase P-1 (Pagbilao)", "block": f"Block {i}", "street": s}
    for s in ["San Vicente Ferrer St", "San Isidro Labrador St", "San Roque St"]
    for i in range(1, 10)
] + [
    {"phase": "Phase S-1 (Sariaya)", "block": f"Block {i}", "street": s}
    for s in ["San Francisco de Asis St", "Santa Clara St", "Santo Domingo St"]
    for i in range(1, 8)
] + [
    {"phase": "Phase C-1 (Candelaria)", "block": f"Block {i}", "street": s}
    for s in ["San Miguel St", "San Gabriel St", "San Rafael St"]
    for i in range(1, 5)
]
BASE_LAT = 13.9360069
BASE_LON = 121.6314674


def _coord_offset(rng: random.Random) -> tuple[float, float]:
    r = rng.random() * 1500
    theta = rng.random() * 2 * math.pi
    dlat = r / 111320
    dlon = r / (111320 * math.cos(math.radians(BASE_LAT)))
    return round(BASE_LAT + dlat * math.cos(theta), 7), round(
        BASE_LON + dlon * math.sin(theta), 7
    )


def _seasonal_factor(month: int, rng: random.Random) -> float:
    if month in (3, 4, 5):
        return rng.uniform(1.10, 1.30)
    elif month in (6, 7, 8, 9, 10):
        return rng.uniform(0.90, 1.05)
    else:
        return rng.uniform(0.82, 0.98)


def _generate_consumption(months: int, rng: random.Random) -> list[float]:
    base = rng.uniform(12, 40)
    values: list[float] = []
    for m in range(months):
        year = m // 12
        month_num = (m % 12) + 1
        grown = base * ((1.0 + rng.uniform(-0.02, 0.05)) ** year)
        seasonal = _seasonal_factor(month_num, rng)
        noise = rng.uniform(0.92, 1.08)
        consumption = max(5.0, round(grown * seasonal * noise, 1))
        values.append(consumption)
    return values


def _seed_data(
    n_customers: int, n_months: int,
    _report: Callable[[float, str], None] | None = None,
) -> None:
    _report_fn = _report if _report else lambda p, m: None

    import binascii
    import hashlib
    import secrets as _secrets

    _report_fn(2, "Clearing existing staff...")
    Staff.query.filter(Staff.username != "superuser").delete(
        synchronize_session="fetch"
    )
    db.session.flush()

    rng = random.Random(42)
    now = datetime.utcnow()

    def _hash_pass(password: str) -> bytes:
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
        pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)
        return salt + binascii.hexlify(pwdhash)

    latest_month = now.month
    latest_year = now.year
    ref_dt = datetime(latest_year, latest_month, min(now.day, 28))
    date_slots: list[datetime] = []
    for i in range(n_months - 1, -1, -1):
        y = ref_dt.year
        m = ref_dt.month - i
        while m < 1:
            m += 12
            y -= 1
        date_slots.append(datetime(y, m, min(now.day, 28)))

    staff_users = [
        {"username": "admin", "name": "Admin", "all": True},
        {"username": "cashier1", "name": "Cashier"}, {"username": "cashier2", "name": "Cashier"},
        {"username": "reader1", "name": "Reader"},
        {"username": "manager", "name": "Manager"},
        {"username": "enroller", "name": "Enroller"},
    ]
    staff_ids: dict[str, int] = {}
    for s in staff_users:
        perms = {p: True for p in [
            "can_read_meters", "can_accept_payment", "can_enroll_customer",
            "can_drop_reading", "can_drop_payment", "can_enroll_staff", "can_manage_billing",
        ]} if s.get("all") else {}
        if s["username"] == "cashier1":
            perms["can_accept_payment"] = True
        elif s["username"] == "cashier2":
            perms["can_accept_payment"] = True
        elif s["username"] == "reader1":
            perms["can_read_meters"] = True
        elif s["username"] == "manager":
            perms["can_drop_payment"] = perms["can_drop_reading"] = perms["can_manage_billing"] = True
        elif s["username"] == "enroller":
            perms["can_enroll_customer"] = perms["can_enroll_staff"] = True

        staff = Staff(
            username=s["username"],
            name=s["name"],
            password=_hash_pass(s["username"]),
            **perms,
            is_active=True,
            date_created=now,
            last_modified=now,
        )
        db.session.add(staff)
        db.session.flush()
        staff_ids[s["username"]] = staff.id

    cashier_id = staff_ids.get("cashier1", next(iter(staff_ids.values())))
    _report_fn(4, f"Created {len(staff_users)} staff accounts")

    api_key_map: dict[int, int] = {}
    for sid_name, sid in staff_ids.items():
        if sid_name in ("superuser", "admin", "reader1"):
            raw = "CRDC-" + _secrets.token_hex(16).upper()
            ak = ApiKey(key=raw, label=f"{sid_name} token", staff_id=sid, is_active=True)
            db.session.add(ak)
            db.session.flush()
            api_key_map[sid] = ak.id

    reader_token_ids = list(api_key_map.values())

    for ci in range(n_customers):
        cnum = f"{ci + 1}"
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        pd = rng.choice(PHASE_DATA)
        coord = _coord_offset(rng)
        cust = Customer(
            customer_number=cnum,
            name=f"{first} {last}",
            address=f"{rng.randint(1, 50)} {pd['street']}",
            contact_number="09" + "".join(rng.choice("0123456789") for _ in range(9)),
            email=f"c{ci+1}{first.lower()}@gmail.com",
            x_coordinate=coord[0],
            y_coordinate=coord[1],
            phase=pd["phase"],
            block=pd["block"],
            cumulative_balance=0.00,
            max_meter_value=99999.00,
            is_active=True,
            date_created=now,
            date_modified=now,
        )
        db.session.add(cust)
        db.session.flush()

        cust_rng = random.Random(ci * 1000 + 42)
        consumptions = _generate_consumption(n_months, cust_rng)
        meter_value = round(rng.uniform(100, 500), 1)
        reading_ids: list[int] = []

        for month_idx in range(n_months):
            reading_dt = date_slots[month_idx].replace(
                hour=rng.randint(8, 17), minute=rng.randint(0, 59),
            )
            if month_idx > 0:
                meter_value = round(meter_value + consumptions[month_idx - 1], 1)
            mr = MeterReading(
                customer_number=cnum,
                reading_value=meter_value,
                token_id=rng.choice(reader_token_ids),
                timestamp=reading_dt,
                date_created=now,
                date_modified=now,
            )
            db.session.add(mr)
            db.session.flush()
            reading_ids.append(mr.id)

        cum_balance = 0.0
        for month_idx in range(1, n_months):
            prev_val = sum(consumptions[:month_idx])
            curr_val = sum(consumptions[:month_idx + 1])
            consumption = round(curr_val - prev_val, 1)
            reading_id = reading_ids[month_idx]
            water_bill, _ = compute_water_bill(consumption)

            if month_idx == n_months - 1:
                bill = Billing(
                    customer_number=cnum,
                    reading_id=reading_id,
                    previous_reading_value=prev_val,
                    current_reading_value=curr_val,
                    consumption=consumption,
                    billed_amount=water_bill,
                    penalty=0, paid_amount=0, carryover_offset=0,
                    is_paid=False,
                    date_created=now,
                    date_modified=now,
                )
                db.session.add(bill)
                continue

            pay_dt = date_slots[month_idx] + timedelta(days=rng.randint(3, 28))
            penalty = 15.0 if pay_dt > date_slots[month_idx] + timedelta(days=7) else 0.0
            total_due = round(water_bill + penalty, 2)

            if cum_balance > 0.01:
                effective_due = max(0.0, round(total_due - cum_balance, 2))
            else:
                effective_due = total_due

            if effective_due <= 0.01:
                paid_amount = 0.0
                carryover_offset = round(-total_due, 2)
            else:
                paid_amount = float(math.ceil(effective_due / 50.0) * 50)
                carryover_offset = round(paid_amount - total_due, 2)

            cum_balance = round(cum_balance + carryover_offset, 2)

            bill = Billing(
                customer_number=cnum,
                reading_id=reading_id,
                previous_reading_value=prev_val,
                current_reading_value=curr_val,
                consumption=consumption,
                billed_amount=water_bill,
                penalty=penalty,
                paid_amount=paid_amount,
                carryover_offset=carryover_offset,
                is_paid=True,
                receipt_number=f"R{rng.randint(10000000, 99999999)}",
                cashier_id=cashier_id,
                payment_timestamp=pay_dt,
                date_paid=pay_dt,
                date_created=now,
                date_modified=now,
            )
            db.session.add(bill)

        cust.cumulative_balance = round(cum_balance, 2)

        if (ci + 1) % 10 == 0:
            db.session.commit()
            _report_fn(4 + round(93 * (ci + 1) / n_customers, 1),
                       f"Seeding customer {ci + 1}/{n_customers}...")

    db.session.commit()
    _report_fn(97, "Finalizing...")
