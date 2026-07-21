from flask import Blueprint, request, jsonify
import logging
import os

logger = logging.getLogger('api')

webhook_bp = Blueprint('xendit_webhook', __name__)

@webhook_bp.route('/api/webhook/xendit-payment', methods=['POST'])
def xendit_webhook():
    token = request.headers.get('X-Callback-Token')
    if token != os.environ.get('XENDIT_WEBHOOK_TOKEN'):  # uses INTERNAL_API_KEY from proxy
        if token != os.environ.get('INTERNAL_API_KEY'):
            return jsonify({'error': 'Invalid token'}), 401

    data = request.get_json(silent=True) or {}
    logger.info(f"Xendit webhook received: event={data.get('event')}, status={data.get('data', {}).get('status', 'unknown')}")
    callback = data.get('data', data)
    status = callback.get('status', '').upper()
    reference_id = callback.get('reference_id', '') or callback.get('external_id', '')

    if not reference_id:
        logger.warning(f"Xendit webhook: missing reference_id in {callback}")
        return jsonify({'error': 'Missing reference_id'}), 400

    from app import db
    from models import Customer, Staff, XenditTransaction
    from services.payment_service import submit_payment

    tx = XenditTransaction.query.filter_by(external_id=reference_id).first()
    if not tx:
        tx = XenditTransaction.query.filter_by(xendit_pr_id=callback.get('id', '')).first()
    if not tx:
        logger.warning(f"Xendit webhook: transaction not found for ref={reference_id} id={callback.get('id')}")
        return jsonify({'received': True})

    logger.info(f"Found transaction: id={tx.id} cust={tx.customer_number} amount={tx.amount} current_status={tx.status}")

    tx.status = status

    if status in ('PAID', 'SUCCEEDED', 'COMPLETED'):
        xendit_staff = Staff.query.filter_by(username='xendit').first()
        cashier_id = xendit_staff.id if xendit_staff else 1
        pay_amount = float(tx.base_amount or tx.amount)
        result, error, code = submit_payment(tx.customer_number, pay_amount, cashier_id)
        if error:
            logger.error(f"Auto-pay failed for {tx.customer_number}: {error}")
        else:
            logger.info(f"Auto-paid {tx.customer_number} via Xendit: {pay_amount} result={result}")

    db.session.commit()
    return jsonify({'received': True})
