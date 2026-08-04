import os
from flask import request
from itsdangerous import URLSafeTimedSerializer

SALT = 'billing-session'
MAX_AGE = 3600

serializer = URLSafeTimedSerializer(os.environ['SECRET_KEY'], salt=SALT)


def load_session():
    token = request.cookies.get('billing_session')
    if not token:
        return None
    try:
        return serializer.loads(token, max_age=MAX_AGE)
    except Exception:
        return None
