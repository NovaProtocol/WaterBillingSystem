from flask import Blueprint, request, jsonify
import os

webhook_bp = Blueprint('xendit_webhook', __name__)

@webhook_bp.route('/api/xendit-payment', methods=['POST'])
def xendit_webhook():
    token = request.headers.get('X-Callback-Token')
    if token != os.environ.get('XENDIT_WEBHOOK_TOKEN'):
        return jsonify({'error': 'Invalid token'}), 401
    from app import db
    from models import XenditTransaction
    data = request.get_json()
    external_id = data.get('external_id', '')
    status = data.get('status', '')
    tx = XenditTransaction.query.filter_by(external_id=external_id).first()
    if tx:
        tx.status = status
        if status == 'PAID':
            parts = external_id.split('-')
            customer_number = parts[1] if len(parts) > 1 else ''
            from services.payment_service import submit_payment
            from models import Billing
            billings = Billing.query.filter_by(customer_number=customer_number, is_paid=False).order_by(Billing.created_at).all()
            for b in billings:
                submit_payment(b.id, tx.id)
        db.session.commit()
    return jsonify({'received': True})
