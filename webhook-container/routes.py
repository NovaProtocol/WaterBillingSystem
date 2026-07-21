from flask import Blueprint, request, jsonify
import logging
import os, requests

logger = logging.getLogger('webhook-container')

webhook_bp = Blueprint('webhook', __name__)
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://api:8008')
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', '')

@webhook_bp.route('/webhook/xendit', methods=['POST'])
def xendit_webhook():
    headers = {
        'X-Callback-Token': INTERNAL_API_KEY,
        'Content-Type': 'application/json',
    }
    try:
        resp = requests.post(
            f"{API_BASE_URL}/api/webhook/xendit-payment",
            json=request.get_json(silent=True),
            headers=headers,
            timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.exception(f"Xendit webhook proxy failed:")
        return jsonify({'error': str(e)}), 502
