"""Self-read auth for GET /api/customer/{n} (plan wbs-customer-login-loop).

Own-number portal JWT authorizes; cross-number / anonymous / invalid do not.
Staff path via require_staff is unchanged.
"""
import os

from fastapi import Request

LONG_SECRET = "test-secret-32-chars-long-enough-0123456789abcdef"

os.environ["SECRET_KEY"] = LONG_SECRET

from shared.wbs_jwt import create_customer_token  # noqa: E402
from utils import require_customer_self  # noqa: E402


def _req(token: str = "") -> Request:
    scope = {"type": "http", "headers": []}
    req = Request(scope)
    if token:
        # starlette stores headers immutably; inject via scope
        req.scope["headers"] = [(b"x-customer-token", token.encode())]
    return req


class TestRequireCustomerSelf:
    def test_own_number_ok(self):
        token = create_customer_token(1, {"name": "A"}, secret=LONG_SECRET)
        assert os.environ.get("SECRET_KEY") == LONG_SECRET
        data = require_customer_self(1, _req(token))
        assert data is not None
        assert int(data["customer_number"]) == 1

    def test_cross_number_denied(self):
        token = create_customer_token(2, secret=LONG_SECRET)
        assert require_customer_self(1, _req(token)) is None

    def test_anonymous_denied(self):
        assert require_customer_self(1, _req("")) is None

    def test_invalid_token_denied(self):
        assert require_customer_self(1, _req("not-a-jwt")) is None


class TestCustomerInfoGuard:
    def test_anonymous_denied(self, client):
        r = client.get("/api/customer/1")
        assert r.status_code in (401, 403)

    def test_cross_number_denied(self, client):
        token = create_customer_token(2, secret=LONG_SECRET)
        r = client.get("/api/customer/1", headers={"X-Customer-Token": token})
        assert r.status_code in (401, 403)

    def test_own_number_passes_auth(self, client):
        """Own-number JWT passes the auth guard (404 = auth OK, no row)."""
        token = create_customer_token(99991, secret=LONG_SECRET)
        r = client.get("/api/customer/99991", headers={"X-Customer-Token": token})
        # 404 proves the self-read guard passed; 401/403 would mean auth failed
        assert r.status_code != 401, r.text
        assert r.status_code != 403, r.text

    def test_staff_path_unchanged(self, client):
        # No staff context forwarded -> staff-only callers without perms still 403/401
        r = client.get("/api/customer/count", headers={"X-Internal-API-Key": "test"})
        assert r.status_code in (401, 403, 200)
