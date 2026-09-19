import datetime as dt

import jwt

from shared.wbs_jwt import (
    ALG,
    AUD,
    ISS,
    create_customer_token,
    create_dev_token,
    create_staff_token,
    decode_without_verify,
    verify_customer_token,
    verify_dev_token,
    verify_staff_token,
)

SECRET = "test-secret-32-chars-long-enough"


class TestCustomerToken:
    def test_roundtrip_returns_customer_number(self):
        token = create_customer_token(1, {"name": "Domingo"}, secret=SECRET)
        data = verify_customer_token(token, secret=SECRET)
        assert data is not None
        assert data["customer_number"] == 1

    def test_payload_carries_iss_aud_jti(self):
        token = create_customer_token(1, secret=SECRET)
        data = decode_without_verify(token)
        assert data is not None
        assert data["iss"] == ISS
        assert data["aud"] == AUD
        assert data["jti"]

    def test_expired_token_returns_none(self):
        token = create_customer_token(1, secret=SECRET, expires_hours=-1)
        assert verify_customer_token(token, secret=SECRET) is None

    def test_wrong_aud_returns_none(self):
        payload = {
            "iss": ISS,
            "aud": "someone-else",
            "iat": dt.datetime.now(dt.timezone.utc),
            "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
            "customer_number": 1,
        }
        token = jwt.encode(payload, SECRET, algorithm=ALG)
        assert verify_customer_token(token, secret=SECRET) is None

    def test_wrong_secret_returns_none(self):
        token = create_customer_token(1, secret=SECRET)
        assert verify_customer_token(token, secret="wrong-secret-32-chars-long-enough") is None

    def test_missing_customer_number_returns_none(self):
        payload = {
            "iss": ISS,
            "aud": AUD,
            "iat": dt.datetime.now(dt.timezone.utc),
            "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET, algorithm=ALG)
        assert verify_customer_token(token, secret=SECRET) is None

    def test_none_token_returns_none(self):
        assert verify_customer_token(None, secret=SECRET) is None


class TestStaffToken:
    def test_roundtrip_preserves_id_and_perms(self):
        staff = {"id": 7, "username": "cathy", "can_enroll_staff": True, "password": "secret"}
        token = create_staff_token(staff, secret=SECRET)
        data = verify_staff_token(token, secret=SECRET)
        assert data is not None
        assert data["id"] == 7
        assert data["can_enroll_staff"] is True
        assert "password" not in data

    def test_missing_id_returns_none(self):
        token = create_staff_token({"username": "noid"}, secret=SECRET)
        assert verify_staff_token(token, secret=SECRET) is None

    def test_expired_token_returns_none(self):
        token = create_staff_token({"id": 1}, secret=SECRET, expires_hours=-1)
        assert verify_staff_token(token, secret=SECRET) is None


class TestDevToken:
    def test_superuser_gate_passes(self):
        token = create_dev_token({"username": "superuser"}, secret=SECRET)
        data = verify_dev_token(token, secret=SECRET)
        assert data is not None
        assert data["username"] == "superuser"

    def test_non_superuser_returns_none(self):
        token = create_dev_token({"username": "cathy"}, secret=SECRET)
        assert verify_dev_token(token, secret=SECRET) is None

    def test_dev_token_fails_staff_gate(self):
        token = create_dev_token({"username": "superuser"}, secret=SECRET)
        assert verify_staff_token(token, secret=SECRET) is None
