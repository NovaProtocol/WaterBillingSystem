import logging
import random

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from shared.auth import MAX_AGE, load_token, make_token

import api_client
from templating import templates

logger = logging.getLogger('developer-portal')

router = APIRouter(prefix='/developer')

COOKIE_NAME = 'session'


def _set_endpoint(request: Request) -> None:
    route = request.scope.get('route')
    request.endpoint = route.name if route and getattr(route, 'name', None) else ''


def require_superuser(request: Request):
    _set_endpoint(request)
    payload = load_token(request.cookies.get(COOKIE_NAME))
    if not payload or payload.get('username') != 'superuser':
        raise HTTPException(status_code=302, headers={'Location': '/staff/login'})
    request.state.dev_payload = payload


def _resign_cookie(payload: dict):
    return make_token(payload)


async def _confirm_check(request: Request) -> tuple[bool, dict | None]:
    """Validate + consume the one-time confirm code stored in the signed
    session cookie payload. Returns (ok, new_payload_to_resign)."""
    payload = getattr(request.state, 'dev_payload', None)
    if not payload:
        return False, None
    code = None
    try:
        form = await request.form()
    except Exception:
        form = {}
    code = str(form.get('confirm_code', '') or '').strip()
    expected = payload.pop('debug_confirm', None)
    if not expected or code != expected:
        return False, payload
    return True, payload


def _generate_and_store_code(request: Request) -> str:
    code = str(random.randint(10_000_000, 99_999_999))
    payload = getattr(request.state, 'dev_payload', None) or {}
    payload['debug_confirm'] = code
    return code


def _with_confirm_cookie(resp, payload: dict | None):
    if payload is not None:
        resp.set_cookie(COOKIE_NAME, _resign_cookie(payload), max_age=MAX_AGE,
                        httponly=True, samesite='Lax', path='/')
    return resp


# --- Page routes ---

@router.get('/')
async def index(request: Request, _=Depends(require_superuser)):
    return RedirectResponse('/developer/backup', status_code=302)


@router.get('/backup')
async def backup(request: Request, _=Depends(require_superuser)):
    try:
        backup_files = (await api_client.list_backups()).get('backups', [])
    except Exception as e:
        logger.exception(f"List backups failed:")
        backup_files = []
    return templates.TemplateResponse(request, 'dev/backup.html', {'backup_files': backup_files})


@router.get('/seed')
async def seed(request: Request, _=Depends(require_superuser)):
    return templates.TemplateResponse(request, 'dev/seed.html', {})


@router.get('/clear')
async def clear(request: Request, _=Depends(require_superuser)):
    try:
        stats = await api_client.get_stats()
    except Exception as e:
        logger.exception(f"Get stats failed:")
        stats = {}
    return templates.TemplateResponse(request, 'dev/clear.html', {'stats': stats})


@router.get('/history')
async def task_logs(request: Request, _=Depends(require_superuser)):
    return templates.TemplateResponse(request, 'dev/tasks.html', {})


# --- API routes ---

@router.get('/auth')
async def auth(request: Request, _=Depends(require_superuser)):
    return {"authenticated": True, "superuser": True}


@router.post('/confirm')
async def confirm(request: Request, _=Depends(require_superuser)):
    code = _generate_and_store_code(request)
    payload = getattr(request.state, 'dev_payload', None)
    resp = JSONResponse({"code": code})
    return _with_confirm_cookie(resp, payload)


@router.post('/backup')
async def create_backup(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.create_backup()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Backup creation failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get('/backups')
async def list_backups(request: Request, _=Depends(require_superuser)):
    try:
        result = await api_client.list_backups()
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"List backups failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/restore')
async def restore_backup(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    form = {}
    try:
        form = await request.form()
    except Exception:
        pass
    filename = str(form.get('filename', '') or '').strip()
    if not filename:
        return JSONResponse({"error": "No backup file specified"}, status_code=400)
    try:
        result = await api_client.restore_backup(filename)
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Restore backup failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/restore-newest')
async def restore_newest(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.restore_newest()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Restore newest failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/clear')
async def clear_database(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.clear_database()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Clear database failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/seed')
async def seed_data(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        form = await request.form()
        customers = int(form.get("customers", "0"))
        months = int(form.get("months", "0"))
    except (ValueError, TypeError):
        logger.exception("Seed data validation failed:")
        return JSONResponse({"error": "Invalid customer count or months"}, status_code=400)
    if customers < 1 or months < 2 or customers * months > 10_000_000:
        return JSONResponse({"error": "Invalid range: customers × months must be between 1×2 and 10M entries"}, status_code=400)
    try:
        form = await request.form()
        result = await api_client.seed_data(
            customers=customers, months=months,
            cashiers=int(form.get("cashiers", 2)),
            readers=int(form.get("readers", 2)),
            read_current=form.get("read_current", "no"),
            pay_last=form.get("pay_last", "random"),
            randomize_months=form.get("randomize_months", "yes"),
            allow_deactivation=form.get("allow_deactivation", "no"),
        )
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Seed data failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/read-month')
async def read_this_month(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.read_all_this_month()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Read this month failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/unread-month')
async def unread_this_month(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.unread_this_month()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Unread this month failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/pay-month')
async def pay_this_month(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.pay_all_this_month()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Pay this month failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post('/remove-pay-month')
async def remove_payment_this_month(request: Request, _=Depends(require_superuser)):
    ok, payload = await _confirm_check(request)
    if not ok:
        return JSONResponse({"error": "Invalid or missing confirmation code"}, status_code=400)
    try:
        result = await api_client.remove_payments_this_month()
        return _with_confirm_cookie(JSONResponse(result), payload)
    except Exception as e:
        logger.exception(f"Remove payment this month failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get('/tasks')
async def list_tasks(request: Request, _=Depends(require_superuser)):
    try:
        result = await api_client.list_tasks()
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"List tasks failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get('/tasks/{task_id}')
async def get_task(task_id, request: Request, _=Depends(require_superuser)):
    try:
        result = await api_client.get_task(task_id)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"Get task {task_id} failed:")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get('/logs')
async def logs(request: Request, _=Depends(require_superuser)):
    return templates.TemplateResponse(request, 'dev/logs.html', {})


@router.get('/api/logs')
async def api_logs(request: Request, _=Depends(require_superuser)):
    from shared.logger import query_logs
    service = request.query_params.get('service') or None
    level = request.query_params.get('level') or None
    q = request.query_params.get('q') or None
    try:
        limit = min(int(request.query_params.get('limit', '200')), 1000)
    except (ValueError, TypeError):
        limit = 200
    try:
        offset = int(request.query_params.get('offset', '0'))
    except (ValueError, TypeError):
        offset = 0
    results = query_logs(service=service, level=level, q=q, limit=limit, offset=offset)
    return {'data': results, 'total': len(results)}


@router.post('/api/logs/clear')
async def api_logs_clear(request: Request, _=Depends(require_superuser)):
    import glob
    import os as os_mod
    for path in glob.glob('/var/log/app/*.db'):
        try:
            os_mod.remove(path)
        except Exception as e:
            logger.exception(f"Failed to remove log file {path}: {e}")
    return {'message': 'Logs cleared'}
