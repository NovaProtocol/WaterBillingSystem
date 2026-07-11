from __future__ import annotations

import math
import os
import random
import secrets
import shutil as _shutil
import subprocess as _sp
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from apps import db
from apps.models import (
    ApiKey,
    Billing,
    Customer,
    ManagementLog,
    MeterReading,
    NfcTag,
    Staff,
    XenditTransaction,
)
from apps.pricing import compute_water_bill
from apps.services.payment_service import recalc_cumulative_balance, submit_payment
from apps.services.staff_seeder import (
    ensure_prereq_staff,
    delete_non_prereq_staff,
)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

BACKUP_DIR = _PROJECT_ROOT / "db_backups"

TABLE_NAMES = [
    "customers", "meter_readings",
    "billings", "api_keys", "nfc_tags", "management_logs", "app_config",
]


# ── Helpers ────────────────────────────────────────────────────────────

def _clear_all_tables() -> None:
    try:
        db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 0"))
        for table_name in reversed(TABLE_NAMES):
            db.session.execute(db.text(f"TRUNCATE TABLE {table_name}"))
        delete_non_prereq_staff()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1"))


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
    import binascii
    import hashlib

    _report_fn = _report if _report else lambda p, m: None
    _report_fn(2, "Clearing existing staff...")
    print("  > Removing non-prerequisite staff...", flush=True)
    delete_non_prereq_staff()
    db.session.flush()
    print("  > Staff cleared", flush=True)

    rng = random.Random(42)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def _hash_pass(password: str) -> bytes:
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
        pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)
        return salt + binascii.hexlify(pwdhash)

    print("  > Preparing date slots for {} months...".format(n_months), flush=True)
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
    print("  > Creating {} staff accounts with permissions...".format(len(staff_users)), flush=True)
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
    print("  > Staff created: {}".format(", ".join(staff_ids.keys())), flush=True)

    cashier_id = staff_ids.get("cashier1", next(iter(staff_ids.values())))
    _report_fn(4, f"Created {len(staff_users)} staff accounts")

    print("  > Creating API keys for mobile access...", flush=True)
    api_key_map: dict[int, int] = {}
    for sid_name, sid in staff_ids.items():
        if sid_name in ("superuser", "admin", "reader1"):
            raw = "CRDC-" + secrets.token_hex(16).upper()
            ak = ApiKey(key=raw, label=f"{sid_name} token", staff_id=sid, is_active=True)
            db.session.add(ak)
            db.session.flush()
            api_key_map[sid] = ak.id
    print("  > {} API keys created".format(len(api_key_map)), flush=True)

    reader_token_ids = list(api_key_map.values())

    last_print = 0
    next_pct = 1
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
        reading_values: list[float] = []

        for month_idx in range(n_months):
            reading_dt = date_slots[month_idx].replace(
                hour=rng.randint(8, 17), minute=rng.randint(0, 59),
            )
            if month_idx > 0:
                meter_value = round(meter_value + consumptions[month_idx - 1], 1)
            reading_values.append(meter_value)
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
            prev_reading_value = reading_values[month_idx - 1]
            curr_reading_value = reading_values[month_idx]
            consumption = round(curr_reading_value - prev_reading_value, 1)
            reading_id = reading_ids[month_idx]
            water_bill, _ = compute_water_bill(consumption)

            if month_idx == n_months - 1:
                bill = Billing(
                    customer_number=cnum,
                    reading_id=reading_id,
                    previous_reading_value=prev_reading_value,
                    current_reading_value=curr_reading_value,
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
                previous_reading_value=prev_reading_value,
                current_reading_value=curr_reading_value,
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
            pct = 4 + round(93 * (ci + 1) / n_customers, 1)
            _report_fn(pct, f"Seeding customer {ci + 1}/{n_customers}...")
            now_ts = _time.time()
            if pct >= next_pct or now_ts - last_print >= 5:
                print("  > {:>7,}/{:<7,} ({}%) — {:>7,} readings, {:>7,} bills".format(
                    ci + 1, n_customers, pct,
                    (ci + 1) * n_months,
                    (ci + 1) * (n_months - 1),
                ), flush=True)
                next_pct = int(pct) + 1
                last_print = now_ts

    db.session.commit()
    _report_fn(97, "Finalizing...")


# ── Handler functions ──────────────────────────────────────────────────

def handle_backup(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    print("  > Checking for mysqldump...", flush=True)
    if not _shutil.which("mysqldump"):
        raise RuntimeError("mysqldump not found. Install mysql-client (apt install default-mysql-client)")
    print("  > mysqldump found", flush=True)

    report(0, "Starting mysqldump backup...")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "3306")
    db_user = os.environ.get("DB_USERNAME", "root")
    db_pass = os.environ.get("DB_PASS", "")
    db_name = os.environ.get("DB_NAME", "BillServerDB")

    print(f"  > Counting customers...", flush=True)
    customer_count = db.session.query(db.func.count(Customer.id)).scalar() or 0
    print(f"  > Database: {db_name} on {db_host}:{db_port} — {customer_count} customers", flush=True)

    filename = f"backup_{datetime.now(timezone.utc).replace(tzinfo=None):%Y%m%d_%H%M%S}.sql"
    path = BACKUP_DIR / filename
    print(f"  > Output file: {path}", flush=True)

    cmd = [
        "mysqldump",
        "-h", db_host,
        "-P", db_port,
        "-u", db_user,
        f"-p{db_pass}",
        "--ssl=0",
        "--single-transaction",
        "--routines", "--triggers", "--events",
        db_name,
    ]
    report(10, f"Dumping database ({customer_count} customers)...")
    print(f"  > Spawning mysqldump...", flush=True)
    dump_t0 = _time.time()
    with open(path, "w") as f:
        result = _sp.run(cmd, stdout=f, stderr=_sp.PIPE, text=True)
    dump_dur = _time.time() - dump_t0
    if result.returncode != 0:
        err = result.stderr.strip() or f"exit code {result.returncode}"
        print(f"  > FAILED: {err}", flush=True)
        raise RuntimeError(f"Backup failed: {err}")
    file_size = path.stat().st_size
    file_size_str = f"{file_size / 1024 / 1024:.1f} MB" if file_size > 1024 * 1024 else f"{file_size / 1024:.1f} KB"
    total_dur = _time.time() - t0
    print(f"  > mysqldump completed in {dump_dur:.1f}s", flush=True)
    print(f"  > File size: {file_size_str}", flush=True)
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    report(100, f"Backup saved: {filename} ({file_size_str}, {customer_count} customers, {total_dur:.1f}s)")


def handle_restore(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    print("  > Checking for mysql client...", flush=True)
    if not _shutil.which("mysql"):
        raise RuntimeError("mysql not found. Install mysql-client (apt install default-mysql-client)")
    print("  > mysql found", flush=True)

    filename = params.get("filename", "")
    path = BACKUP_DIR / filename
    print(f"  > Backup file: {path}", flush=True)
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".sql"):
        print(f"  > File not found or invalid: {filename}", flush=True)
        raise FileNotFoundError(f"Backup file not found: {filename}")

    file_size = path.stat().st_size
    file_size_str = f"{file_size / 1024 / 1024:.1f} MB" if file_size > 1024 * 1024 else f"{file_size / 1024:.1f} KB"
    print(f"  > File size: {file_size_str}", flush=True)

    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "3306")
    db_user = os.environ.get("DB_USERNAME", "root")
    db_pass = os.environ.get("DB_PASS", "")
    db_name = os.environ.get("DB_NAME", "BillServerDB")

    report(5, f"Restoring {filename} ({file_size_str})...")
    print(f"  > Dropping and recreating database {db_name}...", flush=True)
    cmd = [
        "mysql",
        "-h", db_host,
        "-P", db_port,
        "-u", db_user,
        f"-p{db_pass}",
        "--ssl=0",
        db_name,
    ]
    print(f"  > Feeding SQL dump into mysql...", flush=True)
    restore_t0 = _time.time()
    with open(path) as f:
        result = _sp.run(cmd, stdin=f, stdout=_sp.PIPE, stderr=_sp.PIPE, text=True)
    restore_dur = _time.time() - restore_t0
    if result.returncode != 0:
        err = result.stderr.strip() or f"exit code {result.returncode}"
        print(f"  > FAILED: {err}", flush=True)
        raise RuntimeError(f"Restore failed: {err}")
    print(f"  > Restore completed in {restore_dur:.1f}s", flush=True)
    print(f"  > Ensuring prerequisite staff accounts...", flush=True)

    try:
        ensure_prereq_staff()
        db.session.commit()
        customer_count = db.session.query(db.func.count(Customer.id)).scalar() or 0
        print(f"  > Customers after restore: {customer_count}", flush=True)
    except Exception:
        db.session.rollback()
        print(f"  > Could not count customers (DB was replaced by restore)", flush=True)

    total_dur = _time.time() - t0
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    print(f"  > Restore complete: {filename} ({file_size_str}, {total_dur:.1f}s)", flush=True)


