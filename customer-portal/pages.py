import os

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from shared.auth import load_token

from app import templates

DEBUG = os.environ['DEBUG'].lower() in ('true', '1', 'yes')

pages_bp = APIRouter()


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=302)


@pages_bp.get('/customer/login')
async def login(request: Request):
    return templates.TemplateResponse(request, 'customer/login.html', {'debug': DEBUG})


@pages_bp.get('/customer/logout')
async def logout():
    resp = RedirectResponse('/customer/login', status_code=302)
    resp.headers['Cache-Control'] = 'no-store'
    resp.delete_cookie('billing_session', path='/customer/')
    return resp


@pages_bp.get('/customer/')
async def app_shell(request: Request):
    return templates.TemplateResponse(request, 'customer/app.html', {})


@pages_bp.get('/customer/maintenance')
async def maintenance(request: Request):
    if not load_token(request.cookies.get('billing_session')):
        return _redirect('/customer/login')
    return templates.TemplateResponse(request, 'customer/maintenance.html', {})


@pages_bp.get('/customer/report')
async def report(request: Request):
    if not load_token(request.cookies.get('billing_session')):
        return _redirect('/customer/login')
    return templates.TemplateResponse(request, 'customer/report.html', {})


@pages_bp.get('/customer/billing/{customer_number}')
async def billing_redirect(customer_number: int):
    return RedirectResponse('/customer/', status_code=301)


@pages_bp.get('/customer/identify')
async def identify_redirect():
    return RedirectResponse('/customer/login', status_code=301)
