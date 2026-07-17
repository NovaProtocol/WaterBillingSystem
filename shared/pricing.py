from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

LATE_PENALTY: float = 15.00
DUE_DAYS: int = 7

PRICING_TIERS: list[dict[str, Any]] = [
    {
        "label": "First 10 m\u00b3",
        "from_unit": 0,
        "to_unit": 10,
        "rate": 150.00,
        "unit": "flat",
    },
    {
        "label": "11 m\u00b3 to 20 m\u00b3",
        "from_unit": 10,
        "to_unit": 20,
        "rate": 25.00,
        "unit": "m\u00b3",
    },
    {
        "label": "21 m\u00b3 to 30 m\u00b3",
        "from_unit": 20,
        "to_unit": 30,
        "rate": 30.00,
        "unit": "m\u00b3",
    },
    {
        "label": "31 m\u00b3 to 40 m\u00b3",
        "from_unit": 30,
        "to_unit": 40,
        "rate": 35.00,
        "unit": "m\u00b3",
    },
    {
        "label": "41 m\u00b3 and above",
        "from_unit": 40,
        "to_unit": 999999,
        "rate": 40.00,
        "unit": "m\u00b3",
    },
]


def compute_water_bill(consumption: int | float) -> tuple[float, list[dict[str, Any]]]:
    total = 0.0
    breakdown: list[dict[str, Any]] = []
    for tier in PRICING_TIERS:
        if consumption <= tier["from_unit"]:
            units_in_tier = 0
        else:
            units_in_tier = min(consumption, tier["to_unit"]) - tier["from_unit"]
        if tier["unit"] == "flat":
            charge = tier["rate"] if units_in_tier > 0 else 0
        else:
            charge = units_in_tier * tier["rate"]
        breakdown.append(
            {"label": tier["label"], "units": units_in_tier, "charge": charge}
        )
        total += charge
    return total, breakdown


def compute_penalty(
    reading_timestamp: datetime, billing_record: Any | None = None
) -> float:
    due_dt = reading_timestamp + timedelta(days=DUE_DAYS)
    if billing_record:
        payment_ts = billing_record.payment_timestamp or billing_record.date_paid or datetime.now(tz=timezone.utc).replace(tzinfo=None)
        if payment_ts > due_dt:
            return LATE_PENALTY
    else:
        if datetime.now(tz=timezone.utc).replace(tzinfo=None) > due_dt:
            return LATE_PENALTY
    return 0.0
