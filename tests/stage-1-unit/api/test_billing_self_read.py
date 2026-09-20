"""Regression: GET /api/customer/{n}/billing honors X-Customer-Token.

The billing route previously rejected every request with 403 because it
had no customer-self branch.  After the fix:

  * matching X-Customer-Token  -> past auth (404 = no row, not 403)
  * cross-number X-Customer-Token -> 403 (self-read guard)
  * no token                    -> 403 (staff path unchanged)
"""
import os

LONG_SECRET = "test-secret-32-chars-long-enough-0123456789abcdef"
os.environ["SECRET_KEY"] = LONG_SECRET

from shared.wbs_jwt import create_customer_token  # noqa: E402


def _headers(token: str) -> dict:
    return {"X-Customer-Token": token} if token else {}


class TestBillingSelfRead:
    def test_own_number_passes_auth(self, client):
        token = create_customer_token(1, {"name": "A"}, secret=LONG_SECRET)
        r = client.get("/api/customer/1/billing", headers=_headers(token))
        # 404 = auth OK, no billing row for this number; 403 would mean
        # the self-read guard failed and the staff path rejected it
        assert r.status_code != 403, r.text
        assert r.status_code != 401, r.text

    def test_cross_number_denied(self, client):
        token = create_customer_token(2, secret=LONG_SECRET)
        r = client.get("/api/customer/1/billing", headers=_headers(token))
        assert r.status_code in (401, 403), r.text

    def test_anonymous_uses_staff_path(self, client):
        r = client.get("/api/customer/1/billing")
        # No token -> staff-only path; result is 403 (no staff context)
        assert r.status_code in (401, 403), r.text
