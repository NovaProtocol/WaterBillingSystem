from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker")

import math
import os
import random
import secrets
import shutil as _shutil
import time as _time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from db_async import session_factory, sync_session
from models import (
    ApiKey,
    Billing,
    Customer,
    MeterReading,
    Staff,
    XenditTransaction,
)
from pricing import compute_water_bill
from services.payment_service import recalc_cumulative_balance, submit_payment
from services.staff_seeder import (
    delete_non_prereq_staff,
    ensure_prereq_staff,
)
from sqlalchemy import func, select, text

WORKER_JOB_CONCURRENCY = int(os.environ.get("WORKER_JOB_CONCURRENCY", "8"))

BACKUP_DIR = Path("/app/db_backups")

TABLE_NAMES = [
    "customers",
    "meter_readings",
    "billings",
    "api_keys",
    "nfc_tags",
    "management_logs",
    "app_config",
]


# ── Helpers ────────────────────────────────────────────────────────────


async def _clear_all_tables(s) -> None:
    try:
        await s.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table_name in reversed(TABLE_NAMES):
            await s.execute(text(f"TRUNCATE TABLE {table_name}"))
        await s.commit()
    except Exception as e:
        logger.error(f"Error: {e}")
        await s.rollback()
        raise
    finally:
        await s.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


async def _recalc_cumulative_balance(s, customer_number: int) -> None:
    total = (
        await s.execute(
            select(func.sum(Billing.carryover_offset)).where(
                Billing.customer_number == customer_number
            )
        )
    ).scalar() or 0
    customer = (
        await s.execute(select(Customer).where(Customer.customer_number == customer_number))
    ).scalar_one_or_none()
    if customer:
        customer.cumulative_balance = round(float(total), 2)


async def _recalc_total_due(s, customer_number: int) -> None:
    total = 0.0
    for bill in (
        (
            await s.execute(
                select(Billing).where(
                    Billing.customer_number == customer_number,
                    Billing.is_paid.is_(False),
                )
            )
        )
        .scalars()
        .all()
    ):
        bill_due = (
            float(bill.billed_amount or 0) + float(bill.penalty or 0) - float(bill.paid_amount or 0)
        )
        total += max(0, bill_due)
    balance = float(
        (
            await s.execute(
                select(func.sum(Billing.carryover_offset)).where(
                    Billing.customer_number == customer_number
                )
            )
        ).scalar()
        or 0
    )
    customer = (
        await s.execute(select(Customer).where(Customer.customer_number == customer_number))
    ).scalar_one_or_none()
    if customer:
        customer.total_due = max(0, round(total - balance, 2))


def _recalc_total_due_sync(ss, customer_number: int) -> None:
    total = 0.0
    for bill in (
        ss.query(Billing)
        .filter_by(
            customer_number=customer_number,
            is_paid=False,
        )
        .all()
    ):
        bill_due = (
            float(bill.billed_amount or 0) + float(bill.penalty or 0) - float(bill.paid_amount or 0)
        )
        total += max(0, bill_due)
    balance = float(
        ss.query(func.sum(Billing.carryover_offset))
        .filter_by(customer_number=customer_number)
        .scalar()
        or 0
    )
    customer = ss.query(Customer).filter_by(customer_number=customer_number).first()
    if customer:
        customer.total_due = max(0, round(total - balance, 2))


# ── Seed data ──────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Juan",
    "Maria",
    "Jose",
    "Ana",
    "Pedro",
    "Rosa",
    "Antonio",
    "Luz",
    "Francisco",
    "Dolores",
    "Manuel",
    "Carmen",
    "Ramon",
    "Teresa",
    "Eduardo",
    "Gloria",
    "Emilio",
    "Feliza",
    "Ricardo",
    "Elena",
    "Alfredo",
    "Consuelo",
    "Benito",
    "Corazon",
    "Arturo",
    "Aurora",
    "Carlos",
    "Natividad",
    "Diego",
    "Imelda",
    "Felipe",
    "Ligaya",
    "Miguel",
    "Perlita",
    "Roberto",
    "Remedios",
    "Vicente",
    "Salud",
    "Andres",
    "Trinidad",
    "Domingo",
    "Leonila",
    "Esteban",
    "Milagros",
    "Fernando",
    "Beatriz",
    "Guillermo",
    "Ester",
    "Hilario",
    "Concepcion",
    "Jaime",
    "Angelita",
    "Lorenzo",
    "Fe",
    "Nestor",
    "Purita",
    "Orlando",
    "Zenaida",
    "Rolando",
    "Natividad",
]
LAST_NAMES = [
    "dela Cruz",
    "Garcia",
    "Reyes",
    "Ramos",
    "Mendoza",
    "Santos",
    "Flores",
    "Gonzales",
    "Bautista",
    "Villanueva",
    "Fernandez",
    "Rivera",
    "Aquino",
    "Castro",
    "Lopez",
    "Torres",
    "Domingo",
    "Martinez",
    "Gutierrez",
    "Rosario",
    "Salvador",
    "Navarro",
    "Padilla",
    "Marquez",
    "Estrada",
    "Velasco",
    "Pascual",
    "Soriano",
    "Dizon",
    "Manuel",
    "De Leon",
    "Enriquez",
    "Tolentino",
    "Santiago",
    "Luna",
    "Mercado",
    "Agustin",
    "Hernandez",
    "Alvarez",
    "Pineda",
    "Cabrera",
    "Cruz",
    "Alcantara",
    "Magbanua",
    "Macaraeg",
    "Bacani",
    "Dela Peña",
    "Capili",
    "Aguilar",
    "Jacinto",
    "Laxamana",
]
PHASE_DATA = (
    [
        {"phase": "Phase L-1 (St. Jude Village)", "block": f"Block {i}", "street": s}
        for s in [
            "St. Peregrine St",
            "St. Peter Lane",
            "St. Jude Ave",
            "San Lorenzo Ruiz St",
        ]
        for i in range(1, 15)
    ]
    + [
        {"phase": "Phase L-2A (St. Jude Village)", "block": f"Block {i}", "street": s}
        for s in [
            "St. Paul St",
            "St. John St",
            "St. Matthew St",
            "Immaculate Conception Drive",
        ]
        for i in range(1, 15)
    ]
    + [
        {"phase": "Phase L-2C (St. Jude East)", "block": f"Block {i}", "street": s}
        for s in [
            "St. Thomas St",
            "St. Luke St",
            "St. Mark St",
            "San Pedro Calungsod St",
        ]
        for i in range(1, 35)
    ]
    + [
        {"phase": "Phase L-3D (St. Jude East)", "block": f"Block {i}", "street": s}
        for s in ["St. Joseph St", "St. Mary St", "St. Anne St", "St. Therese St"]
        for i in range(1, 25)
    ]
    + [
        {"phase": "Phase P-1 (Pagbilao)", "block": f"Block {i}", "street": s}
        for s in ["San Vicente Ferrer St", "San Isidro Labrador St", "San Roque St"]
        for i in range(1, 10)
    ]
    + [
        {"phase": "Phase S-1 (Sariaya)", "block": f"Block {i}", "street": s}
        for s in ["San Francisco de Asis St", "Santa Clara St", "Santo Domingo St"]
        for i in range(1, 8)
    ]
    + [
        {"phase": "Phase C-1 (Candelaria)", "block": f"Block {i}", "street": s}
        for s in ["San Miguel St", "San Gabriel St", "San Rafael St"]
        for i in range(1, 5)
    ]
)
BASE_LAT = 13.9360069
BASE_LON = 121.6314674


