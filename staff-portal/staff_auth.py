from __future__ import annotations

from contextvars import ContextVar
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from shared.auth import MAX_AGE, load_token, make_token

COOKIE_NAME = 'session'

_current_staff: ContextVar[dict | None] = ContextVar('current_staff', default=None)


class _Anonymous:
    is_authenticated = False
    is_anonymous = True
    id = None
    username = None
    name = None
    email = None
    contact_number = None
    can_read_meters = False
    can_accept_payment = False
    can_enroll_customer = False
    can_drop_reading = False
    can_drop_payment = False
    can_enroll_staff = False
    can_manage_billing = False


class _StaffProxy:
    """Lazy proxy: templates use `current_user.<attr>`; resolves against the
    per-request staff payload or an anonymous stub."""

    def __getattr__(self, name):
        staff = _current_staff.get()
        if staff is None:
            return getattr(_Anonymous(), name)
        if name == 'is_authenticated':
            return True
        if name == 'is_anonymous':
            return False
        return staff.get(name)


current_user = _StaffProxy()


def set_staff(request: Request) -> None:
    payload = load_token(request.cookies.get(COOKIE_NAME))
    if payload and payload.get('id'):
        _current_staff.set(payload)


def clear_staff() -> None:
    _current_staff.set(None)


def staff_payload() -> dict | None:
    return _current_staff.get()


def login_cookie(staff: dict) -> str:
    return make_token(staff)


def logout_response() -> RedirectResponse:
    resp = RedirectResponse('/staff/login', status_code=302)
    resp.headers['Cache-Control'] = 'no-store'
    resp.delete_cookie(COOKIE_NAME, path='/')
    return resp


async def require_login(request: Request):
    if not _current_staff.get():
        return RedirectResponse('/staff/login', status_code=302)
    return None


def require_perms(*perms: str):
    async def _dep(request: Request):
        staff = _current_staff.get()
        if staff is None:
            return RedirectResponse('/staff/login', status_code=302)
        for perm in perms:
            if not staff.get(perm, False):
                return JSONResponse({'error': 'Unauthorized'}, status_code=403)
        return None

    return _dep
