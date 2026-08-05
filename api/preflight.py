"""Startup DB preflight: safe auto-fixes, loud crash on risky schema drift.

Policy (see docs/superpowers/specs/2026-08-06-db-preflight-design.md):
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

from db_async import Base

logger = logging.getLogger("preflight")

TIME_NAME_RE = re.compile(
    r"timestamp|date_|_at$|created|updated|scheduled|started|finished|reversed|modified"
)


def is_time_name(name: str) -> bool:
    return bool(TIME_NAME_RE.search(name))


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
        if db_spec.precision < model_spec.precision or (
            db_spec.scale or 0) < (model_spec.scale or 0):
            return "widen"
        return "ok"
    return "ok"
