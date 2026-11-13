"""Endpoints the meter-reading app calls, kept in one place.

The app was written against the old `/api/nfc/*`, `/api/key/*`, `/api/pricing`
and `/api/readings/*` paths. The routes were later regrouped under
`/api/customer/*` and `/api/config/*`, which left the phone with no NFC sync and
no bulk reading pull at all. These handlers restore those paths without moving
the logic: every one delegates to the service or query that already owns the
behaviour, so there is a single implementation of billing and a single
definition of the payload.
"""

from __future__ import annotations

import os

from db_async import session
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from models import ApiKey, Config as AppConfig, Customer, MeterReading, NfcTag, Staff
from pydantic import BaseModel
from pricing import DUE_DAYS, LATE_PENALTY, PRICING_TIERS
from sqlalchemy import desc, select
from sqlalchemy.orm import joinedload
from utils import get_staff_id, require_staff

from routes.customer.common import _run_sync

router = APIRouter(prefix="/api")

MOBILE_STAFF_FIELDS = (
    "id",
    "username",
    "name",
    "can_read_meters",
    "can_accept_payment",
    "can_enroll_customer",
    "can_drop_reading",
    "can_drop_payment",
    "can_enroll_staff",
    "can_manage_billing",
)


class NfcSyncPayload(BaseModel):
    enrollments: list[dict] | None = None


class MobileSyncPayload(BaseModel):
    readings: list[dict] | None = None


def _staff_payload(staff) -> dict | None:
    if staff is None:
        return None
    return {field: getattr(staff, field) for field in MOBILE_STAFF_FIELDS}


@router.get("/key/info")
async def key_info(request: Request, api_key=Depends(require_staff())):
    """Validate the key the phone is holding and report its staff permissions."""
    if api_key is True:
        # Internal callers (the portals) arrive without an ApiKey row; report
        # the staff named by X-Staff-ID so the shape stays the same.
        staff_id = await get_staff_id(request)
        staff = await session().get(Staff, staff_id) if staff_id else None
        return {
            "api_key": None,
            "staff": _staff_payload(staff),
        }
    return {
        "api_key": {
            "id": api_key.id,
            "label": api_key.label,
            "is_active": api_key.is_active,
            "date_created": (
                api_key.date_created.isoformat() if api_key.date_created else None
            ),
        },
        "staff": _staff_payload(api_key.staff),
    }


@router.get("/pricing")
async def mobile_pricing(api_key: ApiKey = Depends(require_staff("can_read_meters"))):
    return {
        "tiers": PRICING_TIERS,
        "late_penalty": LATE_PENALTY,
        "due_days": DUE_DAYS,
    }


@router.get("/nfc/config")
async def mobile_nfc_config(api_key: ApiKey = Depends(require_staff("can_read_meters"))):
    result = await session().execute(select(AppConfig).where(AppConfig.key == "nfc_generation"))
    gen_row = result.scalar_one_or_none()
    return {
        "nfc_pwd_secret": os.environ["NFC_PWD_SECRET"],
        "nfc_generation": int(gen_row.value) if gen_row else 0,
    }


@router.get("/nfc/tags")
async def mobile_nfc_tags(api_key: ApiKey = Depends(require_staff("can_read_meters"))):
    result = await session().execute(select(NfcTag).order_by(desc(NfcTag.date_created)))
    return {
        "tags": [
            {"uid": tag.uid, "customer_number": tag.customer_number}
            for tag in result.scalars().all()
        ]
    }


