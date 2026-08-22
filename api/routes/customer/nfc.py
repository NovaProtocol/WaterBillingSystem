from __future__ import annotations

from datetime import datetime, timezone

from db_async import session
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from models import ApiKey, Config, Customer, NfcTag
from pydantic import BaseModel
from sqlalchemy import desc, select
from utils import get_staff_id, require_staff

router = APIRouter()


class NfcCreatePayload(BaseModel):
    uid: str = ""


@router.get("/customer/{customer_number}/nfc")
async def customer_nfc(
    customer_number: int, api_key: ApiKey = Depends(require_staff("can_read_meters"))
):
    result = await session().execute(
        select(NfcTag).where(NfcTag.customer_number == customer_number)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        return {"nfc_uid": None}

    return {
        "nfc_uid": tag.uid,
        "customer_number": tag.customer_number,
    }


@router.get("/customer/all/nfc")
async def customer_all_nfc(api_key: ApiKey = Depends(require_staff("can_read_meters"))):
    result = await session().execute(select(NfcTag).order_by(desc(NfcTag.date_created)))
    tags = result.scalars().all()
    return {"tags": [{"uid": t.uid, "customer_number": t.customer_number} for t in tags]}


@router.post("/customer/{customer_number}/nfc/create", status_code=201)
async def customer_nfc_create(
    customer_number: int,
    payload: NfcCreatePayload,
    request: Request,
    api_key: ApiKey = Depends(require_staff("can_enroll_customer")),
):
    uid = str(payload.uid or "").strip()
    if not uid:
        return JSONResponse({"error": "uid is required"}, status_code=400)

    existing_result = await session().execute(select(NfcTag).where(NfcTag.uid == uid))
    if existing_result.scalar_one_or_none():
        return JSONResponse({"error": "Tag UID already assigned"}, status_code=409)

    customer_result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        return JSONResponse({"error": "Customer not found"}, status_code=404)

    if api_key is True:
        enrolled_by = await get_staff_id(request) or 1
    else:
        enrolled_by = api_key.staff.id

    tag = NfcTag(uid=uid, customer_number=customer_number, enrolled_by_id=enrolled_by)
    session().add(tag)
    customer.date_modified = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    await session().commit()

    return {"message": "Tag assigned", "uid": uid, "customer_number": customer_number}


@router.post("/customer/{customer_number}/nfc/delete")
async def customer_nfc_delete(
    customer_number: int,
    api_key: ApiKey = Depends(require_staff("can_enroll_customer")),
):
    tag_result = await session().execute(
        select(NfcTag).where(NfcTag.customer_number == customer_number)
    )
    tag = tag_result.scalar_one_or_none()
    if not tag:
        return JSONResponse({"error": "No NFC tag assigned to this customer"}, status_code=404)

    customer_result = await session().execute(
        select(Customer).where(Customer.customer_number == customer_number)
    )
    customer = customer_result.scalar_one_or_none()
    await session().delete(tag)

    gen_result = await session().execute(select(Config).where(Config.key == "nfc_generation"))
    gen_row = gen_result.scalar_one_or_none()
    if gen_row:
        gen_row.value = str(int(gen_row.value) + 1)
    else:
        session().add(Config(key="nfc_generation", value="1"))

    if customer:
        customer.date_modified = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    await session().commit()

    return {"message": "Tag deleted", "uid": tag.uid}
