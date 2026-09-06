from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import jwt

from shared.config import get_config

ISS = "wbs"
AUD = "waterbillingsystem"
ALG = "HS256"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _secret(secret: str | None = None) -> str:
    if secret:
        return secret
    return get_config().SECRET_KEY


def _base_payload(expires_hours: int, secret: str | None = None) -> dict[str, Any]:
    now = _now()
    return {
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + dt.timedelta(hours=expires_hours),
        "jti": uuid.uuid4().hex,
    }


def create_customer_token(
    customer_number: int, customer: dict | None = None, secret: str | None = None, expires_hours: int = 12
) -> str:
    sec = _secret(secret)
    payload = {**_base_payload(expires_hours, sec), "customer_number": int(customer_number)}
    if customer is not None:
        payload["customer"] = customer
    return jwt.encode(payload, sec, algorithm=ALG)


def verify_customer_token(token: str | None, secret: str | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    sec = _secret(secret)
    try:
        data = jwt.decode(token, sec, algorithms=[ALG], audience=AUD, issuer=ISS)
        if "customer_number" not in data:
            return None
        return data
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        # one-deploy grace: try itsdangerous
        try:
            from shared.auth import load_token as _load_its

            d = _load_its(token)
            if d and d.get("customer_number"):
                try:
                    import logging

                    logging.getLogger("wbs.jwt").info("jwt_fallback_used customer")
                except Exception:
                    pass
                return d
        except Exception:
            pass
        return None
    except Exception:
        return None


def create_staff_token(staff: dict, secret: str | None = None, expires_hours: int = 8) -> str:
    sec = _secret(secret)
    payload = {**_base_payload(expires_hours, sec), **{k: v for k, v in staff.items() if k != "password"}}
    # ensure id present
    if "id" not in payload and "staff_id" in staff:
        payload["id"] = staff["staff_id"]
    return jwt.encode(payload, sec, algorithm=ALG)


def verify_staff_token(token: str | None, secret: str | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    sec = _secret(secret)
    try:
        data = jwt.decode(token, sec, algorithms=[ALG], audience=AUD, issuer=ISS)
        if not data.get("id"):
            return None
        return data
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        try:
            from shared.auth import load_token as _load_its

            d = _load_its(token)
            if d and d.get("id"):
                try:
                    import logging

                    logging.getLogger("wbs.jwt").info("jwt_fallback_used staff")
                except Exception:
                    pass
                return d
        except Exception:
            pass
        return None
    except Exception:
        return None


def create_dev_token(payload: dict, secret: str | None = None, expires_hours: int = 8) -> str:
    sec = _secret(secret)
    base = _base_payload(expires_hours, sec)
    base.update(payload)
    return jwt.encode(base, sec, algorithm=ALG)


def verify_dev_token(token: str | None, secret: str | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    sec = _secret(secret)
    try:
        data = jwt.decode(token, sec, algorithms=[ALG], audience=AUD, issuer=ISS)
        if data.get("username") != "superuser":
            return None
        return data
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        try:
            from shared.auth import load_token as _load_its

            d = _load_its(token)
            if d and d.get("username") == "superuser":
                try:
                    import logging

                    logging.getLogger("wbs.jwt").info("jwt_fallback_used dev")
                except Exception:
                    pass
                return d
        except Exception:
            pass
        return None
    except Exception:
        return None


def decode_without_verify(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None