def _coord_offset(rng: random.Random) -> tuple[float, float]:
    r = rng.random() * 1500
    theta = rng.random() * 2 * math.pi
    dlat = r / 111320
    dlon = r / (111320 * math.cos(math.radians(BASE_LAT)))
    return round(BASE_LAT + dlat * math.cos(theta), 7), round(BASE_LON + dlon * math.sin(theta), 7)


def _seasonal_factor(month: int, rng: random.Random) -> float:
    if month in (3, 4, 5):
        return rng.uniform(1.10, 1.30)
    elif month in (6, 7, 8, 9, 10):
        return rng.uniform(0.90, 1.05)
    else:
        return rng.uniform(0.82, 0.98)


def _generate_consumption(count: int, rng: random.Random) -> list[float]:
    base = rng.uniform(12, 40)
    yearly_growth = rng.uniform(1.04, 1.10)
    values: list[float] = []
    for m in range(count):
        year = m // 12
        month_num = (m % 12) + 1
        grown = base * (yearly_growth**year)
        seasonal = _seasonal_factor(month_num, rng)
        noise = rng.uniform(0.92, 1.08)
        consumption = max(5.0, round(grown * seasonal * noise, 1))
        values.append(consumption)
    return values


async def _seed_data(
    n_customers: int,
    n_months: int,
    cashiers: int,
    readers: int,
    read_current: bool,
    pay_last: str,
    randomize_months: bool,
    allow_deactivation: bool,
    _report: Callable[[float, str], None] | None = None,
    s=None,
) -> None:
    import binascii
    import hashlib

    _report_fn = _report if _report else lambda p, m: None

    _report_fn(2, "Ensuring prerequisite staff...")
    print("  > Ensuring prerequisite staff (superuser, xendit)...", flush=True)
    ss = sync_session()
    try:
        await asyncio.to_thread(ensure_prereq_staff, ss)
    finally:
        ss.close()
    print("  > Prerequisite staff ready", flush=True)

    rng = random.Random(42)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def _hash_pass(password: str) -> bytes:
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
        pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)
        return salt + binascii.hexlify(pwdhash)

    current_months = now.year * 12 + now.month - 1
    print(
        f"  > Preparing {n_months} date slots on the 15th, backwards from current month...",
        flush=True,
    )
    date_slots: list[datetime] = []
    for i in range(n_months):
        month_offset = n_months - 1 - i
        target_months = current_months - month_offset
        y = target_months // 12
        m = target_months % 12 + 1
        date_slots.append(datetime(y, m, 15))

    cashier_staff_ids: list[int] = []
    print(f"  > Creating {cashiers} cashier accounts...", flush=True)
    for i in range(cashiers):
        uname = f"cashier{i + 1}"
        staff = Staff(
            username=uname,
            name=f"Cashier {i + 1}",
            password=_hash_pass(uname),
            can_accept_payment=True,
            is_active=True,
            date_created=now,
            last_modified=now,
        )
        s.add(staff)
        await s.flush()
        cashier_staff_ids.append(staff.id)
    print(f"  > Cashier accounts created: {cashiers}", flush=True)

    reader_staff_ids: list[int] = []
    print(f"  > Creating {readers} reader accounts...", flush=True)
    for i in range(readers):
        uname = f"reader{i + 1}"
        staff = Staff(
            username=uname,
            name=f"Reader {i + 1}",
            password=_hash_pass(uname),
            can_read_meters=True,
            is_active=True,
            date_created=now,
            last_modified=now,
        )
        s.add(staff)
        await s.flush()
        reader_staff_ids.append(staff.id)
    print(f"  > Reader accounts created: {readers}", flush=True)

    _report_fn(4, f"Created {cashiers + readers} additional staff (+ superuser, xendit)")

    print("  > Creating API keys for reader mobile access...", flush=True)
    reader_token_ids: list[int] = []
    for sid in reader_staff_ids:
        raw = "CRDC-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=raw, label=f"reader token {sid}", staff_id=sid, is_active=True)
        s.add(ak)
        await s.flush()
        reader_token_ids.append(ak.id)
    su_staff = (
        await s.execute(select(Staff).where(Staff.username == "superuser"))
    ).scalar_one_or_none()
    if su_staff:
        raw = "CRDC-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=raw, label="superuser token", staff_id=su_staff.id, is_active=True)
        s.add(ak)
        await s.flush()
        reader_token_ids.append(ak.id)
    if not reader_token_ids:
        raise RuntimeError("No reader tokens available (no readers and no superuser found)")
    print(f"  > {len(reader_token_ids)} token IDs available for readings", flush=True)

    if cashier_staff_ids:
        cashier_ids = cashier_staff_ids
    elif su_staff:
        cashier_ids = [su_staff.id]
    else:
        raise RuntimeError("No cashier available (no cashiers and no superuser found)")
    last_print = 0
    next_pct = 1

    for ci in range(n_customers):
        cnum = ci + 1
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        pd = rng.choice(PHASE_DATA)
        coord = _coord_offset(rng)

        if randomize_months:
            actual_months = rng.randint(2, n_months)
        else:
            actual_months = n_months

        start_idx = n_months - actual_months
        sub_day = rng.randint(1, 28) if randomize_months else 15
        subscription_date = date_slots[start_idx].replace(
            day=sub_day,
            hour=rng.randint(8, 17),
            minute=rng.randint(0, 59),
        )

        cust = Customer(
            customer_number=cnum,
            name=f"{first} {last}",
            address=f"{rng.randint(1, 50)} {pd['street']}",
            contact_number="09" + "".join(rng.choice("0123456789") for _ in range(9)),
            email=f"c{ci + 1}{first.lower()}@gmail.com",
            x_coordinate=coord[0],
            y_coordinate=coord[1],
            phase=pd["phase"],
            block=pd["block"],
            cumulative_balance=0.00,
            max_meter_value=99999.00,
            is_active=True,
            date_created=subscription_date,
            date_modified=now,
        )
        s.add(cust)
        await s.flush()

        n_readings = actual_months if read_current else max(1, actual_months - 1)
        n_transitions = max(0, n_readings - 1)

        cust_rng = random.Random(ci * 1000 + 42)
        consumptions = (
            _generate_consumption(max(n_transitions, 1), cust_rng) if n_transitions > 0 else []
        )

        meter_value = 0.00 if rng.random() >= 0.2 else round(rng.uniform(100, 500), 1)

        reading_ids: list[int] = []
        reading_values: list[float] = []
        reading_dates: list[datetime] = []

        for ri in range(n_readings):
            if ri == 0:
                reading_dt = subscription_date
            else:
                slot_idx = start_idx + ri
                reading_dt = date_slots[slot_idx].replace(
                    hour=rng.randint(8, 17),
                    minute=rng.randint(0, 59),
                )

            if ri > 0 and ri - 1 < len(consumptions):
                meter_value = round(meter_value + consumptions[ri - 1], 1)

            reading_values.append(meter_value)
            reading_dates.append(reading_dt)

            mr = MeterReading(
                customer_number=cnum,
                reading_value=meter_value,
                token_id=rng.choice(reader_token_ids),
                timestamp=reading_dt,
                date_created=now,
                date_modified=now,
            )
            s.add(mr)
            await s.flush()
            reading_ids.append(mr.id)

        cum_balance = 0.0
        last_unpaid_total = 0.0
        should_pay_last = True

        for bi in range(1, n_readings):
            prev_reading_value = reading_values[bi - 1]
            curr_reading_value = reading_values[bi]
            consumption = round(curr_reading_value - prev_reading_value, 1)
            reading_id = reading_ids[bi]
            reading_date = reading_dates[bi]
            water_bill, _ = compute_water_bill(consumption)

            is_last = bi == n_readings - 1

            if is_last:
                if pay_last == "yes":
                    should_pay_last = True
                elif pay_last == "no":
                    should_pay_last = False
                else:
                    should_pay_last = rng.random() < 0.5
            else:
                should_pay_last = True

            if should_pay_last:
                timing_roll = rng.random()
                if timing_roll < 0.80:
                    delay_days = rng.randint(0, 7)
                    penalty = 0.0
                elif timing_roll < 0.95:
                    delay_days = rng.randint(8, 28)
                    penalty = 15.0
                else:
                    delay_days = rng.randint(29, 60)
                    penalty = 15.0

                pay_dt = reading_date + timedelta(days=delay_days)
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
                    cashier_id=rng.choice(cashier_ids),
                    payment_timestamp=pay_dt,
                    date_paid=pay_dt,
                    date_created=now,
                    date_modified=now,
                )
            else:
                penalty = 15.0
                bill = Billing(
                    customer_number=cnum,
                    reading_id=reading_id,
                    previous_reading_value=prev_reading_value,
                    current_reading_value=curr_reading_value,
                    consumption=consumption,
                    billed_amount=water_bill,
                    penalty=penalty,
                    paid_amount=0,
                    carryover_offset=0,
                    is_paid=False,
                    date_created=now,
                    date_modified=now,
                )
                last_unpaid_total = round(water_bill + penalty, 2)
            s.add(bill)

        cust.cumulative_balance = round(cum_balance, 2)
        if not should_pay_last and last_unpaid_total > 0:
            cust.total_due = max(0, round(last_unpaid_total - cum_balance, 2))
        else:
            cust.total_due = 0.0

        if (ci + 1) % 10 == 0:
            await s.commit()
            pct = 4 + round(93 * (ci + 1) / n_customers, 1)
            _report_fn(pct, f"Seeding customer {ci + 1}/{n_customers}...")
            now_ts = _time.time()
            if pct >= next_pct or now_ts - last_print >= 5:
                print(
                    f"  > {ci + 1:>7,}/{n_customers:<7,} ({pct}%) — {(ci + 1) * n_readings:>7,} readings, {(ci + 1) * max(0, n_readings - 1):>7,} bills",
                    flush=True,
                )
                next_pct = int(pct) + 1
                last_print = now_ts

    await s.commit()
    _report_fn(97, "Finalizing...")


