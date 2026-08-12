"""Startup DB preflight: safe auto-fixes, loud crash on risky schema drift.

Policy (see the DB preflight design):
a fix is SAFE iff applying it cannot invalidate existing data. Missing
tables/indexes, widening, and NOT NULL -> NULL are safe. Missing columns,
incompatible types, and time-type violations are FATAL (sys.exit(1))."""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import UniqueConstraint, inspect as sa_inspect, text
from sqlalchemy.types import (BigInteger, Boolean, DateTime, Float, Integer,
                              JSON, LargeBinary, Numeric, SmallInteger,
                              String, Text)

from db_async import Base, engine, sync_engine

logger = logging.getLogger("preflight")

TIME_NAME_RE = re.compile(
    r"timestamp|date_|_at$|created|updated|scheduled|started|finished|reversed|modified"
)


def is_time_name(name: str) -> bool:
    return bool(TIME_NAME_RE.search(name))


# Canonical index list from the 2026-08-06 query audit (see spec). Entries are
# (name, table, [columns], unique). Missing entries are auto-created at startup.
MANIFEST = [
    ("ix_meter_readings_customer_timestamp", "meter_readings", ["customer_number", "timestamp"], False),
    ("ix_meter_readings_date_created", "meter_readings", ["date_created"], False),
    ("ix_meter_readings_date_modified", "meter_readings", ["date_modified"], False),
    ("ix_billings_reading_id", "billings", ["reading_id"], False),
    ("ix_billings_receipt_number", "billings", ["receipt_number"], False),
    ("ix_billings_customer_date_created", "billings", ["customer_number", "date_created"], False),
    ("ix_billings_customer_paid_created", "billings", ["customer_number", "is_paid", "date_created"], False),
    ("ix_billings_payment_timestamp", "billings", ["payment_timestamp", "is_paid", "cashier_id"], False),
    ("ix_xendit_status_created", "xendit_transactions", ["status", "date_created"], False),
    ("ix_background_tasks_status_sched", "background_tasks", ["status", "scheduled_at", "created_at"], False),
    ("ix_customers_active_modified", "customers", ["is_active", "date_modified"], False),
    ("ix_customers_name", "customers", ["name"], False),
    ("ix_management_logs_target_ts", "management_logs", ["target_type", "timestamp"], False),
    ("ix_management_logs_target_action", "management_logs", ["target_type", "action_type", "date_created"], False),
]


def validate_manifest(metadata, manifest) -> list[str]:
    """Return a list of errors; empty means every entry references a real
    table and column in the models."""
    errors: list[str] = []
    tables = {t.name: t for t in metadata.sorted_tables}
    for name, table, cols, unique in manifest:
        t = tables.get(table)
        if t is None:
            errors.append(f"manifest: unknown table {table} for index {name}")
            continue
        for c in cols:
            if c not in t.c:
                errors.append(f"manifest: {table} has no column {c} for index {name}")
    return errors


def _expected_indexes(table):
    expected = []
    seen = set()
    for col in table.columns:
        if col.index:
            # SQLAlchemy materializes index=True on a unique column as a
            # single UNIQUE index named ix_<table>_<col>.
            add = (f"ix_{table.name}_{col.name}", [col.name], bool(col.unique))
            if (tuple(add[1]), add[2]) not in seen:
                expected.append(add)
                seen.add((tuple(add[1]), add[2]))
        if col.unique:
            add = (f"uq_{table.name}_{col.name}", [col.name], True)
            if (tuple(add[1]), add[2]) not in seen:
                expected.append(add)
                seen.add((tuple(add[1]), add[2]))
    for cons in table.constraints:
        if isinstance(cons, UniqueConstraint):
            cols = list(cons.columns.keys())
            add = (cons.name or f"uq_{table.name}_{'_'.join(cols)}", cols, True)
            if (tuple(add[1]), add[2]) not in seen:
                expected.append(add)
                seen.add((tuple(add[1]), add[2]))
    return expected


@dataclass(frozen=True)
class TypeSpec:
    family: str                 # STRING | TEXT | INTEGER | NUMERIC | FLOAT | BOOLEAN | DATETIME | BLOB | JSON | UNKNOWN
    size: int | None = None     # STRING: length; TEXT: 0-3 tier; INTEGER: 0-4 tier
    precision: int | None = None
    scale: int | None = None

    def type_sql(self) -> str:
        if self.family == "STRING":
            return f"VARCHAR({self.size or 255})"
        if self.family == "TEXT":
            return {0: "TINYTEXT", 1: "TEXT", 2: "MEDIUMTEXT", 3: "LONGTEXT"}[
                self.size if self.size is not None else 1]
        if self.family == "INTEGER":
            return {0: "TINYINT", 1: "SMALLINT", 2: "MEDIUMINT", 3: "INT",
                    4: "BIGINT"}[self.size if self.size is not None else 3]
        if self.family == "NUMERIC":
            return f"DECIMAL({self.precision or 10}, {self.scale or 2})"
        if self.family == "BOOLEAN":
            return "TINYINT(1)"
        if self.family == "DATETIME":
            return "DATETIME"
        if self.family == "FLOAT":
            return "FLOAT"
        if self.family == "BLOB":
            return "BLOB"
        if self.family == "JSON":
            return "JSON"
        return "TEXT"


