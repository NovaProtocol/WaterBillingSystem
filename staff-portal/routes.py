import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import HTTPException

import api_client
import staff_auth
from templating import templates
from shared.security import RateLimiter

logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')
logger = logging.getLogger('staff-portal')

router = APIRouter()

login_limiter = RateLimiter(limit=10, window=60.0)


def _set_endpoint(request: Request) -> None:
    route = request.scope.get('route')
    request.endpoint = route.name if route and getattr(route, 'name', None) else ''


def require_login(request: Request):
    _set_endpoint(request)
    if not staff_auth.staff_payload():
        raise HTTPException(status_code=302, headers={'Location': '/staff/login'})


def require_perms(*perms: str):
    def _dep(request: Request):
        _set_endpoint(request)
        staff = staff_auth.staff_payload()
        if staff is None:
            raise HTTPException(status_code=302, headers={'Location': '/staff/login'})
        for perm in perms:
            if not staff.get(perm, False):
                raise HTTPException(status_code=403, detail='Unauthorized')
    return _dep


@router.get('/staff/')
async def index(request: Request):
    if staff_auth.staff_payload():
        return RedirectResponse('/staff/dashboard', status_code=302)
    return RedirectResponse('/staff/login', status_code=302)


@router.get('/staff/login')
async def login_page(request: Request):
    if staff_auth.staff_payload():
        return RedirectResponse('/staff/dashboard', status_code=302)
    return templates.TemplateResponse(request, 'staff/login.html', {'error': None, 'username': ''})


@router.post('/staff/login')
async def login_submit(request: Request):
    if staff_auth.staff_payload():
        return RedirectResponse('/staff/dashboard', status_code=302)

    form = await request.form()
    username = str(form.get('username', '') or '')
    password = str(form.get('password', '') or '')

    forwarded = request.headers.get('X-Forwarded-For', '')
    ip = forwarded.split(',')[0].strip() or (request.client.host if request.client else 'unknown')
    if not login_limiter.allow(ip):
        return templates.TemplateResponse(
            request, 'staff/login.html',
            {'error': 'Too many attempts. Try again later.', 'username': username},
        )

    try:
        result = await api_client.staff_login(username, password)
        if result.get('success'):
            staff_data = result['staff']
            resp = RedirectResponse('/staff/dashboard', status_code=302)
            resp.set_cookie(
                staff_auth.COOKIE_NAME,
                staff_auth.login_cookie(staff_data),
                max_age=staff_auth.MAX_AGE,
                httponly=True,
                samesite='Lax',
                path='/',
            )
            login_limiter.reset(ip)
            return resp
    except Exception as e:
        logger.error(f"Login failed: {e}", exc_info=True)
    return templates.TemplateResponse(
        request, 'staff/login.html',
        {'error': 'Invalid credentials', 'username': username},
    )


@router.get('/staff/logout')
async def logout():
    return staff_auth.logout_response()


@router.get('/staff/dashboard')
async def dashboard(request: Request, _=Depends(require_login)):
    data = await api_client.get_dashboard_data()
    return templates.TemplateResponse(request, 'staff/dashboard.html', {'data': data})


@router.get('/staff/customer-lookup')
async def customer_lookup(request: Request, _=Depends(require_login)):
    q = request.query_params.get('q', '')
    try:
        result = await api_client.customer_search(q)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Customer lookup failed: {e}")
        return JSONResponse({'customers': [], 'error': str(e)})


@router.get('/staff/api/customer/{customer_number}')
async def proxy_customer(customer_number: int, request: Request, _=Depends(require_login)):
    """Proxy: browser calls this instead of calling the API directly."""
    try:
        params = {k: v for k, v in request.query_params.items() if k != 'customer_number'}
        result = await api_client.get_customer(customer_number, params)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Customer proxy failed: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get('/staff/api/customers/search-sort')
async def api_customers_search_sort(request: Request, _=Depends(require_login)):
    q = request.query_params.get('q', '')
    sort_by = request.query_params.get('sort_by', 'customer_number')
    sort_dir = request.query_params.get('sort_dir', 'asc')
    try:
        page = int(request.query_params.get('page', '1'))
    except (ValueError, TypeError):
        page = 1
    try:
        size = int(request.query_params.get('size', '50'))
    except (ValueError, TypeError):
        size = 50
    return JSONResponse(await api_client.customer_search_sort(q, sort_by, sort_dir, page, size))


@router.get('/staff/customers')
async def customers(request: Request, _=Depends(require_login)):
    try:
        page = int(request.query_params.get('page', '1'))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = int(request.query_params.get('per_page', '50'))
    except (ValueError, TypeError):
        per_page = 50
    result = await api_client.get_customers(page, per_page)
    return templates.TemplateResponse(request, 'staff/customers.html', result)