# ── Handler functions ──────────────────────────────────────────────────


async def handle_backup(params, report):
    t0 = _time.time()
    print("  > Checking for mysqldump...", flush=True)
    if not _shutil.which("mysqldump"):
        raise RuntimeError(
            "mysqldump not found. Install mysql-client (apt install default-mysql-client)"
        )
    print("  > mysqldump found", flush=True)

    report(0, "Starting mysqldump backup...")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    db_host = os.environ["DB_HOST"]
    db_port = os.environ["DB_PORT"]
    db_user = os.environ["DB_USERNAME"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]

    async with session_factory()() as s:
        print("  > Counting customers...", flush=True)
        customer_count = (await s.execute(select(func.count(Customer.id)))).scalar() or 0
        print(
            f"  > Database: {db_name} on {db_host}:{db_port} — {customer_count} customers",
            flush=True,
        )

        filename = f"backup_{datetime.now(timezone.utc).replace(tzinfo=None):%Y%m%d_%H%M%S}.sql"
        path = BACKUP_DIR / filename
        print(f"  > Output file: {path}", flush=True)

        cmd = [
            "mysqldump",
            "-h",
            db_host,
            "-P",
            db_port,
            "-u",
            db_user,
            f"-p{db_pass}",
            "--ssl=0",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--events",
            f"--ignore-table={db_name}.background_tasks",
            db_name,
        ]
        report(10, f"Dumping database ({customer_count} customers)...")
        print("  > Spawning mysqldump...", flush=True)
        dump_t0 = _time.time()
        with open(path, "wb") as f:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=f, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
        dump_dur = _time.time() - dump_t0
        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace").strip() or f"exit code {proc.returncode}"
            print(f"  > FAILED: {err}", flush=True)
            raise RuntimeError(f"Backup failed: {err}")
        file_size = path.stat().st_size
        file_size_str = (
            f"{file_size / 1024 / 1024:.1f} MB"
            if file_size > 1024 * 1024
            else f"{file_size / 1024:.1f} KB"
        )
        total_dur = _time.time() - t0
        print(f"  > mysqldump completed in {dump_dur:.1f}s", flush=True)
        print(f"  > File size: {file_size_str}", flush=True)
        print(f"  > Total time: {total_dur:.1f}s", flush=True)
        report(
            100,
            f"Backup saved: {filename} ({file_size_str}, {customer_count} customers, {total_dur:.1f}s)",
        )