def from_model(typ) -> TypeSpec:
    if isinstance(typ, Text):
        ln = typ.length
        if ln is None or ln <= 2 ** 16:
            return TypeSpec("TEXT", size=1)
        if ln <= 2 ** 24:
            return TypeSpec("TEXT", size=2)
        return TypeSpec("TEXT", size=3)
    if isinstance(typ, String):
        return TypeSpec("STRING", size=typ.length or 255)
    if isinstance(typ, BigInteger):
        return TypeSpec("INTEGER", size=4)
    if isinstance(typ, SmallInteger):
        return TypeSpec("INTEGER", size=1)
    if isinstance(typ, Integer):
        return TypeSpec("INTEGER", size=3)
    if isinstance(typ, Float):
        return TypeSpec("FLOAT")
    if isinstance(typ, Numeric):
        return TypeSpec("NUMERIC", precision=typ.precision, scale=typ.scale)
    if isinstance(typ, Boolean):
        return TypeSpec("BOOLEAN")
    if isinstance(typ, DateTime):
        return TypeSpec("DATETIME")
    if isinstance(typ, LargeBinary):
        return TypeSpec("BLOB")
    if isinstance(typ, JSON):
        return TypeSpec("JSON")
    return TypeSpec("UNKNOWN")


_TYPER = re.compile(r"^\s*([A-Za-z]+)(?:\((\d+)(?:,\s*(\d+))?\))?\s*$")
_TEXT_TIERS = {"TINYTEXT": 0, "TEXT": 1, "MEDIUMTEXT": 2, "LONGTEXT": 3}
_INT_TIERS = {"TINYINT": 0, "SMALLINT": 1, "MEDIUMINT": 2, "INT": 3, "INTEGER": 3, "BIGINT": 4}


def from_db(type_str: str) -> TypeSpec:
    m = _TYPER.match(type_str or "")
    if not m:
        return TypeSpec("UNKNOWN")
    base, a, b = m.group(1).upper(), m.group(2), m.group(3)
    if base in ("VARCHAR", "CHAR", "NVARCHAR", "NCHAR", "VARYING", "STRING"):
        return TypeSpec("STRING", size=int(a) if a else 255)
    if base in _TEXT_TIERS:
        return TypeSpec("TEXT", size=_TEXT_TIERS[base])
    if base in ("DATETIME", "TIMESTAMP"):
        return TypeSpec("DATETIME")
    if base in ("DECIMAL", "NUMERIC", "FIXED"):
        return TypeSpec("NUMERIC",
                        precision=int(a) if a else None,
                        scale=int(b) if b else None)
    if base == "BOOLEAN":
        return TypeSpec("BOOLEAN")
    if base == "TINYINT":
        if a == "1":
            return TypeSpec("BOOLEAN")
        return TypeSpec("INTEGER", size=0)
    if base in _INT_TIERS:
        return TypeSpec("INTEGER", size=_INT_TIERS[base])
    if base in ("FLOAT", "DOUBLE", "REAL"):
        return TypeSpec("FLOAT")
    if base in ("BLOB", "TINYBLOB", "MEDIUMBLOB", "LONGBLOB", "BINARY", "VARBINARY"):
        return TypeSpec("BLOB")
    if base == "JSON":
        return TypeSpec("JSON")
    return TypeSpec("UNKNOWN")


