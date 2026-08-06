import logging
import os

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_async import session, sync_session
from models import Staff, XenditTransaction

logger = logging.getLogger('api')

webhook_router = APIRouter()


@webhook_router.post('/api/webhook/xendit-payment')
async def xendit_webhook(request: Request):
    token = request.headers.get('X-Callback-Token')
    if token != os.environ['XENDIT_WEBHOOK_TOKEN']:
        if token != os.environ['INTERNAL_API_KEY']:
            return JSONResponse({'error': 'Invalid token'}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    logger.info(f"Xendit webhook received: event={data.get('event')}, status={data.get('data', {}).get('status', 'unknown')}")
    callback = data.get('data', data)
    status = callback.get('status', '').upper()
    reference_id = callback.get('reference_id', '') or callback.get('external_id', '')

    if not reference_id:
        logger.warning(f"Xendit webhook: missing reference_id in {callback}")
        return JSONResponse({'error': 'Missing reference_id'}, status_code=400)

    from services.payment_service import submit_payment

    result = await session().execute(
        select(XenditTransaction).where(XenditTransaction.external_id == reference_id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        result = await session().execute(
            select(XenditTransaction).where(XenditTransaction.xendit_pr_id == callback.get('id', ''))
        )
        tx = result.scalar_one_or_none()
    if not tx:
        logger.warning(f"Xendit webhook: transaction not found for ref={reference_id} id={callback.get('id')}")
        return {'received': True}

    logger.info(f"Found transaction: id={tx.id} cust={tx.customer_number} amount={tx.amount} current_status={tx.status}")

    tx.status = status

    if status in ('PAID', 'SUCCEEDED', 'COMPLETED'):
        result = await session().execute(
            select(Staff).where(Staff.username == 'xendit')
        )
        xendit_staff = result.scalar_one_or_none()
        cashier_id = xendit_staff.id if xendit_staff else 1
        pay_amount = float(tx.base_amount or tx.amount)

        def _pay():
            s = sync_session()
            try:
                return submit_payment(tx.customer_number, pay_amount, cashier_id, session=s)
            finally:
                s.close()

        res, error, code = await run_in_threadpool(_pay)
        if error:
            logger.error(f"Auto-pay failed for {tx.customer_number}: {error}")
        else:
            logger.info(f"Auto-paid {tx.customer_number} via Xendit: {pay_amount} result={res}")

    await session().commit()
    return {'received': True}