async def handle_restore(params, report):
    t0 = _time.time()
    print("  > Checking for mysql client...", flush=True)
    if not _shutil.which("mysql"):
        raise RuntimeError(
            "mysql not found. Install mysql-client (apt install default-mysql-client)"
        )
    print("  > mysql found", flush=True)

    filename = params.get("filename", "")
    path = BACKUP_DIR / filename
    print(f"  > Backup file: {path}", flush=True)
    if not path.exists() or not path.name.startswith("backup_") or not path.name.endswith(".sql"):
        print(f"  > File not found or invalid: {filename}", flush=True)
        raise FileNotFoundError(f"Backup file not found: {filename}")

    file_size = path.stat().st_size
    file_size_str = (
        f"{file_size / 1024 / 1024:.1f} MB"
        if file_size > 1024 * 1024
        else f"{file_size / 1024:.1f} KB"
    )
    print(f"  > File size: {file_size_str}", flush=True)

    db_host = os.environ["DB_HOST"]
    db_port = os.environ["DB_PORT"]
    db_user = os.environ["DB_USERNAME"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]

    report(5, f"Restoring {filename} ({file_size_str})...")
    print(f"  > Dropping and recreating database {db_name}...", flush=True)
    cmd = [
        "mysql",
        "-h",
        db_host,
        "-P",
        db_port,
        "-u",
        db_user,
        f"-p{db_pass}",
        "--ssl=0",
        db_name,
    ]
    print("  > Feeding SQL dump into mysql...", flush=True)
    restore_t0 = _time.time()
    with open(path, "rb") as f:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=f,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
    restore_dur = _time.time() - restore_t0
    if proc.returncode != 0:
        err = (stderr or b"").decode(errors="replace").strip() or f"exit code {proc.returncode}"
        print(f"  > FAILED: {err}", flush=True)
        raise RuntimeError(f"Restore failed: {err}")
    print(f"  > Restore completed in {restore_dur:.1f}s", flush=True)
    print("  > Ensuring prerequisite staff accounts...", flush=True)

    async with session_factory()() as s:
        try:
            ss = sync_session()
            try:
                await asyncio.to_thread(ensure_prereq_staff, ss)
            finally:
                ss.close()
            await s.commit()
            customer_count = (await s.execute(select(func.count(Customer.id)))).scalar() or 0
            print(f"  > Customers after restore: {customer_count}", flush=True)
        except Exception as e:
            logger.error(f"Error: {e}")
            await s.rollback()
            print(
                "  > Could not count customers (DB was replaced by restore)",
                flush=True,
            )

    total_dur = _time.time() - t0
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    print(
        f"  > Restore complete: {filename} ({file_size_str}, {total_dur:.1f}s)",
        flush=True,
    )


