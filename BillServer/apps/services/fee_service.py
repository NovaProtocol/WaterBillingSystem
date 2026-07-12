from __future__ import annotations

from typing import Tuple

from apps.models import Config

DEFAULT_FEE_CONFIG_KEY = "payment_fee_default"


def get_fee_rate(payment_method: str) -> float:
    config = Config.query.filter_by(key=f"payment_fee_{payment_method}").first()
    if config and config.value:
        try:
            return float(config.value)
        except (ValueError, TypeError):
            pass
    config = Config.query.filter_by(key=DEFAULT_FEE_CONFIG_KEY).first()
    if config and config.value:
        try:
            return float(config.value)
        except (ValueError, TypeError):
            pass
    return 0.0


def calculate_fee(amount: float, payment_method: str) -> Tuple[float, float]:
    rate = get_fee_rate(payment_method)
    fee = round(amount * rate / 100, 2)
    return rate, fee
