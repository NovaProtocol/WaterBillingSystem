from __future__ import annotations

from db_async import session
from models import PaymentMethod
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


async def get_method(code: str) -> PaymentMethod | None:
    result = await session().execute(
        select(PaymentMethod).where(PaymentMethod.code == code, PaymentMethod.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def calculate_fee(amount: float, method_code: str) -> tuple[float, float]:
    method = await get_method(method_code)
    if not method:
        return 0.0, 0.0
    return float(method.fee_percent or 0), method.fee_for(amount)


PAYMENT_METHODS: list[dict] = [
    # ── E-Wallets ──
    {
        "code": "gcash_ewallet",
        "label": "GCash E-Wallet",
        "channel_code": "GCASH",
        "fee_percent": 3.00,
        "xendit_fee": 11.00,
        "sort_order": 1,
    },
    {
        "code": "maya_ewallet",
        "label": "Maya E-Wallet",
        "channel_code": "PAYMAYA",
        "fee_percent": 2.00,
        "xendit_fee": 11.00,
        "sort_order": 3,
    },
    {
        "code": "grabfpay",
        "label": "GrabPay",
        "channel_code": "GRABPAY",
        "fee_percent": 2.00,
        "xendit_fee": 11.00,
        "sort_order": 5,
    },
    {
        "code": "shopeepay",
        "label": "ShopeePay",
        "channel_code": "SHOPEEPAY",
        "fee_percent": 2.50,
        "xendit_fee": 11.00,
        "sort_order": 6,
    },
    # ── Cards ──
    {
        "code": "card_domestic",
        "label": "Card (Domestic PHP)",
        "channel_code": "CARDS",
        "fee_percent": 3.50,
        "xendit_fee": 11.00,
        "sort_order": 10,
    },
    {
        "code": "card_international",
        "label": "Card (International PHP)",
        "channel_code": "CARDS",
        "fee_percent": 4.50,
        "fee_flat": 10.00,
        "xendit_fee": 11.00,
        "sort_order": 11,
    },
    # ── Direct Debit ──
    {
        "code": "bpi_directdebit",
        "label": "BPI Direct Debit",
        "channel_code": "BPI",
        "fee_percent": 1.30,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 21,
    },
    {
        "code": "ubp_directdebit",
        "label": "UBP Direct Debit",
        "channel_code": "UBP",
        "fee_percent": 1.30,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 23,
    },
    {
        "code": "rcbc_directdebit",
        "label": "RCBC Direct Debit",
        "channel_code": "RCBC",
        "fee_percent": 1.30,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 24,
    },
    # ── Online Banking ──
    {
        "code": "online_banking",
        "label": "Online Banking",
        "channel_code": "BPI",
        "fee_percent": 1.50,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 30,
    },
    # ── Over-the-Counter ──
    {
        "code": "7eleven_otc",
        "label": "7-Eleven OTC",
        "channel_code": "OTC",
        "fee_percent": 1.50,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 40,
    },
    {
        "code": "cebuana_otc",
        "label": "Cebuana Lhuillier OTC",
        "channel_code": "OTC",
        "fee_flat": 25.00,
        "xendit_fee": 11.00,
        "sort_order": 41,
    },
    {
        "code": "ecpay_otc",
        "label": "ECPay OTC",
        "channel_code": "OTC",
        "fee_percent": 1.50,
        "fee_minimum": 25.00,
        "xendit_fee": 11.00,
        "sort_order": 42,
    },
    {
        "code": "lbc_otc",
        "label": "LBC OTC",
        "channel_code": "OTC",
        "fee_flat": 25.00,
        "xendit_fee": 11.00,
        "sort_order": 46,
    },
    {
        "code": "mlhuillier_otc",
        "label": "M Lhuillier OTC",
        "channel_code": "OTC",
        "fee_flat": 20.00,
        "xendit_fee": 11.00,
        "sort_order": 47,
    },
    {
        "code": "palawan_otc",
        "label": "Palawan Express OTC",
        "channel_code": "OTC",
        "fee_flat": 25.00,
        "xendit_fee": 11.00,
        "sort_order": 48,
    },
    {
        "code": "robinsons_otc",
        "label": "Robinsons Bills Payment",
        "channel_code": "OTC",
        "fee_flat": 25.00,
        "xendit_fee": 11.00,
        "sort_order": 49,
    },
    {
        "code": "sm_otc",
        "label": "SM Bills Payment",
        "channel_code": "OTC",
        "fee_flat": 20.00,
        "xendit_fee": 11.00,
        "sort_order": 50,
    },
    {
        "code": "ussc_otc",
        "label": "USSC OTC",
        "channel_code": "OTC",
        "fee_flat": 20.00,
        "xendit_fee": 11.00,
        "sort_order": 51,
    },
    # ── QR / BNPL / VA ──
    {
        "code": "qrph",
        "label": "QRPh",
        "channel_code": "QRPH",
        "fee_percent": 1.50,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 60,
    },
    {
        "code": "billease",
        "label": "BillEase BNPL",
        "channel_code": "BILLEASE",
        "fee_percent": 1.50,
        "xendit_fee": 11.00,
        "sort_order": 61,
    },
    {
        "code": "virtual_account",
        "label": "Virtual Account",
        "channel_code": "VIRTUAL_ACCOUNT",
        "fee_percent": 1.00,
        "fee_minimum": 15.00,
        "xendit_fee": 11.00,
        "sort_order": 62,
    },
]


async def seed_payment_methods() -> None:
    import logging

    logger = logging.getLogger("api")
    result = await session().execute(select(PaymentMethod))
    existing = {m.code for m in result.scalars().all()}
    added = 0
    for data in PAYMENT_METHODS:
        if data["code"] not in existing:
            method = PaymentMethod(
                code=data["code"],
                label=data["label"],
                provider="xendit",
                channel_code=data.get("channel_code"),
                fee_percent=data.get("fee_percent"),
                fee_flat=data.get("fee_flat"),
                fee_minimum=data.get("fee_minimum"),
                xendit_fee=data.get("xendit_fee"),
                is_active=True,
                sort_order=data.get("sort_order", 0),
            )
            session().add(method)
            added += 1
    if added:
        try:
            await session().commit()
        except IntegrityError:
            await session().rollback()
    logger.info(f"Seeded {added} payment methods")
