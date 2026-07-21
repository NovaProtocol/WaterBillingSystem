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
    callback = data.get('data', data)
    status = callback.get('status', '').upper()
    reference_id = callback.get('reference_id', '') or callback.get('external_id', '')

    if not reference_id:
        return jsonify({'error': 'Missing reference_id'}), 400

    from app import db
    from models import Customer, Staff, XenditTransaction
    from services.payment_service import submit_payment

    tx = XenditTransaction.query.filter_by(external_id=reference_id).first()
    if not tx:
        tx = XenditTransaction.query.filter_by(xendit_pr_id=callback.get('id', '')).first()
    if not tx:
        logger.warning(f"Xendit webhook: transaction not found for {reference_id}")
        return jsonify({'received': True})

    tx.status = status

    if status == 'PAID':
        xendit_staff = Staff.query.filter_by(username='xendit').first()
        cashier_id = xendit_staff.id if xendit_staff else 1
        result, error, code = submit_payment(tx.customer_number, float(tx.amount), cashier_id)
        if error:
            logger.error(f"Auto-pay failed for {tx.customer_number}: {error}")
        else:
            logger.info(f"Auto-paid {tx.customer_number} via Xendit: {tx.amount}")

    db.session.commit()
    return jsonify({'received': True})
