#!/usr/bin/env python3
"""
Standalone test-data seeder. Connects directly to MySQL, no Flask needed.

Usage:
  python seed_test_data.py --customers 5000 --months 120

Generates realistic water consumption data with seasonal variation
and yearly growth trends. Creates readings, billing records, and payments.

WARNING: DO NOT RUN OUTSIDE USER TERMINAL
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import logging
import math
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

import pymysql
import pymysql.cursors

DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASS = "BillServerDB"
DB_NAME = "BillServerDB"

BACKUP_DIR = Path(__file__).resolve().parent / "db_backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apps.pricing import compute_water_bill

# ── Philippine locale data ──────────────────────────────────────────────────
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

ST_JUDE_DATA = {
    "Phase L-1 (St. Jude Village)": {
        "barangays": ["Brgy. Cotta"],
        "streets": ["St. Peregrine St", "St. Peter Lane", "St. Jude Ave", "San Lorenzo Ruiz St"],
        "weight": 15,
        "blocks": [f"Block {i}" for i in range(1, 15)],
    },
    "Phase L-2A (St. Jude Village)": {
        "barangays": ["Brgy. Ibabang Dupay"],
        "streets": ["St. Paul St", "St. John St", "St. Matthew St", "Immaculate Conception Drive"],
        "weight": 15,
        "blocks": [f"Block {i}" for i in range(1, 15)],
    },
    "Phase L-2C (St. Jude East)": {
        "barangays": ["Brgy. Kanlurang Mayao", "Brgy. Mayao Crossing"],
        "streets": ["St. Thomas St", "St. Luke St", "St. Mark St", "San Pedro Calungsod St"],
        "weight": 30,
        "blocks": [f"Block {i}" for i in range(1, 35)],
    },
    "Phase L-3D (St. Jude East)": {
        "barangays": ["Brgy. Ilayang Mayao", "Brgy. Mayao Crossing"],
        "streets": ["St. Joseph St", "St. Mary St", "St. Anne St", "St. Therese St"],
        "weight": 20,
        "blocks": [f"Block {i}" for i in range(1, 25)],
    },
    "Phase P-1 (Pagbilao)": {
        "barangays": ["Brgy. Bukal", "Brgy. Mapagong"],
        "streets": ["San Vicente Ferrer St", "San Isidro Labrador St", "San Roque St"],
        "weight": 10,
        "blocks": [f"Block {i}" for i in range(1, 10)],
    },
    "Phase S-1 (Sariaya)": {
        "barangays": ["Brgy. Santo Cristo", "Brgy. Manggalang"],
        "streets": ["San Francisco de Asis St", "Santa Clara St", "Santo Domingo St"],
        "weight": 7,
        "blocks": [f"Block {i}" for i in range(1, 8)],
    },
    "Phase C-1 (Candelaria)": {
        "barangays": ["Brgy. Masin", "Brgy. Pahinga Norte"],
        "streets": ["San Miguel St", "San Gabriel St", "San Rafael St"],
        "weight": 3,
        "blocks": [f"Block {i}" for i in range(1, 5)],
    },
}

PHASE_NAMES = list(ST_JUDE_DATA.keys())
PHASE_WEIGHTS = [ST_JUDE_DATA[p]["weight"] for p in PHASE_NAMES]

STAFF_NAMES = [
    "Samantha", "Marcus", "Angelo", "Bianca", "Carlos", "Diana",
    "Emilio", "Francesca", "Gabriel", "Hannah", "Isidro", "Jasmine",
    "Kevin", "Lara", "Miguel", "Nina", "Oscar", "Patricia",
    "Ramon", "Sofia", "Tomas", "Vera",
]


def _pick_name(exclude: set[str]) -> str:
    available = list(set(STAFF_NAMES) - exclude)
    return random.choice(available) if available else "Staff"


BASE_LAT = 13.9360069
BASE_LON = 121.6314674


def _coord_offset(
    lat: float, lon: float, radius_m: float = 1000
) -> tuple[float, float]:
    r = random.random() * radius_m
    theta = random.random() * 2 * math.pi
    dlat = r / 111320
    dlon = r / (111320 * math.cos(math.radians(lat)))
    return round(lat + dlat * math.cos(theta), 7), round(
        lon + dlon * math.sin(theta), 7
    )


def hash_pass(password: str) -> bytes:
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
    pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)
    return salt + binascii.hexlify(pwdhash)


def get_conn() -> Any:
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )


# ── Consumption model ───────────────────────────────────────────────────────

def seasonal_factor(month: int) -> float:
    """Return seasonal multiplier for a given month (1=Jan) in the Philippines."""
    if month in (3, 4, 5):       # Summer — higher water usage
        return random.uniform(1.10, 1.30)
    elif month in (6, 7, 8, 9, 10):  # Rainy — moderate
        return random.uniform(0.90, 1.05)
    else:                          # Cool (11, 12, 1, 2) — lower usage
        return random.uniform(0.82, 0.98)


def generate_consumption_series(
    months: int,
    base: float,
    yearly_growth: float,
    rng: random.Random,
) -> list[float]:
    """Generate a series of monthly consumption values.

    Args:
        months: Number of months to generate.
        base: Base monthly consumption in m³ (before growth/season).
        yearly_growth: Compound yearly growth rate (-0.02 to 0.05).
        rng: Per-customer random state.

    Returns list of consumption values in chronological order.
    """
    values: list[float] = []
    for m in range(months):
        year = m // 12
        month = (m % 12) + 1
        grown_base = base * ((1.0 + yearly_growth) ** year)
        seasonal = seasonal_factor(month)
        noise = rng.uniform(0.92, 1.08)
        consumption = grown_base * seasonal * noise
        consumption = max(5.0, round(consumption, 1))
        values.append(consumption)
    return values


# ── Main seed logic ─────────────────────────────────────────────────────────

def seed(n_customers: int, n_months: int, filed_this_month: bool = False) -> None:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now()
    master_rng = random.Random(42)  # reproducible seed

    # ── Staff ────────────────────────────────────────────────────────────
    logger.info("Creating staff accounts...")
    STAFF_SEEDS = [
        {"username": "superuser", "name": "Super Admin", "all_perms": True},
        {"username": "admin", "name": "Admin", "all_perms": True},
        {"username": "cashier1", "name": None,
         "perms": {"can_accept_payment": True}},
        {"username": "cashier2", "name": None,
         "perms": {"can_accept_payment": True}},
        {"username": "reader1", "name": None,
         "perms": {"can_read_meters": True}},
        {"username": "manager", "name": None,
         "perms": {"can_drop_payment": True, "can_drop_reading": True,
                   "can_manage_billing": True}},
        {"username": "enroller", "name": None,
         "perms": {"can_enroll_customer": True, "can_enroll_staff": True}},
    ]
    staff_ids: dict[str, int] = {}
    used_names: set[str] = set()
    for s in STAFF_SEEDS:
        password = hash_pass(s["username"])
        perms = s.get("perms", {})
        if s["name"] is None:
            raw = _pick_name(used_names)
            role = {
                "cashier1": "Cashier", "cashier2": "Cashier",
                "reader1": "Reader", "manager": "Manager",
                "enroller": "Enroller",
            }.get(s["username"], "Staff")
            s["name"] = f"{role} {raw}"
            used_names.add(raw)

        sql = """INSERT INTO staff
            (username, name, password, can_read_meters, can_accept_payment,
             can_enroll_customer, can_drop_reading, can_drop_payment,
             can_enroll_staff, can_manage_billing, is_active,
             date_created, last_modified)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,NOW(),NOW())"""
        vals = (
            s["username"], s["name"], password,
            perms.get('can_read_meters', 0) or (1 if s.get("all_perms") else 0),
            perms.get('can_accept_payment', 0) or (1 if s.get("all_perms") else 0),
            perms.get('can_enroll_customer', 0) or (1 if s.get("all_perms") else 0),
            perms.get('can_drop_reading', 0) or (1 if s.get("all_perms") else 0),
            perms.get('can_drop_payment', 0) or (1 if s.get("all_perms") else 0),
            perms.get('can_enroll_staff', 0) or (1 if s.get("all_perms") else 0),
            perms.get('can_manage_billing', 0) or (1 if s.get("all_perms") else 0),
        )
        cur.execute(sql, vals)
        conn.commit()
        staff_ids[s["username"]] = cur.lastrowid

    # Create xendit system user (automated payments, blank password = cannot log in)
    cur.execute(
        """INSERT IGNORE INTO staff
            (username, name, password, can_accept_payment,
             can_manage_billing, can_drop_payment,
             is_active, date_created, last_modified)
           VALUES (%s,%s,%s,%s,%s,%s,1,NOW(),NOW())""",
        ("xendit", "Xendit", b"", 1, 1, 1),
    )
    staff_ids["xendit"] = cur.lastrowid

    cashier_id = staff_ids.get("cashier1") or staff_ids["superuser"]
    logger.info(f"  {len(STAFF_SEEDS) + 1} staff created")

    # ── API Keys ─────────────────────────────────────────────────────────
    logger.info("Creating API keys...")
    import secrets as _secrets

    token_key_map: dict[int, int] = {}  # staff_id -> token_key_id
    for s in STAFF_SEEDS:
        sid = staff_ids[s["username"]]
        if s.get("all_perms") or s.get("perms", {}).get("can_read_meters"):
            raw_key = "CRDC-" + _secrets.token_hex(16).upper()
            cur.execute(
                """INSERT INTO api_keys (`key`, label, staff_id, is_active,
                   date_created, last_modified)
                   VALUES (%s,%s,%s,1,NOW(),NOW())""",
                (raw_key, f"{s['name']} token", sid),
            )
            conn.commit()
            token_key_map[sid] = cur.lastrowid

    super_sid = staff_ids["superuser"]
    if super_sid not in token_key_map:
        raw_key = "CRDC-STATIC-SUPERUSER-KEY-FOR-SEED-DATA"
        cur.execute(
            """INSERT INTO api_keys (`key`, label, staff_id, is_active,
               date_created, last_modified)
               VALUES (%s,%s,%s,1,NOW(),NOW())""",
            (raw_key, "Superuser seed token", super_sid),
        )
        conn.commit()
        token_key_map[super_sid] = cur.lastrowid

    reader_token_ids = list(token_key_map.values())
    logger.info(f"  {len(token_key_map)} API keys created")

    # ── Date slots ───────────────────────────────────────────────────────
    # Generate dates on the same day as today, going back n_months
    # If filed_this_month=True, the last slot = this month (unpaid)
    # If filed_this_month=False, last slot = last month (unpaid)
    date_slots: list[datetime] = []
    latest_month = now.month if filed_this_month else now.month - 1
    latest_year = now.year
    if latest_month < 1:
        latest_month += 12
        latest_year -= 1

    ref_dt = datetime(latest_year, latest_month, min(now.day, 28))
    for i in range(n_months - 1, -1, -1):
        y = ref_dt.year
        m = ref_dt.month - i
        while m < 1:
            m += 12
            y -= 1
        day = min(now.day, 28)
        date_slots.append(datetime(y, m, day))
    logger.info(f"  Date range: {date_slots[0].strftime('%b %Y')} → "
                f"{date_slots[-1].strftime('%b %Y')} ({n_months} months)")

    # ── Customers ────────────────────────────────────────────────────────
    logger.info(f"Creating {n_customers:,} customers...")
    BATCH = 500

    for batch_start in range(0, n_customers, BATCH):
        batch_end = min(batch_start + BATCH, n_customers)
        rows: list[tuple] = []
        for j in range(batch_start, batch_end):
            cnum = f"{j + 1}"
            first = master_rng.choice(FIRST_NAMES)
            last = master_rng.choice(LAST_NAMES)
            name = f"{first} {last}"
            house_num = master_rng.randint(1, 50)

            phase_name = master_rng.choices(PHASE_NAMES, weights=PHASE_WEIGHTS, k=1)[0]
            phase_data = ST_JUDE_DATA[phase_name]
            phase_display = phase_name  # e.g. "Phase L-1 (St. Jude Village)"
            street = master_rng.choice(phase_data["streets"])
            brgy = master_rng.choice(phase_data["barangays"])
            block = master_rng.choice(phase_data["blocks"])
            addr = f"{house_num} {street}, {brgy}, {block}"

            contact = "09" + "".join(
                master_rng.choice("0123456789") for _ in range(9)
            )
            email = f"c{j+1}{first.lower()}@gmail.com"
            x_coord, y_coord = _coord_offset(BASE_LAT, BASE_LON, 1500)
            rows.append((
                cnum, name, addr, contact, email,
                x_coord, y_coord, phase_display, block,
            ))
        cur.executemany(
            """INSERT INTO customers
                (customer_number, name, address, contact_number, email,
                 x_coordinate, y_coordinate, phase, block,
                 cumulative_balance, max_meter_value,
                 is_active, date_created, date_modified)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       0.00, 99999.00, 1, NOW(), NOW())""",
            rows,
        )
        conn.commit()
        logger.info(f"  customers {batch_start + 1:,}–{batch_end:,} / {n_customers:,}")
    logger.info(f"  {n_customers:,} customers created")

    # ── Readings + Bills + Payments ──────────────────────────────────────
    logger.info(
        f"Creating {n_months} months of readings + billing records "
        f"per customer ({n_customers * n_months:,} total readings)..."
    )
    total_readings = 0
    total_bills = 0
    total_payments = 0
    receipt_seq = 0

    rng_state = random.Random(42)
    billing_batch: list[tuple] = []

    def _flush_billings(cur: Any, batch: list) -> None:
        if not batch:
            return
        cur.executemany(
            """INSERT INTO billings
                (customer_number, reading_id,
                 previous_reading_value, current_reading_value,
                 consumption, billed_amount, penalty,
                 paid_amount, carryover_offset, is_paid,
                 receipt_number, cashier_id,
                 payment_timestamp, date_paid,
                 date_created, date_modified)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())""",
            batch,
        )
        batch.clear()

    for ci in range(n_customers):
        cnum = f"{ci + 1}"

        base_consumption = rng_state.uniform(12, 40)
        yearly_growth = rng_state.uniform(-0.02, 0.05)
        cust_rng = random.Random(ci * 1000 + 42)
        consumptions = generate_consumption_series(
            n_months, base_consumption, yearly_growth, cust_rng
        )

        meter_value = round(rng_state.uniform(100, 500), 1)
        reading_values: list[float] = []
        reading_rows: list[tuple] = []

        for month_idx in range(n_months):
            reading_dt = date_slots[month_idx].replace(
                hour=rng_state.randint(8, 17),
                minute=rng_state.randint(0, 59),
            )
            if month_idx > 0:
                meter_value = round(meter_value + consumptions[month_idx - 1], 1)
            reading_values.append(meter_value)
            reading_rows.append((
                cnum, meter_value, rng_state.choice(reader_token_ids), reading_dt
            ))

        cur.executemany(
            """INSERT INTO meter_readings
                (customer_number, reading_value, token_id, timestamp,
                 date_created, date_modified)
               VALUES (%s,%s,%s,%s,NOW(),NOW())""",
            reading_rows,
        )
        total_readings += n_months
        first_reading_id = cur.lastrowid
        reading_ids = list(range(first_reading_id, first_reading_id + n_months))

        cum_balance = 0.0

        for month_idx in range(1, n_months):
            prev_reading = reading_values[month_idx - 1]
            curr_reading = reading_values[month_idx]
            consumption = round(curr_reading - prev_reading, 1)
            reading_id = reading_ids[month_idx]

            water_bill, _ = compute_water_bill(consumption)

            if month_idx == n_months - 1:
                billing_batch.append((
                    cnum, reading_id,
                    prev_reading, curr_reading,
                    consumption, water_bill, 0,
                    0, 0, 0,
                    None, None,
                    None, None,
                ))
                total_bills += 1
                continue

            pay_dt = date_slots[month_idx] + timedelta(days=rng_state.randint(3, 28))
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

            receipt_seq += 1
            billing_batch.append((
                cnum, reading_id,
                prev_reading, curr_reading,
                consumption, water_bill, penalty,
                paid_amount, carryover_offset, 1,
                f"R{receipt_seq:08d}", cashier_id,
                pay_dt, pay_dt,
            ))
            total_bills += 1
            total_payments += 1

        cur.execute(
            "UPDATE customers SET cumulative_balance = %s WHERE customer_number = %s",
            (round(cum_balance, 2), cnum),
        )

        if len(billing_batch) >= 500:
            _flush_billings(cur, billing_batch)
            conn.commit()

        if (ci + 1) % 200 == 0 or ci == n_customers - 1:
            _flush_billings(cur, billing_batch)
            conn.commit()
            logger.info(
                f"  customer {ci + 1:,} / {n_customers:,}  "
                f"(readings: {total_readings:,}, bills: {total_bills:,}, "
                f"payments: {total_payments:,})"
            )

    _flush_billings(cur, billing_batch)
    conn.commit()
    logger.info(f"  {total_readings:,} meter readings created")
    logger.info(f"  {total_bills:,} billing records created ({total_payments:,} paid)")

    # Recalculate cumulative_balance for all customers from carryover_offsets
    logger.info("Recalculating cumulative balances from carryover offsets...")
    cur.execute("""
        UPDATE customers c
        JOIN (
            SELECT customer_number, COALESCE(SUM(carryover_offset), 0) AS total_offset
            FROM billings
            GROUP BY customer_number
        ) b ON c.customer_number = b.customer_number
        SET c.cumulative_balance = b.total_offset
    """)
    conn.commit()
    logger.info("Cumulative balances synced.")

    logger.info("Seed complete!")

    cur.close()
    conn.close()


def clear(force: bool = False) -> None:
    if not force:
        ans = input(
            "WARNING: This will DELETE ALL EXISTING DATA in the database!\n"
            "Type 'yes' to confirm, anything else to cancel: "
        ).strip().lower()
        if ans != "yes":
            print("Cancelled.")
            sys.exit(1)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    tables = [
        "management_logs", "nfc_tags", "api_keys",
        "billings", "meter_readings", "customers", "staff",
    ]
    for table in tables:
        cur.execute(f"TRUNCATE TABLE {table}")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    cur.close()
    conn.close()
    logger.info("All tables cleared.")


def backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    conn = get_conn()
    cur = conn.cursor()
    tables = [
        "staff", "customers", "meter_readings",
        "nfc_tags", "billings", "api_keys", "management_logs",
    ]
    data = {}
    for table in tables:
        cur.execute(f"SELECT * FROM {table} ORDER BY id")
        rows = cur.fetchall()
        data[table] = []
        for row in rows:
            d = {}
            for k, v in row.items():
                if isinstance(v, (datetime, timedelta)):
                    v = v.isoformat()
                elif isinstance(v, bytes):
                    v = v.hex()
                elif isinstance(v, float):
                    v = round(v, 2)
                d[k] = v
            data[table].append(d)
    cur.close()
    conn.close()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Backup saved: {path}")


def restore(filename: str | None = None) -> None:
    if filename:
        path = Path(filename)
        if not path.is_absolute():
            path = BACKUP_DIR / path
    else:
        backups = sorted(BACKUP_DIR.glob("backup_*.json"))
        if not backups:
            logger.info("No backups found.")
            return
        path = backups[-1]
    logger.info(f"Restoring from: {path}")
    with open(path) as f:
        data = json.load(f)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    tables = [
        "management_logs", "nfc_tags", "api_keys",
        "billings", "meter_readings", "customers", "staff",
    ]
    for table in tables:
        cur.execute(f"TRUNCATE TABLE {table}")
    insert_order = [
        "staff", "customers", "nfc_tags",
        "meter_readings", "billings", "api_keys", "management_logs",
    ]
    for table in insert_order:
        rows = data.get(table, [])
        if not rows:
            continue
        cols = list(rows[0].keys())
        place_holders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({place_holders})"
        for row in rows:
            vals = []
            for c in cols:
                v = row[c]
                if c == "password" and isinstance(v, str):
                    v = bytes.fromhex(v)
                vals.append(v)
            cur.execute(sql, vals)
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Restore complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed realistic test data into BillServer database"
    )
    parser.add_argument(
        "--customers", type=int, required=True,
        help="Number of customers to create",
    )
    parser.add_argument(
        "--months", type=int, required=True,
        help="Number of months of history (e.g. 120 for 10 years)",
    )
    parser.add_argument(
        "--filed_this_month", action="store_true",
        help="Include this month's reading (still unpaid). Default: stops at last month",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip confirmation prompt before clearing data",
    )
    args = parser.parse_args()

    logger.info(f"Seeding {args.customers:,} customers × {args.months} months...")
    clear(force=args.force)
    seed(n_customers=args.customers, n_months=args.months, filed_this_month=args.filed_this_month)