async def handle_clear(params, report) -> None:
    t0 = _time.time()
    print("  > Counting rows before clear...", flush=True)
    async with session_factory()() as s:
        counts_before = {}
        for t in TABLE_NAMES:
            try:
                counts_before[t] = (await s.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
            except Exception as e:
                logger.error(f"Error: {e}")
                counts_before[t] = 0
        print(
            f"  > Tables to truncate: {', '.join(TABLE_NAMES)} ({sum(counts_before.values())} total rows)",
            flush=True,
        )
        report(0, "Clearing tables...")
        await _clear_all_tables(s)
        print(f"  > All {len(TABLE_NAMES)} tables truncated", flush=True)
        report(50, "Recreating system users...")
        await s.commit()
    ss = sync_session()
    try:
        await asyncio.to_thread(ensure_prereq_staff, ss)
        await asyncio.to_thread(delete_non_prereq_staff, ss)
        ss.commit()
    finally:
        ss.close()
    total_dur = _time.time() - t0
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    report(
        100,
        f"Cleared {len(TABLE_NAMES)} tables ({sum(counts_before.values())} rows removed)",
    )


async def handle_seed(params: dict[str, Any], report: Callable[[float, str], None]) -> None:
    t0 = _time.time()
    n_customers = int(params.get("customers", 0))
    n_months = int(params.get("months", 24))
    cashiers = int(params.get("cashiers", 2))
    readers = int(params.get("readers", 2))
    read_current = params.get("read_current", "no") == "yes"
    pay_last = params.get("pay_last", "random")
    randomize_months = params.get("randomize_months", "yes") == "yes"
    allow_deactivation = params.get("allow_deactivation", "no") == "yes"
    print(f"  > Generating {n_customers} customers, max {n_months} months", flush=True)
    print(
        f"  > cashiers={cashiers}, readers={readers}, read_current={read_current}, pay_last={pay_last}, randomize_months={randomize_months}",
        flush=True,
    )
    print(f"  > Total rows to create: ~{n_customers * (n_months + 1)}", flush=True)

    async with session_factory()() as s:
        report(0, "Clearing existing data...")
        await _clear_all_tables(s)
        print("  > Existing data cleared", flush=True)

        report(2, f"Seeding {n_customers} customers × {n_months} months...")
        await _seed_data(
            n_customers,
            n_months,
            cashiers,
            readers,
            read_current,
            pay_last,
            randomize_months,
            allow_deactivation,
            report,
            s,
        )

        actual_customers = (await s.execute(select(func.count(Customer.id)))).scalar() or 0
        actual_readings = (await s.execute(select(func.count(MeterReading.id)))).scalar() or 0
        actual_bills = (await s.execute(select(func.count(Billing.id)))).scalar() or 0

    total_dur = _time.time() - t0
    print(
        f"  > Created {actual_customers} customers, {actual_readings} readings, {actual_bills} bills",
        flush=True,
    )
    print(f"  > Total time: {total_dur:.1f}s", flush=True)
    report(
        100,
        f"Seeded {actual_customers} customers × {n_months} months ({actual_readings} readings, {actual_bills} bills, {total_dur:.1f}s)",
    )


async def _get_customers_without_reading_this_month(s, now: datetime) -> list[int]:
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    subq = select(MeterReading.customer_number).where(MeterReading.timestamp >= first_of_month)
    customers = (
        (
            await s.execute(
                select(Customer.customer_number).where(
                    Customer.is_active.is_(True), ~Customer.customer_number.in_(subq)
                )
            )
        )
        .scalars()
        .all()
    )
    return list(customers)


async def _process_one_read(
    sem: asyncio.Semaphore, rng: random.Random, cnum: int, now: datetime
) -> tuple[int, int]:
    # returns (created_delta, skipped_delta) for this customer
    async with sem, session_factory()() as s:
        prev = (
            await s.execute(
                select(MeterReading)
                .where(MeterReading.customer_number == cnum)
                .order_by(MeterReading.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not prev:
            return (0, 1)
        consumption = max(
            5.0,
            round(
                abs(rng.gauss(20, 10))
                * (
                    1.1
                    if now.month in (3, 4, 5)
                    else 0.95
                    if now.month in (6, 7, 8, 9, 10)
                    else 0.90
                )
                * rng.uniform(0.92, 1.08),
                1,
            ),
        )
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
        s.add(mr)
        await s.flush()
        water_bill, _ = compute_water_bill(consumption)
        s.add(
            Billing(
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
        )
        await s.commit()
        return (1, 0)


async def handle_read_this_month(
    params: dict[str, Any], report: Callable[[float, str], None]
) -> None:
    t0 = _time.time()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    print("  > Finding customers without a reading this month...", flush=True)
    async with session_factory()() as s:
        customers = await _get_customers_without_reading_this_month(s, now)
    total = len(customers)
    print(f"  > Found {total} customers to process", flush=True)
    report(5, f"Found {total} customers to read")
    if not total:
        report(100, "All customers already have a reading this month.")
        return
    rng = random.Random(now.year * 12 + now.month)
    sem = asyncio.Semaphore(WORKER_JOB_CONCURRENCY)
    created = 0
    skipped = 0
    next_log = 10
    done = 0
    # bounded batches so report() stays meaningful and memory is bounded
    for batch_start in range(0, total, 64):
        batch = customers[batch_start : batch_start + 64]
        results = await asyncio.gather(*(_process_one_read(sem, rng, cnum, now) for cnum in batch))
        for dc, dsk in results:
            created += dc
            skipped += dsk
            done += 1
            if done >= next_log:
                print(
                    f"  > {done}/{total} — {created} created, {skipped} skipped",
                    flush=True,
                )
                next_log += 50
            report(
                5 + round(90 * min(done, total) / max(total, 1), 1),
                f"Read {done}/{total} ({created} created, {skipped} skipped)",
            )
    total_dur = _time.time() - t0
    print(
        f"  > Done: {created} readings created, {skipped} skipped in {total_dur:.1f}s",
        flush=True,
    )
    report(100, f"Done. {created} readings created, {skipped} skipped ({total_dur:.1f}s).")


async def _process_one_unread(sem: asyncio.Semaphore, reading_id: int) -> tuple[int, int]:
    # returns (removed_delta, skipped_paid_delta) for this reading
    async with sem, session_factory()() as s:
        bill = (
            await s.execute(select(Billing).where(Billing.reading_id == reading_id))
        ).scalar_one_or_none()
        if bill and bill.is_paid:
            return (0, 1)
        if bill:
            await s.delete(bill)
        reading = (
            await s.execute(select(MeterReading).where(MeterReading.id == reading_id))
        ).scalar_one_or_none()
        if reading:
            await s.delete(reading)
        await s.commit()
        return (1, 0)


async def handle_unread_this_month(
    params: dict[str, Any], report: Callable[[float, str], None]
) -> None:
    t0 = _time.time()
    print("  > Finding this month's readings...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with session_factory()() as s:
        reading_ids = (
            (
                await s.execute(
                    select(MeterReading.id).where(MeterReading.timestamp >= first_of_month)
                )
            )
            .scalars()
            .all()
        )
    total = len(reading_ids)
    print(f"  > Found {total} readings this month", flush=True)
    report(5, f"Found {total} readings")
    sem = asyncio.Semaphore(WORKER_JOB_CONCURRENCY)
    removed = 0
    skipped_paid = 0
    next_log = 100
    done = 0
    for batch_start in range(0, total, 64):
        batch = reading_ids[batch_start : batch_start + 64]
        results = await asyncio.gather(*(_process_one_unread(sem, rid) for rid in batch))
        for drem, dskip in results:
            removed += drem
            skipped_paid += dskip
            done += 1
            report(
                5 + round(90 * done / max(total, 1), 1),
                f"Unread {done}/{total} ({removed} removed, {skipped_paid} skipped - already paid)",
            )
            if removed >= next_log:
                print(
                    f"  > {removed} removed ({done}/{total}), {skipped_paid} skipped (paid)",
                    flush=True,
                )
                next_log += 100
    total_dur = _time.time() - t0
    print(
        f"  > Done: {removed} removed, {skipped_paid} skipped (paid) in {total_dur:.1f}s",
        flush=True,
    )
    report(100, f"Done. {removed} readings removed, {skipped_paid} skipped (paid).")


async def _process_one_pay(
    sem: asyncio.Semaphore, bill_id: int, su_id: int, now: datetime
) -> tuple[int, int]:
    # returns (paid_delta, 0) for this bill
    async with sem, session_factory()() as s:
        bill = (await s.execute(select(Billing).where(Billing.id == bill_id))).scalar_one_or_none()
        if not bill:
            return (0, 0)
        bill.is_paid = True
        bill.paid_amount = round(float(bill.billed_amount) + float(bill.penalty), 2)
        bill.receipt_number = "MONTHLY-" + secrets.token_hex(4).upper()
        bill.cashier_id = su_id
        bill.payment_timestamp = now
        bill.date_paid = now
        await s.commit()
        return (1, 0)


async def handle_pay_this_month(
    params: dict[str, Any], report: Callable[[float, str], None]
) -> None:
    t0 = _time.time()
    print("  > Finding unpaid this-month bills...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with session_factory()() as s:
        unpaid_bills = (
            (
                await s.execute(
                    select(Billing)
                    .join(MeterReading, Billing.reading_id == MeterReading.id)
                    .where(
                        MeterReading.timestamp >= first_of_month,
                        Billing.is_paid.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        su = (
            await s.execute(select(Staff).where(Staff.username == "superuser"))
        ).scalar_one_or_none()
    total = len(unpaid_bills)
    total_amount = sum(float(b.billed_amount) + float(b.penalty) for b in unpaid_bills)
    print(
        f"  > Found {total} unpaid bills, total due: PHP {total_amount:,.2f}",
        flush=True,
    )
    report(5, f"Found {total} unpaid bills")
    su_id = su.id if su else 1
    sem = asyncio.Semaphore(WORKER_JOB_CONCURRENCY)
    paid = 0
    next_log = 100
    done = 0
    for batch_start in range(0, total, 64):
        batch = unpaid_bills[batch_start : batch_start + 64]
        results = await asyncio.gather(*(_process_one_pay(sem, b.id, su_id, now) for b in batch))
        for dp, _ in results:
            paid += dp
            done += 1
            report(5 + round(90 * done / max(total, 1), 1), f"Paid {done}/{total}")
            if paid >= next_log:
                print(f"  > Paid {paid}/{total} bills...", flush=True)
                next_log += 100
    total_dur = _time.time() - t0
    print(
        f"  > Done: {paid} bills paid (PHP {total_amount:,.2f}) in {total_dur:.1f}s",
        flush=True,
    )
    report(100, f"Done. {paid} bills paid ({total_dur:.1f}s).")


async def _process_one_unpay(sem: asyncio.Semaphore, bill_id: int) -> tuple[int, int]:
    # returns (undone_delta, customer_number) for this bill
    async with sem, session_factory()() as s:
        bill = (await s.execute(select(Billing).where(Billing.id == bill_id))).scalar_one_or_none()
        if not bill:
            return (0, 0)
        cnum = bill.customer_number
        bill.is_paid = False
        bill.paid_amount = 0
        bill.receipt_number = None
        bill.cashier_id = None
        bill.payment_timestamp = None
        bill.date_paid = None
        bill.carryover_offset = 0
        await s.commit()
        return (1, cnum)


async def handle_remove_payment_this_month(
    params: dict[str, Any], report: Callable[[float, str], None]
) -> None:
    t0 = _time.time()
    print("  > Finding paid this-month bills...", flush=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with session_factory()() as s:
        paid_bills = (
            (
                await s.execute(
                    select(Billing)
                    .join(MeterReading, Billing.reading_id == MeterReading.id)
                    .where(
                        MeterReading.timestamp >= first_of_month,
                        Billing.is_paid.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
    total = len(paid_bills)
    total_amount = sum(float(b.paid_amount) for b in paid_bills if b.paid_amount)
    print(f"  > Found {total} paid bills (PHP {total_amount:,.2f} total)", flush=True)
    report(5, f"Found {total} paid bills")
    sem = asyncio.Semaphore(WORKER_JOB_CONCURRENCY)
    undone = 0
    seen: set[int] = set()
    next_log = 100
    done = 0
    for batch_start in range(0, total, 64):
        batch = paid_bills[batch_start : batch_start + 64]
        results = await asyncio.gather(*(_process_one_unpay(sem, b.id) for b in batch))
        for dundone, cnum in results:
            undone += dundone
            done += 1
            if dundone and cnum not in seen:
                seen.add(cnum)
            report(5 + round(90 * done / max(total, 1), 1), f"Reverted {done}/{total}")
            if undone >= next_log:
                print(f"  > Reverted {undone}/{total} bills...", flush=True)
                next_log += 100
    print("  > Recalculating cumulative balances...", flush=True)
    async with session_factory()() as s:
        for cnum in seen:
            await _recalc_cumulative_balance(s, cnum)
            await _recalc_total_due(s, cnum)
        await s.commit()
    total_dur = _time.time() - t0
    print(
        f"  > Done: {undone} bills reverted ({len(seen)} customers affected) in {total_dur:.1f}s",
        flush=True,
    )
    report(100, f"Done. {undone} bills reverted ({len(seen)} customers).")


async def handle_xendit_reconcile(
    params: dict[str, Any], report: Callable[[float, str], None]
) -> None:
    import base64

    t0 = _time.time()

    report(0, "Starting Xendit reconciliation...")

    key = os.environ["XENDIT_API_KEY"]
    if not key or key == "your-xendit-secret-api-key":
        print("  > XENDIT_API_KEY not set or is placeholder — skipping", flush=True)
        report(100, "Reconciliation skipped: Xendit not configured")
        return

    async def _xendit_get(client: httpx.AsyncClient, path: str) -> dict:
        auth = base64.b64encode(f"{key}:".encode()).decode()
        resp = await client.get(
            f"https://api.xendit.co/{path}",
            headers={"Authorization": f"Basic {auth}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def _get_session(client: httpx.AsyncClient, session_id: str) -> dict:
        return await _xendit_get(client, f"sessions/{session_id}")

    print("  > Connected to Xendit API", flush=True)

    threshold = datetime.now(timezone.utc).replace(tzinfo=None).timestamp() - 300
    print("  > Querying pending transactions older than 5 minutes...", flush=True)
    async with session_factory()() as s:
        rows = (
            await s.execute(
                select(XenditTransaction.id, XenditTransaction.date_created).where(
                    XenditTransaction.status == "PENDING"
                )
            )
        ).all()
    pending_ids = [tid for tid, dc in rows if dc and dc.timestamp() < threshold]

    if not pending_ids:
        print(
            "  > No pending transactions to reconcile — queueing next run in 5m",
            flush=True,
        )
        report(100, "No pending transactions to reconcile")
        await _enqueue_next_reconcile()
        return

    total = len(pending_ids)
    print(f"  > Found {total} pending transactions to reconcile", flush=True)
    report(5, f"Found {total} pending transactions")

    async def _reconcile_one(
        sem: asyncio.Semaphore, client: httpx.AsyncClient, txn_id: int
    ) -> tuple[str, str]:
        # returns (result, label); result in succeeded/failed/reversed/skipped/errored
        async with sem:
            async with session_factory()() as s:
                txn = (
                    await s.execute(select(XenditTransaction).where(XenditTransaction.id == txn_id))
                ).scalar_one_or_none()
                if not txn or txn.status != "PENDING":
                    return ("errored", f"txn #{txn_id}")
                label = (
                    f"{(txn.xendit_pr_id or '')[:16]}... ({txn.customer_number}, PHP {txn.amount})"
                )
                try:
                    session_id = (
                        txn.xendit_pr_id
                        if txn.xendit_pr_id and txn.xendit_pr_id.startswith("ps-")
                        else None
                    )

                    if session_id:
                        response = await _get_session(client, session_id)
                        status = response.get("status", "")
                        print(f"    → Session status: {status}", flush=True)
                        if status == "COMPLETED":
                            pr_id = response.get("payment_request_id", "")
                            if pr_id:
                                txn.xendit_pr_id = pr_id
                            payment_id = response.get("payment_id", "")
                            if payment_id:
                                txn.xendit_payment_id = payment_id
                            await s.commit()
                            ss = sync_session()
                            try:
                                ok = await asyncio.to_thread(
                                    _process_xendit_payment_sync, ss, txn_id
                                )
                            finally:
                                ss.close()
                            if ok:
                                print("    → Payment processed successfully", flush=True)
                                return ("succeeded", label)
                            print("    → Payment processing failed", flush=True)
                            return ("errored", label)
                        elif status in ("EXPIRED", "CANCELED"):
                            print(
                                f"    → Session {status.lower()} — marking as failed",
                                flush=True,
                            )
                            txn.status = "FAILED"
                            txn.error_message = f"Session {status.lower()} (reconciled)"
                            await s.commit()
                            return ("failed", label)
                        else:
                            print(
                                f"    → Unknown Session status: {status} — skipping",
                                flush=True,
                            )
                            return ("skipped", label)
                    else:
                        response = await _xendit_get(client, f"payment_requests/{txn.xendit_pr_id}")
                        status = response.get("status", "")
                        if status in ("SUCCEEDED", "PAID", "SETTLED"):
                            print(
                                f"    → Xendit status: {status} — processing payment...",
                                flush=True,
                            )
                            payment_id = response.get("id", "")
                            if payment_id:
                                txn.xendit_payment_id = str(payment_id)
                            await s.commit()
                            ss = sync_session()
                            try:
                                ok = await asyncio.to_thread(
                                    _process_xendit_payment_sync, ss, txn_id
                                )
                            finally:
                                ss.close()
                            if ok:
                                print("    → Payment processed successfully", flush=True)
                                return ("succeeded", label)
                            print("    → Payment processing failed", flush=True)
                            return ("errored", label)
                        elif status in ("FAILED", "EXPIRED"):
                            print(
                                f"    → Xendit status: {status} — marking as failed",
                                flush=True,
                            )
                            txn.status = "FAILED"
                            txn.error_message = f"Payment failed (reconciled: {status})"
                            await s.commit()
                            return ("failed", label)
                        elif status == "REVERSED":
                            print(
                                "    → Xendit status: REVERSED — reversing payment...",
                                flush=True,
                            )
                            ss = sync_session()
                            try:
                                await asyncio.to_thread(_reverse_xendit_payment_sync, ss, txn_id)
                            finally:
                                ss.close()
                            print("    → Payment reversed", flush=True)
                            return ("reversed", label)
                        else:
                            print(
                                f"    → Unknown Xendit status: {status} — skipping",
                                flush=True,
                            )
                            return ("skipped", label)
                except Exception as e:
                    logger.exception(f"Xendit reconciliation error for txn {txn_id}: {e}")
                    print(f"    → ERROR: {e}", flush=True)
                    return ("errored", label)

    succeeded = 0
    failed = 0
    reversed_txns = 0
    errored = 0
    done = 0
    sem = asyncio.Semaphore(WORKER_JOB_CONCURRENCY)
    async with httpx.AsyncClient(timeout=30) as client:
        for batch_start in range(0, total, 64):
            batch = pending_ids[batch_start : batch_start + 64]
            results = await asyncio.gather(*(_reconcile_one(sem, client, tid) for tid in batch))
            for res, label in results:
                done += 1
                if res == "succeeded":
                    succeeded += 1
                elif res == "failed":
                    failed += 1
                elif res == "reversed":
                    reversed_txns += 1
                elif res == "errored":
                    errored += 1
                report(
                    5 + round(85 * done / max(total, 1), 1),
                    f"Reconciling {done}/{total}: {label}",
                )
                print(f"  > [{done}/{total}] {label}", flush=True)

    await _enqueue_next_reconcile()
    total_dur = _time.time() - t0
    summary = f"Reconciled {total} txn ({succeeded} ok, {failed} failed, {reversed_txns} reversed, {errored} errors) in {total_dur:.1f}s"
    print(f"  > {summary}", flush=True)
    print("  > Next reconciliation queued in 5 minutes", flush=True)
    report(100, summary)


def _process_xendit_payment_sync(ss, txn_id: int) -> bool:
    txn = ss.query(XenditTransaction).filter_by(id=txn_id).first()
    if not txn or txn.status != "PENDING":
        return False
    txn_key = txn.id

    customer = ss.query(Customer).filter_by(customer_number=txn.customer_number).first()
    if not customer:
        txn.status = "FAILED"
        txn.error_message = "Customer not found"
        ss.commit()
        return False

    staff = ss.query(Staff).filter_by(username="xendit").first()
    if not staff:
        txn.status = "FAILED"
        txn.error_message = "Xendit system user not found"
        ss.commit()
        return False

    try:
        amount = float(txn.base_amount or txn.amount)
        result, error, status = submit_payment(txn.customer_number, amount, staff.id, session=ss)
        if error:
            ss.rollback()
            txn = ss.query(XenditTransaction).filter_by(id=txn_key).first()
            if txn:
                txn.status = "FAILED"
                txn.error_message = error
                ss.commit()
            return False

        txn.status = "PAID"
        txn.receipt_number = result.get("receipt_number")
        txn.billing_receipt = result.get("receipt_number")
        ss.commit()
        return True
    except Exception as e:
        ss.rollback()
        logger.exception(f"Xendit payment processing failed for txn {txn_key}: {e}")
        txn = ss.query(XenditTransaction).filter_by(id=txn_key).first()
        if txn:
            txn.status = "FAILED"
            txn.error_message = str(e)
            ss.commit()
        return False


def _reverse_xendit_payment_sync(ss, txn_id: int) -> bool:
    txn = ss.query(XenditTransaction).filter_by(id=txn_id).first()
    if not txn or txn.status != "PAID":
        return False

    billing_receipt = txn.billing_receipt
    if not billing_receipt:
        txn.status = "REVERSED"
        txn.error_message = "No billing receipt to reverse"
        ss.commit()
        return True

    bills = ss.query(Billing).filter_by(receipt_number=billing_receipt).with_for_update().all()
    for b in bills:
        b.is_paid = False
        b.paid_amount = 0
        b.receipt_number = None
        b.cashier_id = None
        b.payment_timestamp = None
        b.date_paid = None
        b.carryover_offset = 0

    customer_number = txn.customer_number
    recalc_cumulative_balance(customer_number, session=ss)
    _recalc_total_due_sync(ss, customer_number)

    txn.status = "REVERSED"
    txn.reversed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ss.commit()
    return True


async def _enqueue_next_reconcile() -> None:
    from models import BackgroundTask

    await BackgroundTask.enqueue_unique(
        task_type="xendit_reconcile",
        title="Xendit Reconciliation",
        scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
    )


HANDLERS: dict[str, Callable[[dict[str, Any], Callable[[float, str], None]], Awaitable[None]]] = {
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