@router.post("/nfc/sync")
async def mobile_nfc_sync(
    payload: NfcSyncPayload,
    api_key: ApiKey = Depends(require_staff("can_enroll_customer")),
):
    """Assign tags enrolled on the phone. A tag already on the same customer is
    accepted as-is so a retried upload is not an error; one held by a different
    customer is reported per entry rather than failing the whole batch."""
    enrollments = payload.enrollments
    if enrollments is None:
        return JSONResponse({"error": "enrollments field is required"}, status_code=400)

    synced: list[dict] = []
    errors: list[dict] = []
    for i, entry in enumerate(enrollments):
        uid = str(entry.get("uid") or "").strip()
        try:
            customer_number = int(entry.get("customer_number"))
        except (TypeError, ValueError):
            customer_number = None
        if not uid or customer_number is None:
            errors.append({"index": i, "error": "uid and customer_number are required"})
            continue

        customer = (
            await session().execute(
                select(Customer).where(Customer.customer_number == customer_number)
            )
        ).scalar_one_or_none()
        if not customer:
            errors.append({"index": i, "error": f"Customer {customer_number} not found"})
            continue

        existing = (
            await session().execute(select(NfcTag).where(NfcTag.uid == uid))
        ).scalar_one_or_none()
        if existing:
            if existing.customer_number == customer_number:
                synced.append({"uid": uid, "customer_number": customer_number})
            else:
                errors.append(
                    {
                        "index": i,
                        "error": f"Tag already assigned to customer {existing.customer_number}",
                    }
                )
            continue

        enrolled_by = 1 if api_key is True else api_key.staff.id
        session().add(NfcTag(uid=uid, customer_number=customer_number, enrolled_by_id=enrolled_by))
        synced.append({"uid": uid, "customer_number": customer_number})

    await session().commit()
    return {"synced": len(synced), "total": len(enrollments), "results": synced, "errors": errors}


@router.post("/readings/sync")
async def mobile_readings_sync(
    payload: MobileSyncPayload,
    api_key: ApiKey = Depends(require_staff("can_read_meters")),
):
    """Bulk reading upload from the phone. Delegates to the same service the
    portal and the single-upload route use, so duplicate-month handling, billing
    creation and the audit log are identical."""
    from reading_service import sync_readings

    readings = payload.readings
    if readings is None:
        return JSONResponse({"error": "readings field is required"}, status_code=400)

    if api_key is True:
        token_result = await session().execute(
            select(ApiKey).where(ApiKey.is_active.is_(True)).limit(1)
        )
        token = token_result.scalar_one_or_none()
        token_id = token.id if token else None
        staff_id, staff_name = 1, "superuser"
    else:
        token_id = api_key.id
        staff_id = api_key.staff.id if api_key.staff else None
        staff_name = api_key.staff.name if api_key.staff else None

    synced, results, errors = await _run_sync(
        sync_readings, readings, token_id, staff_id, staff_name
    )
    return {"synced": synced, "total": len(readings), "results": results, "errors": errors}


@router.get("/readings/bulk")
async def mobile_readings_bulk(
    request: Request,
    api_key: ApiKey = Depends(require_staff("can_read_meters")),
):
    """Customer profiles plus their recent readings, keyed by customer number.
    This is the app's main pull: it asks for every changed customer in batches
    of 500."""
    raw = request.query_params.get("customer_numbers", "").strip()
    if not raw:
        return JSONResponse(
            {"error": "customer_numbers parameter is required"}, status_code=400
        )
    try:
        limit = int(request.query_params.get("limit", "0"))
    except (TypeError, ValueError):
        limit = 0

    numbers: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            numbers.append(int(part))
        except ValueError:
            continue
    if not numbers:
        return JSONResponse({"error": "No valid customer numbers"}, status_code=400)

    customers_result = await session().execute(
        select(Customer).where(Customer.customer_number.in_(numbers))
    )
    customers = customers_result.scalars().all()

    nfc_result = await session().execute(
        select(NfcTag.customer_number, NfcTag.uid).where(NfcTag.customer_number.in_(numbers))
    )
    nfc_map = {row[0]: row[1] for row in nfc_result.all()}

    data: dict[str, dict] = {}
    for customer in customers:
        readings_query = (
            select(MeterReading)
            .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
            .where(MeterReading.customer_number == customer.customer_number)
            .order_by(desc(MeterReading.timestamp))
        )
        if limit > 0:
            readings_query = readings_query.limit(limit)
        readings_result = await session().execute(readings_query)
        readings = readings_result.scalars().unique().all()

        data[str(customer.customer_number)] = {
            "customer": {
                "customer_number": customer.customer_number,
                "name": customer.name,
                "address": customer.address,
                "contact_number": customer.contact_number,
                "phase": customer.phase,
                "block": customer.block,
                "street": customer.street,
                "x_coordinate": customer.x_coordinate,
                "y_coordinate": customer.y_coordinate,
                "nfc_uid": nfc_map.get(customer.customer_number),
            },
            "readings": [
                {
                    "id": reading.id,
                    "reading_value": float(reading.reading_value),
                    "reader": (
                        reading.token.staff.name
                        if reading.token and reading.token.staff
                        else None
                    ),
                    "timestamp": int(reading.timestamp.timestamp()),
                }
                for reading in readings
            ],
        }

    return {"customers": data}
