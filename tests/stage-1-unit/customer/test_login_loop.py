"""Login-loop regression tests (plan wbs-customer-login-loop).

Login must set billing_session; context with session must succeed by
forwarding the token to the API; failures must surface as renderable
envelope errors (never a silent bounce); boot must redirect on 401 only.
"""
import os

LONG_SECRET = "test-secret-32-chars-long-enough-0123456789abcdef"

os.environ["SECRET_KEY"] = LONG_SECRET

import api_client  # noqa: E402
from shared.wbs_jwt import create_customer_token  # noqa: E402


def _login_ok(monkeypatch, number=5):
    async def fake_login(account_number, name="", last_receipt=""):
        return {"customer_number": number, "customer": {"customer_number": number, "name": "Test"}}
    monkeypatch.setattr(api_client, "customer_login", fake_login)


class TestLoginLoop:
    def test_login_sets_cookie(self, client, monkeypatch):
        _login_ok(monkeypatch)
        r = client.post("/customer/api/login", json={"account_number": 5})
        assert r.status_code == 200, r.text
        assert r.json()["redirect"] == "/customer/"
        assert "billing_session=" in r.headers.get("set-cookie", "")

    def test_context_200_with_session_forwards_token(self, client, monkeypatch):
        seen = {}

        async def fake_billing(number, customer_token=""):
            seen["number"] = number
            seen["token"] = customer_token
            return {"customer_number": number}

        monkeypatch.setattr(api_client, "get_billing", fake_billing)
        token = create_customer_token(5, {"name": "Test"}, secret=LONG_SECRET)
        r = client.get("/customer/api/context", cookies={"billing_session": token})
        assert r.status_code == 200, r.text
        assert seen["number"] == 5
        assert seen["token"] == token
        body = r.json()
        assert "customer" in body and "billing" in body

    def test_context_401_without_session(self, client):
        r = client.get("/customer/api/context")
        assert r.status_code == 401

    def test_context_failure_is_renderable_not_redirect(self, client, monkeypatch):
        """A 500-shaped backend failure relays as an envelope error, not 401."""

        async def boom(number, customer_token=""):
            raise RuntimeError("backend down")

        monkeypatch.setattr(api_client, "get_billing", boom)
        token = create_customer_token(5, secret=LONG_SECRET)
        r = client.get("/customer/api/context", cookies={"billing_session": token})
        assert r.status_code != 401
        body = r.json()
        assert "error" in body and "error_code" in body

    def test_boot_redirects_only_on_401(self):
        import pathlib

        js = pathlib.Path("shared/static/customer/js/app.js").read_text()
        assert "resp.status === 401" in js
        catch = js.split(".catch(")[-1]
        assert "/customer/login" not in catch
        assert "context-error" in js

    def test_dashboard_has_inline_error_container(self):
        import pathlib

        html = pathlib.Path("customer-portal/templates/customer/app.html").read_text()
        assert 'id="context-error"' in html
        assert 'id="context-error-msg"' in html