def compare(db_spec: TypeSpec, model_spec: TypeSpec) -> str:
    # MySQL Boolean is TINYINT(1); SQLAlchemy reflection on MySQL 8.x reports
    # the column without the deprecated display width, so a genuine boolean
    # column arrives as widthless TINYINT. Storage is identical (1-byte),
    # no data can be invalidated, so this is a match, not a family mismatch.
    if (db_spec.family == "INTEGER" and db_spec.size == 0
            and model_spec.family == "BOOLEAN"):
        return "ok"
    if db_spec.family != model_spec.family:
        return "fatal"
    if db_spec.family == "STRING":
        if db_spec.size < model_spec.size:
            return "widen"
        if db_spec.size > model_spec.size:
            return "warn"
        return "ok"
    if db_spec.family == "TEXT":
        return "widen" if db_spec.size < model_spec.size else "ok"
    if db_spec.family == "INTEGER":
        return "widen" if db_spec.size < model_spec.size else "ok"
    if db_spec.family == "NUMERIC":
        if db_spec.precision is None or model_spec.precision is None:
            return "ok"
        # Data-safe rule: capacity per dimension, int = precision - scale.
        # "widen" only when the model covers the DB's existing capacity in
        # BOTH dimensions and needs more in at least one; "warn" when the DB
        # has capacity (integer or fractional) the model would not cover —
        # altering would round/truncate existing data.
        db_int = db_spec.precision - (db_spec.scale or 0)
        db_frac = db_spec.scale or 0
        model_int = model_spec.precision - (model_spec.scale or 0)
        model_frac = model_spec.scale or 0
        if db_int > model_int or db_frac > model_frac:
            return "warn"
        if db_int < model_int or db_frac < model_frac:
            return "widen"
        return "ok"
    return "ok"


@dataclass
class Finding:
    kind: str          # created_index | dropped_index | modified_column | warning | fatal
    message: str
    ddl: str | None = None


def _type_sql(col) -> str:
    return from_model(col.type).type_sql()


def _default_sql(col) -> str:
    default = getattr(col.default, "arg", None)
    if default is None or callable(default):
        return ""
    if isinstance(default, str):
        return f" DEFAULT '{default}'"
    return f" DEFAULT {default}"


def _modify_column_sql(table: str, col) -> str:
    null = "" if col.nullable else " NOT NULL"
    return (f"ALTER TABLE {table} MODIFY {col.name} {_type_sql(col)}"
            f"{_default_sql(col)}{null}")


def _add_column_sql(table: str, col) -> str:
    sql = (f"ALTER TABLE {table} ADD COLUMN {col.name} {_type_sql(col)}"
           f"{_default_sql(col)}")
    sql += " NULL" if col.nullable else " NOT NULL"
    return sql


def decide(inspector, metadata, manifest) -> list[Finding]:
    findings: list[Finding] = []
    db_tables = set(inspector.get_table_names())
    model_tables = {t.name: t for t in metadata.sorted_tables}

    for name in sorted(model_tables):
        if name not in db_tables:
            findings.append(Finding(
                "fatal",
                f"table '{name}' exists in models but not in the database "
                f"(create_all failed or DB was partially reset)"))

    for name, table in sorted(model_tables.items()):
        if name not in db_tables:
            continue
        db_cols = {c["name"]: c for c in inspector.get_columns(name)}
        for col in table.columns:
            if col.name not in db_cols:
                findings.append(Finding(
                    "fatal",
                    f"missing column {name}.{col.name} (refusing to auto-add; "
                    f"NULL would mutate data)",
                    ddl=_add_column_sql(name, col)))
                continue
            model_spec = from_model(col.type)
            if is_time_name(col.name) and model_spec.family != "DATETIME":
                findings.append(Finding(
                    "fatal",
                    f"time-named column {name}.{col.name} has model type "
                    f"{model_spec.type_sql()} — must be DateTime"))
                continue
            db_col = db_cols[col.name]
            db_spec = from_db(str(db_col["type"]))
            verdict = compare(db_spec, model_spec)
            if verdict == "fatal":
                findings.append(Finding(
                    "fatal",
                    f"type mismatch {name}.{col.name}: db "
                    f"{db_col['type']} vs model {model_spec.type_sql()}",
                    ddl=_modify_column_sql(name, col)))
            elif verdict == "widen":
                findings.append(Finding(
                    "modified_column",
                    f"widened {name}.{col.name} "
                    f"({db_col['type']} -> {model_spec.type_sql()})",
                    ddl=_modify_column_sql(name, col)))
            elif verdict == "warn":
                findings.append(Finding(
                    "warning",
                    f"{name}.{col.name}: db type {db_col['type']} is wider than "
                    f"model {model_spec.type_sql()} — left alone (shrinking "
                    f"could truncate data)"))
            if col.nullable and db_col.get("nullable") is False:
                findings.append(Finding(
                    "modified_column",
                    f"loosened {name}.{col.name} to nullable",
                    ddl=_modify_column_sql(name, col)))
            elif not col.nullable and db_col.get("nullable") is True:
                findings.append(Finding(
                    "warning",
                    f"{name}.{col.name}: db is nullable but model declares "
                    f"NOT NULL — left alone (enforcing could reject data)"))

    for name, table in sorted(model_tables.items()):
        if name not in db_tables:
            continue
        existing = {ix["name"]: ix for ix in inspector.get_indexes(name)}
        manifest_here = [m for m in manifest if m[1] == name]
        expected = _expected_indexes(table) + [
            (m[0], list(m[2]), m[3]) for m in manifest_here]

        for exp_name, exp_cols, exp_unique in expected:
            ix = existing.get(exp_name)
            if ix is None:
                if any(
                    list(e["column_names"]) == exp_cols
                    and bool(e["unique"]) == exp_unique
                    for e in existing.values()
                ):
                    continue  # already covered by an existing index
                uniq = "UNIQUE " if exp_unique else ""
                findings.append(Finding(
                    "created_index",
                    f"creating index {exp_name} on {name} ({', '.join(exp_cols)})",
                    ddl=f"CREATE {uniq}INDEX {exp_name} ON {name} "
                        f"({', '.join(exp_cols)})"))
            elif (
                list(ix["column_names"]) != exp_cols
                or bool(ix["unique"]) != exp_unique
            ):
                findings.append(Finding(
                    "fatal",
                    f"index {exp_name} on {name} exists with columns "
                    f"{ix['column_names']} but models/manifest declare "
                    f"{exp_cols}"))

    # Redundancy sweep: drop non-unique indexes that are strict left-prefixes
    # of another index on the same table (never PRIMARY/UNIQUE, never an index
    # the models or manifest expect).
    for name, table in sorted(model_tables.items()):
        if name not in db_tables:
            continue
        existing = inspector.get_indexes(name)
        expected_colsets = {
            tuple(e[1]) for e in (_expected_indexes(table)
                                  + [(m[0], list(m[2]), m[3])
                                     for m in manifest if m[1] == name])}
        for a in existing:
            if a["unique"] or not a["name"]:
                continue
            cols_a = list(a["column_names"])
            if not cols_a or tuple(cols_a) in expected_colsets:
                continue
            for b in existing:
                if b is a or b["name"] == a["name"]:
                    continue
                cols_b = list(b["column_names"])
                if len(cols_a) < len(cols_b) and cols_a == cols_b[: len(cols_a)]:
                    findings.append(Finding(
                        "dropped_index",
                        f"dropping redundant index {a['name']} on {name} "
                        f"(covered by {b['name']})",
                        ddl=f"DROP INDEX {a['name']} ON {name}"))
                    break

    return findings


