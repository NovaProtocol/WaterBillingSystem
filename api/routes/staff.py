from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import joinedload, selectinload

from fastapi import APIRouter

router = APIRouter(prefix="/api")
from db_async import session, sync_session
from models import ApiKey, Billing, ManagementLog, Staff
from services.payment_service import (
    compute_cashier_tally,
    compute_nav_dates,
    parse_date_range,
)
from utils import get_staff_id, require_staff, resolve_api_key

from shared.passwords import hash_password, verify_password


def _staff_to_dict(staff: Staff) -> dict:
    return {
        "id": staff.id,
        "username": staff.username,
        "name": staff.name,
        "email": staff.email,
        "contact_number": staff.contact_number,
        "is_active": staff.is_active,
        "can_read_meters": staff.can_read_meters,
        "can_accept_payment": staff.can_accept_payment,
        "can_enroll_customer": staff.can_enroll_customer,
        "can_drop_reading": staff.can_drop_reading,
        "can_drop_payment": staff.can_drop_payment,
        "can_enroll_staff": staff.can_enroll_staff,
        "can_manage_billing": staff.can_manage_billing,
    }


@router.post("/staff/login")
async def staff_login(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    username = str(data.get("username", "") or "").strip()
    password = str(data.get("password", "") or "")
    if not username or not password:
        return JSONResponse({"error": "Username and password required"}, status_code=400)
    result = await session().execute(
        select(Staff).where(Staff.username == username)
    )
    staff = result.scalar_one_or_none()
    if not staff or not staff.is_active:
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    if not verify_password(staff.password, password):
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    return _staff_to_dict(staff)


@router.get("/staff/info")
async def staff_info(request: Request):
    api_key = await require_staff()(request)

    if api_key is True:
        staff_id = await get_staff_id(request)
        if not staff_id:
            return JSONResponse({"error": "staff_id required via X-Staff-ID header or request body"}, status_code=400)
        staff = await session().get(Staff, staff_id)
        if not staff:
            return JSONResponse({"error": "Staff not found"}, status_code=404)
    else:
        staff = api_key.staff
        if not staff:
            return JSONResponse({"error": "Staff not found"}, status_code=404)

    return {
        "staff": _staff_to_dict(staff),
        "auth_type": "internal_key" if api_key is True else "api_key",
        "api_key": {
            "id": api_key.id,
            "label": api_key.label,
            "is_active": api_key.is_active,
        } if api_key is not True else None,
    }


@router.get("/staff/all")
async def staff_all(api_key: ApiKey = Depends(require_staff("can_enroll_staff"))):
    result = await session().execute(select(Staff))
    staff_list = result.scalars().all()
    return {"staff": [_staff_to_dict(s) for s in staff_list]}


@router.get("/staff/{staff_id}")
async def staff_get(staff_id: int, api_key: ApiKey = Depends(require_staff("can_enroll_staff"))):
    staff = await session().get(Staff, staff_id)
    if not staff:
        return JSONResponse({"error": "Staff not found"}, status_code=404)
    return _staff_to_dict(staff)


@router.post("/staff/new")
async def staff_new(request: Request, api_key: ApiKey = Depends(require_staff("can_enroll_staff"))):
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    username = str(data.get("username", "") or "").strip()
    password = str(data.get("password", "") or "")
    if not username or not password:
        return JSONResponse({"error": "Username and password are required"}, status_code=400)
    result = await session().execute(select(Staff).where(Staff.username == username))
    if result.scalar_one_or_none():
        return JSONResponse({"error": "Username already exists"}, status_code=409)
    staff = Staff(
        username=username,
        name=str(data.get("name", "") or "").strip() or username,
        password=hash_password(password),
        email=str(data.get("email", "") or "").strip() or None,
        contact_number=str(data.get("contact_number", "") or "").strip() or None,
        can_read_meters=bool(data.get("can_read_meters", False)),
        can_accept_payment=bool(data.get("can_accept_payment", False)),
        can_enroll_customer=bool(data.get("can_enroll_customer", False)),
        can_drop_reading=bool(data.get("can_drop_reading", False)),
        can_drop_payment=bool(data.get("can_drop_payment", False)),
        can_enroll_staff=bool(data.get("can_enroll_staff", False)),
        can_manage_billing=bool(data.get("can_manage_billing", False)),
    )
    session().add(staff)
    await session().commit()
    return JSONResponse({"message": "Staff created", "username": staff.username, "name": staff.name}, status_code=201)


@router.post("/staff/{staff_id}/edit")
async def staff_edit(staff_id: int, request: Request, api_key: ApiKey = Depends(require_staff("can_enroll_staff"))):
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    staff = await session().get(Staff, staff_id)
    if not staff:
        return JSONResponse({"error": "Staff not found"}, status_code=404)
    username = str(data.get("username", "") or "").strip()
    if not username:
        return JSONResponse({"error": "Username is required"}, status_code=400)
    result = await session().execute(
        select(Staff).where(Staff.username == username, Staff.id != staff_id)
    )
    if result.scalar_one_or_none():
        return JSONResponse({"error": "Username already exists"}, status_code=409)
    staff.username = username
    staff.name = str(data.get("name", "") or "").strip() or username
    password = data.get("password", "")
    if password:
        staff.password = hash_password(str(password))
    staff.email = str(data.get("email", "") or "").strip() or None
    staff.contact_number = str(data.get("contact_number", "") or "").strip() or None
    staff.can_read_meters = bool(data.get("can_read_meters", False))
    staff.can_accept_payment = bool(data.get("can_accept_payment", False))
    staff.can_enroll_customer = bool(data.get("can_enroll_customer", False))
    staff.can_drop_reading = bool(data.get("can_drop_reading", False))
    staff.can_drop_payment = bool(data.get("can_drop_payment", False))
    staff.can_enroll_staff = bool(data.get("can_enroll_staff", False))
    staff.can_manage_billing = bool(data.get("can_manage_billing", False))
    staff.is_active = bool(data.get("is_active", True))
    await session().commit()
    return {"message": "Staff updated", "username": staff.username, "name": staff.name}


@router.get("/staff/{staff_id}/cashier-tally")
async def staff_cashier_tally(staff_id: int, request: Request, api_key: ApiKey = Depends(require_staff("can_accept_payment"))):
    period = request.query_params.get("period", "daily")
    today = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    start_str = request.query_params.get("start_date") or request.query_params.get("date")
    end_str = request.query_params.get("end_date")
    try:
        group_days = int(request.query_params.get("group_days", "1"))
    except (ValueError, TypeError):
        group_days = 1
    try:
        cashier_filter = int(request.query_params.get("cashier_id")) if request.query_params.get("cashier_id") else None
    except (ValueError, TypeError):
        cashier_filter = None
    start, end = parse_date_range(period, start_str, end_str, today)

    def _tally():
        s = sync_session()
        try:
            return compute_cashier_tally(start, end, cashier_filter, group_days, session=s)
        finally:
            s.close()

    tally, use_matrix = await run_in_threadpool(_tally)
    nav = compute_nav_dates(period, start, end, today)
    return {
        "tally": tally,
        "use_matrix": use_matrix,
        "nav_date": nav.get("nav_date"),
        "group_days": group_days,
        "start_date": start.strftime("%Y-%m-%d") if start else "",
        "end_date": end.strftime("%Y-%m-%d") if end else "",
        "display": nav["display"],
        "prev_date": nav["prev_date"],
        "next_date": nav["next_date"],
        "is_today": nav["is_today"],
        "period": period,
    }


@router.get("/staff/{staff_id}/reading-logs")
async def staff_reading_logs(staff_id: int, api_key: ApiKey = Depends(require_staff("can_drop_reading"))):
    result = await session().execute(
        select(ManagementLog)
        .options(selectinload(ManagementLog.staff))
        .where(ManagementLog.target_type == "reading")
        .order_by(desc(ManagementLog.timestamp))
        .limit(50)
    )
    logs = result.scalars().all()
    return {
        "logs": [
            {
                "id": log.id,
                "staff_id": log.staff_id,
                "staff_name": log.staff.name if log.staff else None,
                "action_type": log.action_type,
                "target_id": log.target_id,
                "customer_number": log.customer_number,
                "details": log.details,
                "timestamp": int(log.timestamp.timestamp()) if log.timestamp else 0,
            }
            for log in logs
        ]
    }


async def _can_manage_keys(staff_id: int, api_key: ApiKey | bool) -> None:
    """Self-service for the key owner; can_enroll_staff for everyone else."""
    if api_key is True:  # internal key — master access
        return
    if api_key.staff_id == staff_id or api_key.staff.can_enroll_staff:
        return
    raise HTTPException(status_code=403, detail={"error": "Permission denied"})


@router.get("/staff/{staff_id}/api-keys")
async def staff_api_keys(staff_id: int, api_key: ApiKey = Depends(require_staff())):
    await _can_manage_keys(staff_id, api_key)
    result = await session().execute(
        select(ApiKey)
        .options(joinedload(ApiKey.staff))
        .where(ApiKey.staff_id == staff_id)
        .order_by(desc(ApiKey.date_created))
    )
    keys = result.scalars().all()
    return {
        "keys": [
            {
                "id": k.id,
                "key": k.key,
                "label": k.label,
                "is_active": k.is_active,
                "staff_id": k.staff_id,
                "staff_name": k.staff.name if k.staff else None,
                "staff": {
                    "name": k.staff.name,
                    "username": k.staff.username,
                } if k.staff else None,
                "date_created": k.date_created.isoformat() if k.date_created else None,
            }
            for k in keys
        ]
    }


@router.post("/staff/{staff_id}/api-key/generate")
async def staff_api_key_generate(staff_id: int, request: Request, api_key: ApiKey = Depends(require_staff())):
    await _can_manage_keys(staff_id, api_key)
    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    label = str(data.get("label", "") or "").strip() or None
    staff = await session().get(Staff, staff_id)
    if not staff:
        return JSONResponse({"error": "Staff not found"}, status_code=404)
    key = "CRDC-" + secrets.token_hex(16).upper()
    new_key = ApiKey(key=key, label=label, staff_id=staff_id)
    session().add(new_key)
    await session().commit()
    return JSONResponse({"key": key, "label": label, "id": new_key.id}, status_code=201)


@router.post("/staff/{staff_id}/api-key/{key_id}/revoke")
async def staff_api_key_revoke(staff_id: int, key_id: int, api_key: ApiKey = Depends(require_staff())):
    await _can_manage_keys(staff_id, api_key)
    target = await session().get(ApiKey, key_id)
    if not target:
        return JSONResponse({"error": "Key not found"}, status_code=404)
    target.is_active = False
    await session().commit()
    return {"message": "Key revoked"}


@router.post("/staff/{staff_id}/api-key/verify")
async def staff_api_key_verify(staff_id: int, request: Request):
    api_key = await resolve_api_key(request)
    if not api_key:
        return JSONResponse({"error": "Authentication required"}, status_code=401)

    data = await request.json()
    if not isinstance(data, dict):
        data = {}
    verify_key = str(data.get("api_key", "") or "").strip()
    if not verify_key:
        return JSONResponse({"error": "api_key is required"}, status_code=400)

    result = await session().execute(
        select(ApiKey)
        .options(selectinload(ApiKey.staff))
        .where(ApiKey.key == verify_key, ApiKey.is_active.is_(True))
    )
    target = result.scalar_one_or_none()
    if not target:
        return JSONResponse({"error": "Invalid or revoked API key"}, status_code=404)

    staff = target.staff
    return {
        "valid": True,
        "api_key": {
            "id": target.id,
            "label": target.label,
            "staff_id": target.staff_id,
            "is_active": target.is_active,
        },
        "staff": {
            "id": staff.id,
            "username": staff.username,
            "name": staff.name,
            "can_read_meters": staff.can_read_meters,
            "can_accept_payment": staff.can_accept_payment,
            "can_enroll_customer": staff.can_enroll_customer,
            "can_drop_reading": staff.can_drop_reading,
            "can_drop_payment": staff.can_drop_payment,
            "can_enroll_staff": staff.can_enroll_staff,
            "can_manage_billing": staff.can_manage_billing,
        } if staff else None,
    }
