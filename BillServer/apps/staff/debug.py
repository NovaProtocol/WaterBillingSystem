from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

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

ALL_TABLES = [
    Staff, Customer, MeterReading, Billing,
    ApiKey, NfcTag, ManagementLog, Config,
]

TABLE_NAMES = [
    "customers", "meter_readings",
    "billings", "api_keys", "nfc_tags", "management_logs", "app_config",
]


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

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"backup_{datetime.utcnow():%Y%m%d_%H%M%S}.json"

    data: dict[str, list[dict[str, Any]]] = {}
    for table_name in TABLE_NAMES:
        model_cls = next(m for m in ALL_TABLES if m.__tablename__ == table_name)
        rows: list[db.Model] = model_cls.query.order_by(model_cls.id).all()
        data[table_name] = [_serialize_row(r) for r in rows]

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return jsonify({"message": f"Backup saved: {path.name}", "file": path.name})


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

    with open(path) as f:
        data: dict[str, list[dict[str, Any]]] = json.load(f)

    try:
        _clear_all_tables()

        insert_order = [
            ("staff", Staff), ("customers", Customer), ("nfc_tags", NfcTag),
            ("meter_readings", MeterReading), ("billings", Billing),
            ("api_keys", ApiKey), ("management_logs", ManagementLog),
            ("app_config", Config),
        ]
        for table_name, model_cls in insert_order:
            rows = data.get(table_name, [])
            if not rows:
                continue
            for row_data in rows:
                cleaned = {}
                for k, v in row_data.items():
                    if k in ("date_created", "date_modified", "last_modified"):
                        if v:
                            cleaned[k] = datetime.fromisoformat(v)
                        continue
                    col = getattr(model_cls, k, None)
                    if col is None:
                        continue
                    col_type = str(col.type)
                    if "BLOB" in col_type.upper() or "binary" in col_type.lower() or "LargeBinary" in col_type:
                        cleaned[k] = bytes.fromhex(v) if isinstance(v, str) else v
                    elif "DateTime" in col_type or "TIMESTAMP" in col_type.upper():
                        if v:
                            cleaned[k] = datetime.fromisoformat(v)
                    else:
                        cleaned[k] = v
                db.session.add(model_cls(**cleaned))
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": f"Restore failed: {e}"}), 500

    return jsonify({"message": f"Restored from {filename}"})


@blueprint.route("/debug/clear", methods=["POST"])
@superuser_required
def clear_database() -> Response:
    if not _confirm_check():
        return jsonify({"error": "Invalid or missing confirmation code"}), 400

    try:
        _clear_all_tables()
        _ensure_superuser()
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": f"Clear failed: {e}"}), 500

    return jsonify({"message": "All tables cleared. Superuser preserved."})


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

    try:
        _clear_all_tables()
        _seed_data(n_customers, n_months)
        _ensure_superuser()
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": f"Seed failed: {e}"}), 500

    return jsonify({"message": f"Seeded {n_customers} customers × {n_months} months"})


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
    db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 0"))
    for table_name in reversed(TABLE_NAMES):
        db.session.execute(db.text(f"TRUNCATE TABLE {table_name}"))
    Staff.query.filter(Staff.username != "superuser").delete(
        synchronize_session=False
    )
    db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1"))
    db.session.commit()


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
    import math
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


def _seed_data(n_customers: int, n_months: int) -> None:
    import binascii
    import hashlib
    import math
    import secrets as _secrets

    rng = random.Random(42)
    now = datetime.utcnow()

    def _hash_pass(password: str) -> bytes:
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
        pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)
        return salt + binascii.hexlify(pwdhash)

    latest_month = now.month - 1
    latest_year = now.year
    if latest_month < 1:
        latest_month += 12
        latest_year -= 1
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
        {"username": "superuser", "name": "Super Admin", "all": True},
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

    cashier_id = staff_ids.get("cashier1", staff_ids["superuser"])

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

    db.session.commit()
