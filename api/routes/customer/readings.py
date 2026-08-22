from __future__ import annotations

from datetime import datetime, timezone

from db_async import session
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from models import ApiKey, MeterReading
from pydantic import BaseModel
from reading_service import (
    drop_reading as service_drop_reading,
)
from reading_service import (
    edit_reading as service_edit_reading,
)
from reading_service import (
    upload_reading as service_upload_reading,
)
from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload
from utils import require_staff

from routes.customer.common import _run_sync

router = APIRouter()


class ReadingNewPayload(BaseModel):
    reading_value: float | None = None
    timestamp: float | None = None
    staff_id: int | None = None
    staff_name: str | None = None


class ReadingDropPayload(BaseModel):
    reading_id: int | None = None
    reason: str = ""
    staff_id: int | None = None


class ReadingEditPayload(BaseModel):
    reading_id: int | None = None
    reading_value: float = 0
    staff_id: int | None = None


@router.get("/customer/{customer_number}/reading")
async def customer_readings(
    customer_number: int,
    request: Request,
    api_key: ApiKey = Depends(require_staff("can_read_meters")),
):
    try:
        page = int(request.query_params.get("page", "1"))
    except (ValueError, TypeError):
        page = 1
    try:
        size = int(request.query_params.get("size", "50"))
    except (ValueError, TypeError):
        size = 50

    count_result = await session().execute(
        select(func.count())
        .select_from(MeterReading)
        .where(MeterReading.customer_number == customer_number)
    )
    total = count_result.scalar() or 0

    result = await session().execute(
        select(MeterReading)
        .options(joinedload(MeterReading.token).joinedload(ApiKey.staff))
        .where(MeterReading.customer_number == customer_number)
        .order_by(desc(MeterReading.timestamp))
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        {
            "id": r.id,
            "reading_value": float(r.reading_value),
            "reader": r.token.staff.name if r.token and r.token.staff else None,
            "timestamp": int(r.timestamp.timestamp()),
        }
        for r in result.scalars().unique().all()
    ]
    pages = max(1, (total + size - 1) // size) if size else 1
    return {
        "data": items,
        "meta": {
            "current_page": page,
            "page_size": size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@router.post("/customer/{customer_number}/reading/new", status_code=201)
async def customer_reading_new(
    customer_number: int,
    payload: ReadingNewPayload,
    api_key: ApiKey = Depends(require_staff("can_read_meters")),
):
    reading_value = payload.reading_value
    timestamp = (
        payload.timestamp
        if payload.timestamp is not None
        else datetime.now(tz=timezone.utc).replace(tzinfo=None).timestamp()
    )
    staff_id = payload.staff_id if api_key is True else api_key.staff.id
    staff_name = payload.staff_name if api_key is True else api_key.staff.name

    if reading_value is None:
        return JSONResponse({"error": "reading_value is required"}, status_code=400)

    try:
        reading_float = float(reading_value)
        ts_float = float(timestamp)
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid reading_value or timestamp"}, status_code=400)

    if api_key is True:
        token_result = await session().execute(
            select(ApiKey).where(ApiKey.is_active.is_(True)).limit(1)
        )
        token = token_result.scalar_one_or_none()
        token_id = token.id if token else None
    else:
        token_id = api_key.id
    reading, error, status = await _run_sync(
        service_upload_reading,
        customer_number,
        reading_float,
        ts_float,
        token_id,
        staff_id,
        staff_name,
    )
    if error:
        return JSONResponse({"error": error}, status_code=status)

    return {
        "success": True,
        "reading_id": reading.id,
        "customer_number": customer_number,
        "reading_value": float(reading_value),
        "timestamp": int(timestamp),
        "reader": staff_name,
    }


@router.post("/customer/{customer_number}/reading/drop")
async def customer_reading_drop(
    customer_number: int,
    payload: ReadingDropPayload,
    api_key: ApiKey = Depends(require_staff("can_drop_reading")),
):
    reading_id = payload.reading_id
    reason = str(payload.reason or "").strip()
    staff_id = payload.staff_id if api_key is True else api_key.staff.id
    if not reading_id:
        return JSONResponse({"error": "reading_id is required"}, status_code=400)
    if not reason:
        return JSONResponse({"error": "Reason is required"}, status_code=400)
    try:
        await _run_sync(service_drop_reading, reading_id, staff_id, reason)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    return {"message": "Reading dropped"}


@router.post("/customer/{customer_number}/reading/edit")
async def customer_reading_edit(
    customer_number: int,
    payload: ReadingEditPayload,
    api_key: ApiKey = Depends(require_staff("can_manage_billing")),
):
    reading_id = payload.reading_id
    try:
        new_value = float(payload.reading_value)
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid reading value"}, status_code=400)
    if not reading_id:
        return JSONResponse({"error": "reading_id is required"}, status_code=400)
    staff_id = payload.staff_id if api_key is True else api_key.staff.id
    await _run_sync(service_edit_reading, reading_id, new_value, staff_id)
    return {"message": "Reading updated"}
