from __future__ import annotations

import sys
import warnings

warnings.filterwarnings(
    "ignore",
    message="The global interpreter lock \\(GIL\\) has been enabled to load module",
    category=RuntimeWarning,
)
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask
from flask.testing import FlaskClient

from apps import cache as _cache
from apps import create_app
from apps import db as _db
from apps.authentication.util import hash_pass
from apps.models import ApiKey, Billing, Customer, MeterReading, Staff, XenditTransaction


class TestConfig:
    SECRET_KEY: str = "test-secret-key-for-testing"
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    TESTING: bool = True
    WTF_CSRF_ENABLED: bool = False
    DEBUG: bool = True
    BASE_DIR: Path = Path(__file__).resolve().parent.parent / "apps"
    NFC_PWD_SECRET: str = "0000000000000000000000000000000000000000000000000000000000000000"


@pytest.fixture(autouse=True)
def _reset_rate_limit(app: Flask) -> None:
    _cache.clear()


@pytest.fixture(scope="function")
def app() -> Flask:
    the_app = create_app(TestConfig)
    ctx = the_app.app_context()
    ctx.push()
    _db.create_all()
    yield the_app
    _db.session.remove()
    _db.drop_all()
    ctx.pop()


@pytest.fixture(scope="function")
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture(scope="function")
def superuser(app: Flask) -> Staff:
    s = Staff(
        username="superuser",
        name="Superuser",
        password=hash_pass("superuser"),
        can_read_meters=True,
        can_accept_payment=True,
        can_enroll_customer=True,
        can_drop_reading=True,
        can_drop_payment=True,
        can_enroll_staff=True,
        can_manage_billing=True,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def staff_read_only(app: Flask) -> Staff:
    s = Staff(
        username="reader",
        name="Reader",
        password=hash_pass("reader"),
        can_read_meters=True,
        can_accept_payment=False,
        can_enroll_customer=False,
        can_drop_reading=False,
        can_drop_payment=False,
        can_enroll_staff=False,
        can_manage_billing=False,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def staff_payments_only(app: Flask) -> Staff:
    s = Staff(
        username="cashier",
        name="Cashier",
        password=hash_pass("cashier"),
        can_read_meters=False,
        can_accept_payment=True,
        can_enroll_customer=False,
        can_drop_reading=False,
        can_drop_payment=False,
        can_enroll_staff=False,
        can_manage_billing=False,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def staff_drop_payment(app: Flask) -> Staff:
    s = Staff(
        username="drop_pay",
        name="Drop Payment",
        password=hash_pass("drop_pay"),
        can_read_meters=False,
        can_accept_payment=False,
        can_enroll_customer=False,
        can_drop_reading=False,
        can_drop_payment=True,
        can_enroll_staff=False,
        can_manage_billing=False,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def staff_drop_reading(app: Flask) -> Staff:
    s = Staff(
        username="drop_read",
        name="Drop Reading",
        password=hash_pass("drop_read"),
        can_read_meters=False,
        can_accept_payment=False,
        can_enroll_customer=False,
        can_drop_reading=True,
        can_drop_payment=False,
        can_enroll_staff=False,
        can_manage_billing=False,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def staff_manage_billing(app: Flask) -> Staff:
    s = Staff(
        username="mgr_bill",
        name="Billing Manager",
        password=hash_pass("mgr_bill"),
        can_read_meters=False,
        can_accept_payment=False,
        can_enroll_customer=False,
        can_drop_reading=False,
        can_drop_payment=False,
        can_enroll_staff=False,
        can_manage_billing=True,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def staff_enroll(app: Flask) -> Staff:
    s = Staff(
        username="enroller",
        name="Enroller",
        password=hash_pass("enroller"),
        can_read_meters=False,
        can_accept_payment=False,
        can_enroll_customer=True,
        can_drop_reading=False,
        can_drop_payment=False,
        can_enroll_staff=True,
        can_manage_billing=False,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def logged_in_superuser(client: FlaskClient, superuser: Staff) -> Any:
    client.post(
        "/staff/login",
        data={"username": "superuser", "password": "superuser", "login": ""},
        follow_redirects=True,
    )
    return client


@pytest.fixture(scope="function")
def sample_customer(app: Flask) -> Customer:
    c = Customer(
        customer_number="CUST-001",
        name="Juan Dela Cruz",
        address="123 Rizal St, Manila",
        contact_number="09171234567",
        email="juan@example.com",
        cumulative_balance=0.00,
    )
    _db.session.add(c)
    _db.session.commit()
    return c


@pytest.fixture(scope="function")
def sample_customer_with_balance(app: Flask) -> Customer:
    c = Customer(
        customer_number="CUST-002",
        name="Maria Clara",
        address="456 Mabini St, Manila",
        contact_number="09179876543",
        email="maria@example.com",
        cumulative_balance=150.75,
    )
    _db.session.add(c)
    _db.session.commit()
    return c


@pytest.fixture(scope="function")
def sample_reader_token(app: Flask, staff_read_only: Staff) -> ApiKey:
    import secrets

    key = "CRDC-" + secrets.token_hex(16).upper()
    ak = ApiKey(key=key, label="Reader Token", staff_id=staff_read_only.id, is_active=True)
    _db.session.add(ak)
    _db.session.commit()
    return ak


@pytest.fixture(scope="function")
def sample_readings(
    app: Flask, sample_customer: Customer, sample_reader_token: ApiKey
) -> dict[str, MeterReading]:
    now = datetime.utcnow()
    r1 = MeterReading(
        customer_number="CUST-001",
        reading_value=100.0,
        token_id=sample_reader_token.id,
        timestamp=now - timedelta(days=60),
    )
    r2 = MeterReading(
        customer_number="CUST-001",
        reading_value=250.0,
        token_id=sample_reader_token.id,
        timestamp=now - timedelta(days=30),
    )
    r3 = MeterReading(
        customer_number="CUST-001",
        reading_value=400.0,
        token_id=sample_reader_token.id,
        timestamp=now,
    )
    _db.session.add(r1)
    _db.session.add(r2)
    _db.session.add(r3)
    _db.session.commit()
    return {"latest": r3, "last": r2, "oldest": r1}


@pytest.fixture(scope="function")
def sample_billing(
    app: Flask,
    sample_customer: Customer,
    sample_readings: dict[str, MeterReading],
    superuser: Staff,
) -> Billing:
    now = datetime.utcnow()
    b = Billing(
        customer_number="CUST-001",
        receipt_number="RCP-TEST-001",
        paid_amount=500.0,
        billed_amount=400.0,
        cashier_id=superuser.id,
        reading_id=sample_readings["last"].id,
        is_paid=True,
        payment_timestamp=now - timedelta(days=25),
        date_paid=now - timedelta(days=25),
    )
    _db.session.add(b)
    _db.session.commit()
    return b


@pytest.fixture(scope="function")
def sample_api_key(app: Flask, superuser: Staff) -> ApiKey:
    import secrets

    key = "CRDC-" + secrets.token_hex(16).upper()
    ak = ApiKey(
        key=key,
        label="Test Key",
        staff_id=superuser.id,
        is_active=True,
    )
    _db.session.add(ak)
    _db.session.commit()
    return ak


@pytest.fixture(scope="function")
def sample_revoked_api_key(app: Flask, superuser: Staff) -> ApiKey:
    import secrets

    key = "CRDC-" + secrets.token_hex(16).upper()
    ak = ApiKey(
        key=key,
        label="Revoked Key",
        staff_id=superuser.id,
        is_active=False,
    )
    _db.session.add(ak)
    _db.session.commit()
    return ak


@pytest.fixture(scope="function")
def xendit_staff(app: Flask) -> Staff:
    s = Staff(
        username="xendit",
        name="Xendit",
        password=b"",
        can_accept_payment=True,
        can_manage_billing=True,
        can_drop_payment=True,
    )
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture(scope="function")
def pending_xendit_txn(
    app: Flask, sample_customer: Customer, xendit_staff: Staff
) -> XenditTransaction:
    import secrets
    dt = datetime.utcnow()
    txn = XenditTransaction(
        customer_number="CUST-001",
        xendit_pr_id="xendit-pr-" + secrets.token_hex(16),
        external_id="ext-" + secrets.token_hex(8),
        amount=250.0,
        payment_method="gcash",
        status="PENDING",
        date_created=dt,
        date_modified=dt,
    )
    _db.session.add(txn)
    _db.session.commit()
    return txn


@pytest.fixture(scope="function")
def paid_xendit_txn(
    app: Flask, sample_customer: Customer, xendit_staff: Staff
) -> XenditTransaction:
    import secrets
    dt = datetime.utcnow()
    txn = XenditTransaction(
        customer_number="CUST-001",
        xendit_pr_id="xendit-pr-paid-" + secrets.token_hex(16),
        external_id="ext-paid-" + secrets.token_hex(8),
        amount=250.0,
        payment_method="gcash",
        status="PAID",
        receipt_number="RCP-XENDIT-TEST",
        billing_receipt="RCP-XENDIT-TEST",
        date_created=dt - timedelta(hours=2),
        date_modified=dt - timedelta(hours=2),
    )
    _db.session.add(txn)
    _db.session.commit()
    return txn