@router.post('/staff/customers/create')
async def customer_create(request: Request, _=Depends(require_perms('can_enroll_customer'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.create_customer(data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Create customer failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/manage-customers')
async def manage_customers(request: Request, _=Depends(require_login)):
    return templates.TemplateResponse(request, 'staff/manage_customers.html', {})


@router.post('/staff/manage-customers/{customer_id}/edit')
async def edit_customer(customer_id: int, request: Request, _=Depends(require_perms('can_enroll_customer'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.edit_customer(customer_id, data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Edit customer {customer_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post('/staff/manage-customers/{customer_id}/toggle-active')
async def toggle_customer_active(customer_id: int, _=Depends(require_perms('can_enroll_customer'))):
    try:
        result = await api_client.toggle_customer_active(customer_id)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Toggle customer {customer_id} active failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post('/staff/manage-customers/{customer_id}/clear-nfc')
async def clear_customer_nfc(customer_id: int, _=Depends(require_perms('can_enroll_customer'))):
    try:
        result = await api_client.clear_customer_nfc(customer_id)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Clear NFC for customer {customer_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/meter-reading')
async def meter_reading(request: Request, _=Depends(require_login)):
    staff_id = staff_auth.staff_payload().get('id', 1)
    keys_result = await api_client.list_api_keys(staff_id)
    keys = keys_result.get('keys', [])
    return templates.TemplateResponse(request, 'staff/meter_reading.html', {'keys': keys})


@router.post('/staff/meter-reading/generate')
async def generate_api_key(request: Request, _=Depends(require_login)):
    staff_id = staff_auth.staff_payload().get('id', 1)
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.generate_api_key(staff_id, data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Generate API key failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post('/staff/meter-reading/revoke/{key_id}')
async def revoke_api_key(key_id: int, _=Depends(require_login)):
    staff_id = staff_auth.staff_payload().get('id', 1)
    try:
        result = await api_client.revoke_api_key(staff_id, key_id)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Revoke API key {key_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/manage-reading')
async def manage_reading(request: Request, _=Depends(require_login)):
    staff_id = staff_auth.staff_payload().get('id', 1)
    result = await api_client.get_reading_logs(staff_id)
    return templates.TemplateResponse(request, 'staff/manage_reading.html', result)


@router.post('/staff/manage-reading/drop-reading/{reading_id}')
async def drop_reading(reading_id: int, request: Request, _=Depends(require_perms('can_drop_reading'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.drop_reading(reading_id, data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Drop reading {reading_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post('/staff/manage-reading/edit-reading/{reading_id}')
async def edit_reading(reading_id: int, request: Request, _=Depends(require_perms('can_drop_reading'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.edit_reading(reading_id, data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Edit reading {reading_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/payments')
async def payments(request: Request, _=Depends(require_login)):
    return templates.TemplateResponse(request, 'staff/payments.html', {})


@router.post('/staff/payments/submit')
async def submit_payment(request: Request, _=Depends(require_perms('can_accept_payment'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.submit_payment(data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Submit payment failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/cashier-tally')
async def cashier_tally(request: Request, _=Depends(require_perms('can_accept_payment'))):
    period = request.query_params.get('period', 'daily')
    date = request.query_params.get('date', '')
    start_date = request.query_params.get('start_date', '')
    end_date = request.query_params.get('end_date', '')
    try:
        group_days = int(request.query_params.get('group_days', '1'))
    except (ValueError, TypeError):
        group_days = 1
    data = await api_client.get_cashier_tally(period, 0, date, start_date, end_date, group_days)
    return templates.TemplateResponse(request, 'staff/cashier_tally.html', data)


@router.get('/staff/manage-billing')
async def manage_billing(request: Request, _=Depends(require_login)):
    return templates.TemplateResponse(request, 'staff/manage_billing.html', {})


@router.post('/staff/manage-billing/undo-payment/{payment_id}')
async def undo_payment(payment_id: int, request: Request, _=Depends(require_perms('can_drop_payment'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.undo_payment(payment_id, (data or {}).get('reason', ''))
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Undo payment {payment_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/staff')
async def staff_list(request: Request, _=Depends(require_login)):
    result = await api_client.list_staff()
    return templates.TemplateResponse(request, 'staff/staff_list.html', result)


@router.post('/staff/staff/create')
async def staff_create(request: Request, _=Depends(require_perms('can_enroll_staff'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.create_staff(data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Staff create failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get('/staff/staff/{staff_id}')
async def staff_get(staff_id: int, _=Depends(require_perms('can_enroll_staff'))):
    try:
        result = await api_client.get_staff(staff_id)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Staff get {staff_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post('/staff/staff/{staff_id}')
async def staff_edit(staff_id: int, request: Request, _=Depends(require_perms('can_enroll_staff'))):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = await api_client.edit_staff(staff_id, data or {})
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Staff edit {staff_id} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)