async def apply(findings: list[Finding], eng) -> None:
    """Execute DDL for safe findings. Only MySQL executes; other dialects
    (e.g. SQLite in tests) log a skip warning — they are not the deployment
    target and their DDL syntax differs."""
    ddl_list = [f.ddl for f in findings if f.ddl]
    if not ddl_list:
        return
    if eng.dialect.name != "mysql":
        for sql in ddl_list:
            logger.warning("preflight: skipping DDL on %s dialect: %s",
                           eng.dialect.name, sql)
        return
    async with eng.begin() as conn:
        for sql in ddl_list:
            await conn.execute(text(sql))
            logger.info("preflight: applied DDL: %s", sql)


def run_preflight() -> list:
    """Startup preflight: inspect, decide, crash on fatal findings.

    Runs synchronously; returns findings so the caller (lifespan) can pass
    them to `apply`. `apply` is awaited by the caller."""
    errs = validate_manifest(Base.metadata, MANIFEST)
    if errs:
        for err in errs:
            print(f"FATAL: {err}", file=sys.stderr)
        logger.error("preflight FATAL: %d manifest error(s) — refusing to start",
                     len(errs))
        sys.exit(1)
    findings = decide(sa_inspect(sync_engine()), Base.metadata, MANIFEST)
    fatals = [f for f in findings if f.kind == "fatal"]
    if fatals:
        print(
            "FATAL: DB preflight found problems that cannot be auto-fixed. "
            "Container will not start until resolved (back up the DB, then "
            "run the listed commands or restore).",
            file=sys.stderr,
        )
        for f in fatals:
            print(f"  - {f.message}", file=sys.stderr)
            if f.ddl:
                print(f"    suggested command: {f.ddl}", file=sys.stderr)
        logger.error("preflight FATAL: %d issue(s) — refusing to start",
                     len(fatals))
        sys.exit(1)
    for f in findings:
        if f.kind == "created_index":
            logger.info("preflight: %s", f.message)
        elif f.kind == "dropped_index":
            logger.info("preflight: %s", f.message)
        elif f.kind == "modified_column":
            logger.info("preflight: %s", f.message)
        elif f.kind == "warning":
            logger.warning("preflight: %s", f.message)
    if not findings:
        logger.info("preflight: OK — schema matches models (no changes needed)")
    else:
        logger.info("preflight: OK — %d change(s) will be applied", len(findings))
    return findings
