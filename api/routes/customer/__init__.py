from __future__ import annotations

from fastapi import APIRouter

from routes.customer.accounts import router as _accounts_router
from routes.customer.billing import router as _billing_router
from routes.customer.nfc import router as _nfc_router
from routes.customer.payments import router as _payments_router
from routes.customer.readings import router as _readings_router

router = APIRouter(prefix="/api")
for _r in (
    _accounts_router,
    _readings_router,
    _billing_router,
    _nfc_router,
    _payments_router,
):
    router.include_router(_r)

__all__ = ["router"]