def handle_clear(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    print("  > Counting rows before clear...", flush=True)
    counts_before = {}
    for t in TABLE_NAMES:
        try:
            counts_before[t] = db.session.execute(db.text(f"SELECT COUNT(*) FROM {t}")).scalar()
        except Exception:
            counts_before[t] = 0
    print(f"  > Tables to truncate: {', '.join(TABLE_NAMES)} ({sum(counts_before.values())} total rows)", flush=True)

    report(0, "Clearing tables...")
    _clear_all_tables()
    print(f"  > All {len(TABLE_NAMES)} tables truncated", flush=True)

    report(50, "Recreating system users...")
    ensure_prereq_staff()
    db.session.commit()
    print(f"  > System users recreated (superuser, xendit)", flush=True)

    total_dur = _time.time() - t0
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    report(100, f"Cleared {len(TABLE_NAMES)} tables ({sum(counts_before.values())} rows removed)")


def handle_seed(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    n_customers = int(params.get("customers", 0))
    n_months = int(params.get("months", 0))
    print(f"  > Generating {n_customers} customers × {n_months} months of data", flush=True)
    print(f"  > Total rows to create: ~{n_customers * (n_months + 1)}", flush=True)

    report(0, "Clearing existing data...")
    _clear_all_tables()
    print(f"  > Existing data cleared", flush=True)

    report(2, f"Seeding {n_customers} customers × {n_months} months...")
    _seed_data(n_customers, n_months, report)
    ensure_prereq_staff()
    db.session.commit()

    actual_customers = db.session.query(db.func.count(Customer.id)).scalar() or 0
    actual_readings = db.session.query(db.func.count(MeterReading.id)).scalar() or 0
    actual_bills = db.session.query(db.func.count(Billing.id)).scalar() or 0
    total_dur = _time.time() - t0
    print(f"  > Created {actual_customers} customers, {actual_readings} readings, {actual_bills} bills", flush=True)
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    report(100, f"Seeded {actual_customers} customers × {n_months} months ({actual_readings} readings, {actual_bills} bills, {total_dur:.1f}s)")


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
    t0 = _time.time()
    print("  > Finding customers without a reading this month...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    customers = _get_customers_without_reading_this_month(now)
    total = len(customers)
    print(f"  > Found {total} customers to process", flush=True)
    report(5, f"Found {total} customers to read")
    if not total:
        print("  > All customers already have a reading this month", flush=True)
        report(100, "All customers already have a reading this month.")
        return
    rng = random.Random(now.year * 12 + now.month)
    created = 0
    skipped = 0
    next_log = 10
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
        if i + 1 >= next_log:
            print(f"  > {i + 1}/{total} — {created} created, {skipped} skipped", flush=True)
            next_log += 50
    db.session.commit()
    total_dur = _time.time() - t0
    print(f"  > Done: {created} readings created, {skipped} skipped in {total_dur:.1f}s", flush=True)
    report(100, f"Done. {created} readings created, {skipped} skipped ({total_dur:.1f}s).")


def handle_unread_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    print("  > Finding this month's readings...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    readings = (
        MeterReading.query
        .filter(MeterReading.timestamp >= first_of_month)
        .all()
    )
    total = len(readings)
    print(f"  > Found {total} readings this month", flush=True)
    report(5, f"Found {total} readings")
    removed = 0
    skipped_paid = 0
    next_log = 100
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
        report(pct, f"Unread {i + 1}/{total} ({removed} removed, {skipped_paid} skipped - already paid)")
        if removed >= next_log:
            print(f"  > {removed} removed ({i + 1}/{total}), {skipped_paid} skipped (paid)", flush=True)
            next_log += 100
    db.session.commit()
    total_dur = _time.time() - t0
    print(f"  > Done: {removed} removed, {skipped_paid} skipped (paid) in {total_dur:.1f}s", flush=True)
    report(100, f"Done. {removed} readings removed, {skipped_paid} skipped (paid).")


def handle_pay_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    print("  > Finding unpaid this-month bills...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    unpaid_bills = (
        Billing.query
        .outerjoin(MeterReading, Billing.reading_id == MeterReading.id)
        .filter(MeterReading.timestamp >= first_of_month)
        .filter(Billing.is_paid.is_(False))
        .all()
    )
    total = len(unpaid_bills)
    total_amount = sum(float(b.billed_amount) + float(b.penalty) for b in unpaid_bills)
    print(f"  > Found {total} unpaid bills, total due: PHP {total_amount:,.2f}", flush=True)
    report(5, f"Found {total} unpaid bills")
    paid = 0
    su = Staff.query.filter_by(username="superuser").first()
    su_id = su.id if su else 1
    next_log = 100
    for i, bill in enumerate(unpaid_bills):
        bill.is_paid = True
        bill.paid_amount = round(float(bill.billed_amount) + float(bill.penalty), 2)
        bill.receipt_number = "MONTHLY-" + secrets.token_hex(4).upper()
        bill.cashier_id = su_id
        bill.payment_timestamp = now
        bill.date_paid = now
        paid += 1
        if paid % 100 == 0:
            db.session.commit()
        report(5 + round(90 * (i + 1) / max(total, 1), 1),
               f"Paid {i + 1}/{total}")
        if paid >= next_log:
            print(f"  > Paid {paid}/{total} bills...", flush=True)
            next_log += 100
    db.session.commit()
    total_dur = _time.time() - t0
    print(f"  > Done: {paid} bills paid (PHP {total_amount:,.2f}) in {total_dur:.1f}s", flush=True)
    report(100, f"Done. {paid} bills paid ({total_dur:.1f}s).")


def handle_remove_payment_this_month(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    print("  > Finding paid this-month bills...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    paid_bills = (
        Billing.query
        .outerjoin(MeterReading, Billing.reading_id == MeterReading.id)
        .filter(MeterReading.timestamp >= first_of_month)
        .filter(Billing.is_paid.is_(True))
        .all()
    )
    total = len(paid_bills)
    total_amount = sum(float(b.paid_amount) for b in paid_bills if b.paid_amount)
    print(f"  > Found {total} paid bills (PHP {total_amount:,.2f} total)", flush=True)
    report(5, f"Found {total} paid bills")
    undone = 0
    next_log = 100
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
        if undone >= next_log:
            print(f"  > Reverted {undone}/{total} bills...", flush=True)
            next_log += 100
    db.session.commit()
    print(f"  > Recalculating cumulative balances...", flush=True)
    seen: set[str] = set()
    for bill in paid_bills:
        if bill.customer_number not in seen:
            seen.add(bill.customer_number)
            _recalc_cumulative_balance(bill.customer_number)
    total_dur = _time.time() - t0
    print(f"  > Done: {undone} bills reverted ({len(seen)} customers affected) in {total_dur:.1f}s", flush=True)
    report(100, f"Done. {undone} bills reverted ({len(seen)} customers).")


def handle_xendit_reconcile(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    from apps.models import BackgroundTask
    t0 = _time.time()

    report(0, "Starting Xendit reconciliation...")
    import xendit
    from xendit.apis import PaymentRequestApi

    key = os.environ.get("XENDIT_API_KEY", "")
    if not key or key == "your-xendit-secret-api-key":
        print(f"  > XENDIT_API_KEY not set or is placeholder — skipping", flush=True)
        report(100, "Reconciliation skipped: Xendit not configured")
        return

    xendit.set_api_key(key)
    print(f"  > Connected to Xendit API", flush=True)

    threshold = datetime.now(timezone.utc).replace(tzinfo=None).timestamp() - 300
    print(f"  > Querying pending transactions older than 5 minutes...", flush=True)
    pending = (
        XenditTransaction.query
        .filter_by(status="PENDING")
        .all()
    )
    pending = [t for t in pending if t.date_created and t.date_created.timestamp() < threshold]

    if not pending:
        print(f"  > No pending transactions to reconcile — queueing next run in 5m", flush=True)
        report(100, "No pending transactions to reconcile")
        _enqueue_next_reconcile()
        return

    total = len(pending)
    print(f"  > Found {total} pending transactions to reconcile", flush=True)
    report(5, f"Found {total} pending transactions")

    client = xendit.ApiClient()
    api_instance = PaymentRequestApi(client)

    succeeded = 0
    failed = 0
    expired = 0
    reversed_txns = 0
    errored = 0

    for i, txn in enumerate(pending):
        report(5 + round(85 * (i + 1) / total, 1), f"Reconciling {i+1}/{total}: {txn.xendit_pr_id[:16]}... ({txn.customer_number}, PHP {txn.amount})")
        print(f"  > [{i+1}/{total}] {txn.xendit_pr_id[:20]}... ({txn.customer_number}, PHP {txn.amount})", flush=True)
        try:
            response = api_instance.get_payment_request_by_id(txn.xendit_pr_id)
            status = getattr(response, "status", None)
            if status and str(status) in ("SUCCEEDED", "PAID", "SETTLED"):
                print(f"    → Xendit status: {status} — processing payment...", flush=True)
                payment_id = getattr(response, "id", "")
                if payment_id:
                    txn.xendit_payment_id = str(payment_id)
                if _process_xendit_payment(txn):
                    succeeded += 1
                    print(f"    → Payment processed successfully", flush=True)
                else:
                    errored += 1
                    print(f"    → Payment processing failed", flush=True)
            elif status and str(status) in ("FAILED", "EXPIRED"):
                print(f"    → Xendit status: {status} — marking as failed", flush=True)
                txn.status = "FAILED"
                txn.error_message = f"Payment failed (reconciled: {status})"
                db.session.commit()
                failed += 1
            elif status and str(status) == "REVERSED":
                print(f"    → Xendit status: REVERSED — reversing payment...", flush=True)
                _reverse_xendit_payment(txn)
                reversed_txns += 1
                print(f"    → Payment reversed", flush=True)
            else:
                print(f"    → Unknown Xendit status: {status} — skipping", flush=True)
        except Exception as e:
            errored += 1
            print(f"    → ERROR: {e}", flush=True)

    _enqueue_next_reconcile()
    total_dur = _time.time() - t0
    summary = f"Reconciled {total} txn ({succeeded} ok, {failed} failed, {reversed_txns} reversed, {errored} errors) in {total_dur:.1f}s"
    print(f"  > {summary}", flush=True)
    print(f"  > Next reconciliation queued in 5 minutes", flush=True)
    report(100, summary)


def _process_xendit_payment(txn: XenditTransaction) -> bool:
    if txn.status != "PENDING":
        return False

    customer = Customer.query.filter_by(customer_number=txn.customer_number).first()
    if not customer:
        txn.status = "FAILED"
        txn.error_message = "Customer not found"
        db.session.commit()
        return False

    staff = Staff.query.filter_by(username="xendit").first()
    if not staff:
        txn.status = "FAILED"
        txn.error_message = "Xendit system user not found"
        db.session.commit()
        return False

    try:
        amount = float(txn.amount)
        result, error, status = submit_payment(txn.customer_number, amount, staff.id)
        if error:
            txn.status = "FAILED"
            txn.error_message = error
            db.session.commit()
            return False

        txn.status = "PAID"
        txn.receipt_number = result.get("receipt_number")
        txn.billing_receipt = result.get("receipt_number")
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        txn = db.session.merge(txn)
        txn.status = "FAILED"
        txn.error_message = str(e)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False


def _reverse_xendit_payment(txn: XenditTransaction) -> bool:
    if txn.status != "PAID":
        return False

    billing_receipt = txn.billing_receipt
    if not billing_receipt:
        txn.status = "REVERSED"
        txn.error_message = "No billing receipt to reverse"
        db.session.commit()
        return True

    bills = Billing.query.filter_by(receipt_number=billing_receipt).with_for_update().all()
    for b in bills:
        b.is_paid = False
        b.paid_amount = 0
        b.receipt_number = None
        b.cashier_id = None
        b.payment_timestamp = None
        b.date_paid = None
        b.carryover_offset = 0

    recalc_cumulative_balance(txn.customer_number)

    txn.status = "REVERSED"
    txn.reversed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return True


def _enqueue_next_reconcile() -> None:
    from apps.models import BackgroundTask
    BackgroundTask.enqueue_unique(
        task_type="xendit_reconcile",
        title="Xendit Reconciliation",
        scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
    )


HANDLERS: dict[str, Callable[[dict[str, Any], Callable[[float, str], None]], None]] = {
    "backup": handle_backup,
    "restore": handle_restore,
    "clear": handle_clear,
    "seed": handle_seed,
    "read-this-month": handle_read_this_month,
    "unread-this-month": handle_unread_this_month,
    "pay-this-month": handle_pay_this_month,
    "remove-payment-this-month": handle_remove_payment_this_month,
    "xendit_reconcile": handle_xendit_reconcile,
}
