from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any

from apps import db
from apps.models import (
    ApiKey,
    Billing,
    Customer,
    ManagementLog,
    MeterReading,
    Staff,
)
from apps.pricing import compute_penalty, compute_water_bill

# =============================================================================
# Authentication Tests
# =============================================================================


class TestAuth:
    def test_login_page_renders(self, client: Any) -> None:
        resp = client.get("/staff/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data or b"login" in resp.data

    def test_login_success_redirects_to_dashboard(
        self, client: Any, superuser: Staff
    ) -> None:
        resp = client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data or b"dashboard" in resp.data.lower()

    def test_login_fail_shows_error(self, client: Any, superuser: Staff) -> None:
        resp = client.post(
            "/staff/login",
            data={"username": "superuser", "password": "wrongpass", "login": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Wrong user or password" in resp.data

    def test_login_unknown_user(self, client: Any) -> None:
        resp = client.post(
            "/staff/login",
            data={"username": "nobody", "password": "nobody", "login": ""},
            follow_redirects=True,
        )
        assert b"Wrong user or password" in resp.data

    def test_logout_redirects_to_index(
        self, client: Any, logged_in_superuser: Any
    ) -> None:
        resp = client.get("/staff/logout", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Login" in resp.data or b"login" in resp.data

    def test_already_logged_in_redirects_to_dashboard(
        self, client: Any, logged_in_superuser: Any
    ) -> None:
        resp = client.get("/staff/login", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data or b"dashboard" in resp.data.lower()

    def test_dashboard_requires_auth(self, client: Any) -> None:
        resp = client.get("/staff/dashboard", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Login" in resp.data or b"login" in resp.data

    def test_staff_index_public(self, client: Any) -> None:
        resp = client.get("/staff/")
        assert resp.status_code == 200


# =============================================================================
# Permission Tests
# =============================================================================


class TestPermissions:
    def test_meter_reading_requires_can_read_meters(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "cashier", "password": "cashier", "login": ""},
        )
        resp = client.get("/staff/meter-reading")
        assert resp.status_code == 302
        assert "/staff/login" in resp.location

    def test_meter_reading_allowed(self, client: Any, staff_read_only: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        resp = client.get("/staff/meter-reading", follow_redirects=True)
        assert resp.status_code == 200
        assert b"API" in resp.data or b"meter" in resp.data.lower()

    def test_payments_requires_can_accept_payment(
        self, client: Any, staff_read_only: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        resp = client.get("/staff/payments")
        assert resp.status_code == 302
        assert "/staff/login" in resp.location

    def test_payments_allowed(self, client: Any, staff_payments_only: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "cashier", "password": "cashier", "login": ""},
        )
        resp = client.get("/staff/payments", follow_redirects=True)
        assert resp.status_code == 200

    def test_undo_payment_requires_can_drop_payment(
        self,
        client: Any,
        superuser: Staff,
        sample_billing: Billing,
        staff_read_only: Staff,
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            f"/staff/manage-billing/undo-payment/{sample_billing.id}",
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 200  # superuser has all perms

        client.get("/staff/logout")
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        with client.application.app_context():
            from datetime import datetime

            reader = db.session.get(Staff, staff_read_only.id)
            b2 = Billing(
                customer_number="CUST-001",
                receipt_number="RCP-NOPERM-001",
                paid_amount=100.0,
                billed_amount=100.0,
                cashier_id=reader.id,
                reading_id=None,
                is_paid=True,
                payment_timestamp=datetime.utcnow(),
                date_paid=datetime.utcnow(),
            )
            db.session.add(b2)
            db.session.commit()
            bid = b2.id
        resp = client.post(
            f"/staff/manage-billing/undo-payment/{bid}",
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_drop_reading_requires_can_drop_reading(
        self,
        client: Any,
        staff_payments_only: Staff,
        sample_readings: dict[str, MeterReading],
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "cashier", "password": "cashier", "login": ""},
        )
        resp = client.post(
            f'/staff/manage-reading/drop-reading/{sample_readings["latest"].id}',
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_undo_payment_no_reason_returns_400(
        self, client: Any, superuser: Staff, sample_billing: Billing
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            f"/staff/manage-billing/undo-payment/{sample_billing.id}",
            data=json.dumps({"reason": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_edit_reading_requires_can_manage_billing(
        self,
        client: Any,
        staff_drop_reading: Staff,
        sample_readings: dict[str, MeterReading],
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "drop_read", "password": "drop_read", "login": ""},
        )
        resp = client.post(
            f'/staff/manage-reading/edit-reading/{sample_readings["latest"].id}',
            data=json.dumps({"reading_value": 999}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_staff_list_requires_can_enroll_staff(
        self, client: Any, staff_read_only: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        resp = client.get("/staff/staff")
        assert resp.status_code == 302
        assert "/staff/login" in resp.location

    def test_staff_list_allowed(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.get("/staff/staff")
        assert resp.status_code == 200

    def test_customers_requires_can_enroll_customer(
        self, client: Any, staff_read_only: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        resp = client.get("/staff/customers")
        assert resp.status_code == 302
        assert "/staff/login" in resp.location

    def test_customers_allowed(self, client: Any, staff_enroll: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "enroller", "password": "enroller", "login": ""},
        )
        resp = client.get("/staff/customers")
        assert resp.status_code == 200


# =============================================================================
# API Tests
# =============================================================================


class TestAPI:
    def test_api_requires_auth(self, client: Any, sample_customer: Customer) -> None:
        resp = client.get("/api/customer/CUST-001")
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert "error" in data

    def test_api_valid_api_key_bearer(
        self, client: Any, sample_customer: Customer, sample_api_key: ApiKey
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["customer_number"] == "CUST-001"

    def test_api_valid_api_key_query_param(
        self, client: Any, sample_customer: Customer, sample_api_key: ApiKey
    ) -> None:
        resp = client.get(f"/api/customer/CUST-001?api_key={sample_api_key.key}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["customer_number"] == "CUST-001"

    def test_api_invalid_api_key_returns_401(
        self, client: Any, sample_customer: Customer
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": "Bearer CRDC-INVALID-KEY"},
        )
        assert resp.status_code == 401

    def test_api_revoked_key_returns_401(
        self, client: Any, sample_customer: Customer, sample_revoked_api_key: ApiKey
    ) -> None:
        resp = client.get(
            f"/api/customer/CUST-001?api_key={sample_revoked_api_key.key}"
        )
        assert resp.status_code == 401

    def test_api_staff_session(
        self, client: Any, superuser: Staff, sample_customer: Customer
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.get("/api/customer/CUST-001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["customer_number"] == "CUST-001"

    def test_api_customer_not_found(self, client: Any, sample_api_key: ApiKey) -> None:
        resp = client.get(
            "/api/customer/DOES-NOT-EXIST",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        assert resp.status_code == 404

    def test_api_returns_valid_json_no_infinity(
        self,
        client: Any,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
        sample_api_key: ApiKey,
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        assert resp.status_code == 200
        raw = resp.data.decode("utf-8")
        assert "Infinity" not in raw
        assert "NaN" not in raw
        data = json.loads(raw)
        assert isinstance(data["consumption"], (int, float))
        assert isinstance(data["total_due"], (int, float))

    def test_api_returns_correct_structure(
        self,
        client: Any,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
        sample_api_key: ApiKey,
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        data = json.loads(resp.data)
        expected_keys = {
            "customer_number",
            "name",
            "address",
            "contact_number",
            "email",
            "latest_reading",
            "last_reading",
            "consumption",
            "bill_breakdown",
            "pricing_tiers",
            "water_bill",
            "original_water_bill",
            "carryover",
            "cumulative_balance",
            "penalty",
            "total_due",
            "latest_unpaid",
            "due_date",
            "days_remaining",
            "billing_items",
            "recent_payments",
        }
        assert expected_keys.issubset(data.keys())
        assert data["customer_number"] == "CUST-001"
        assert data["name"] == "Juan Dela Cruz"

    def test_api_billing_computation(
        self,
        client: Any,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
        sample_api_key: ApiKey,
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        data = json.loads(resp.data)
        # consumption = 400 - 250 = 150
        assert data["consumption"] == 150.0
        # water bill for 150 m3 should be > 0
        assert data["water_bill"] > 0
        # bill breakdown should have entries
        assert len(data["bill_breakdown"]) > 0
        # pricing_tiers should be the full tier list
        assert len(data["pricing_tiers"]) == 5

    def test_api_recent_payments(
        self,
        client: Any,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
        sample_billing: Billing,
        sample_api_key: ApiKey,
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        data = json.loads(resp.data)
        assert len(data["recent_payments"]) >= 1
        assert data["recent_payments"][0]["receipt_number"] == "RCP-TEST-001"

    def test_api_billing_items_status(
        self,
        client: Any,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
        sample_billing: Billing,
        sample_api_key: ApiKey,
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_api_key.key}"},
        )
        data = json.loads(resp.data)
        for item in data["billing_items"]:
            assert item["status"] in ("Paid", "Unpaid", "No bill")
            assert isinstance(item["reading_value"], (int, float))
            assert isinstance(item["total_due"], (int, float))
        # The reading linked to sample_billing should be 'Paid'
        paid_items = [i for i in data["billing_items"] if i["status"] == "Paid"]
        assert len(paid_items) >= 1


# =============================================================================
# Customer Lookup Tests
# =============================================================================


class TestCustomerLookup:
    def test_lookup_requires_auth(self, client: Any, sample_customer: Customer) -> None:
        resp = client.get("/staff/customer-lookup?q=CUST")
        assert resp.status_code == 403

    def test_lookup_empty_query(self, client: Any, logged_in_superuser: Any) -> None:
        resp = client.get("/staff/customer-lookup?q=")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_lookup_short_query(self, client: Any, logged_in_superuser: Any) -> None:
        resp = client.get("/staff/customer-lookup?q=a")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_lookup_by_customer_number(
        self, client: Any, logged_in_superuser: Any, sample_customer: Customer
    ) -> None:
        resp = client.get("/staff/customer-lookup?q=CUST-001")
        data = json.loads(resp.data)
        assert len(data) >= 1
        assert data[0]["customer_number"] == "CUST-001"

    def test_lookup_by_name(
        self, client: Any, logged_in_superuser: Any, sample_customer: Customer
    ) -> None:
        resp = client.get("/staff/customer-lookup?q=Juan")
        data = json.loads(resp.data)
        assert len(data) >= 1
        assert data[0]["name"] == "Juan Dela Cruz"

    def test_lookup_partial_match(
        self, client: Any, logged_in_superuser: Any, sample_customer: Customer
    ) -> None:
        resp = client.get("/staff/customer-lookup?q=Jua")
        data = json.loads(resp.data)
        assert len(data) >= 1

    def test_lookup_no_match(self, client: Any, logged_in_superuser: Any) -> None:
        resp = client.get("/staff/customer-lookup?q=ZZZZNOTEXIST")
        data = json.loads(resp.data)
        assert data == []

    def test_lookup_multiple_customers(
        self,
        client: Any,
        logged_in_superuser: Any,
        sample_customer: Customer,
        sample_customer_with_balance: Customer,
    ) -> None:
        resp = client.get("/staff/customer-lookup?q=CUST")
        data = json.loads(resp.data)
        assert len(data) >= 2

    def test_lookup_returns_limited_results(
        self, client: Any, logged_in_superuser: Any
    ) -> None:
        # Create 15 customers
        with client.application.app_context():
            for i in range(15):
                c = Customer(
                    customer_number=f"BULK-{i:04d}",
                    name=f"Bulk Customer {i}",
                )
                db.session.add(c)
            db.session.commit()
        resp = client.get("/staff/customer-lookup?q=BULK")
        data = json.loads(resp.data)
        assert len(data) <= 10


# =============================================================================
# Payment Tests
# =============================================================================


class TestPayments:
    def test_submit_payment_creates_billing_and_receive(
        self,
        client: Any,
        superuser: Staff,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "amount": 250.0,
                    "reading_id": sample_readings["latest"].id,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert "Payment recorded" in data["message"]
        assert data["amount"] == 250.0

    def test_submit_payment_requires_auth(
        self, client: Any, sample_customer: Customer
    ) -> None:
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "amount": 100.0,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_submit_payment_invalid_customer(
        self, client: Any, logged_in_superuser: Any
    ) -> None:
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "DOES-NOT-EXIST",
                    "amount": 100.0,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_submit_payment_zero_amount(
        self, client: Any, logged_in_superuser: Any, sample_customer: Customer
    ) -> None:
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "amount": 0,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_submit_payment_negative_amount(
        self, client: Any, logged_in_superuser: Any, sample_customer: Customer
    ) -> None:
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "amount": -50,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_submit_payment_empty_customer(
        self, client: Any, logged_in_superuser: Any
    ) -> None:
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "",
                    "amount": 100.0,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_submit_payment_no_reading(
        self, client: Any, logged_in_superuser: Any, sample_customer: Customer
    ) -> None:
        """Payment without linking to a reading should still work"""
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "amount": 100.0,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201

    def test_submit_payment_auto_links_oldest_unpaid_reading(
        self,
        client: Any,
        logged_in_superuser: Any,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
    ) -> None:
        """Payment without reading_id covers oldest unpaid item fully; remainder to credit"""
        resp = client.post(
            "/staff/payments/submit",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "amount": 6000.0,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201


# =============================================================================
# Management Tests (Drop/Edit Payments & Readings)
# =============================================================================


class TestManagement:
    def test_undo_payment_resets_billing(
        self,
        client: Any,
        superuser: Staff,
        sample_customer: Customer,
        sample_billing: Billing,
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            f"/staff/manage-billing/undo-payment/{sample_billing.id}",
            data=json.dumps({"reason": "Test undo"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "Payment group" in data["message"]
        assert "undone" in data["message"]

        with client.application.app_context():
            b = Billing.query.get(sample_billing.id)
            assert b is not None
            assert b.is_paid is False
            assert float(b.paid_amount) == 0
            assert b.receipt_number is None

    def test_undo_payment_creates_log(
        self,
        client: Any,
        superuser: Staff,
        sample_customer: Customer,
        sample_billing: Billing,
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        client.post(
            f"/staff/manage-billing/undo-payment/{sample_billing.id}",
            data=json.dumps({"reason": "Test undo with log check"}),
            content_type="application/json",
        )
        with client.application.app_context():
            log = ManagementLog.query.filter_by(
                target_type="billing", target_id=sample_billing.id
            ).first()
            assert log is not None
            assert log.action_type == "drop"
            assert log.staff_id == superuser.id
            assert "Test undo with log check" in log.details
            assert "RCP-TEST-001" in log.details

    def test_undo_payment_restores_carryover(
        self, client: Any, superuser: Staff, sample_customer: Customer, sample_billing: Billing
    ) -> None:
        from apps.models import Customer
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        with client.application.app_context():
            cust = Customer.query.filter_by(customer_number="CUST-001").first()
            cust.cumulative_balance = 100.0
            db.session.commit()

        resp = client.post(
            f"/staff/manage-billing/undo-payment/{sample_billing.id}",
            data=json.dumps({"reason": "Test carryover restore"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with client.application.app_context():
            cust = Customer.query.filter_by(customer_number="CUST-001").first()
            # formula: 100 + 400.0 + 0 - 500.0 = 0
            assert float(cust.cumulative_balance) == 0.0

    def test_drop_reading_creates_log(
        self,
        client: Any,
        superuser: Staff,
        sample_customer: Customer,
        sample_readings: dict[str, MeterReading],
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        rid = sample_readings["latest"].id
        resp = client.post(
            f"/staff/manage-reading/drop-reading/{rid}",
            data=json.dumps({"reason": "Test reading drop"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with client.application.app_context():
            reading = MeterReading.query.get(rid)
            assert reading is None
            log = ManagementLog.query.filter_by(
                target_type="reading", target_id=rid
            ).first()
            assert log is not None
            assert log.action_type == "drop"
            assert "Test reading drop" in log.details

    def test_edit_reading_creates_log(
        self, client: Any, superuser: Staff, sample_readings: dict[str, MeterReading]
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        rid = sample_readings["latest"].id
        resp = client.post(
            f"/staff/manage-reading/edit-reading/{rid}",
            data=json.dumps({"reading_value": 888.88}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with client.application.app_context():
            reading = MeterReading.query.get(rid)
            assert float(reading.reading_value) == 888.88
            log = ManagementLog.query.filter_by(
                target_type="reading", target_id=rid
            ).first()
            assert log is not None
            assert log.action_type == "edit"

    def test_undo_payment_requires_permission(
        self, client: Any, staff_read_only: Staff, sample_billing: Billing
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        resp = client.post(
            f"/staff/manage-billing/undo-payment/{sample_billing.id}",
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_drop_reading_requires_permission(
        self,
        client: Any,
        staff_payments_only: Staff,
        sample_readings: dict[str, MeterReading],
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "cashier", "password": "cashier", "login": ""},
        )
        resp = client.post(
            f'/staff/manage-reading/drop-reading/{sample_readings["latest"].id}',
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_manage_billing_page_accessible(
        self, client: Any, superuser: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.get("/staff/manage-billing")
        assert resp.status_code == 200

    def test_manage_reading_page_accessible(
        self, client: Any, superuser: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.get("/staff/manage-reading")
        assert resp.status_code == 200

    def test_undo_payment_billing_not_found_404(
        self, client: Any, superuser: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/manage-billing/undo-payment/99999",
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_drop_reading_not_found_404(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/manage-reading/drop-reading/99999",
            data=json.dumps({"reason": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 404


# =============================================================================
# API Key Tests
# =============================================================================


class TestApiKeys:
    def test_generate_api_key(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/meter-reading/generate",
            data=json.dumps({"label": "My Test Key"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["key"].startswith("CRDC-")
        assert data["label"] == "My Test Key"
        assert "id" in data

        with client.application.app_context():
            ak = ApiKey.query.get(data["id"])
            assert ak is not None
            assert ak.key == data["key"]
            assert ak.label == "My Test Key"
            assert ak.is_active is True

    def test_generate_api_key_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "cashier", "password": "cashier", "login": ""},
        )
        resp = client.post(
            "/staff/meter-reading/generate",
            data=json.dumps({"label": "Should Fail"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_generate_api_key_no_label(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/meter-reading/generate",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["key"].startswith("CRDC-")
        assert data["label"] is None

    def test_revoke_api_key(
        self, client: Any, superuser: Staff, sample_api_key: ApiKey
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            f"/staff/meter-reading/revoke/{sample_api_key.id}",
            content_type="application/json",
        )
        assert resp.status_code == 200

        with client.application.app_context():
            ak = ApiKey.query.get(sample_api_key.id)
            assert ak.is_active is False

    def test_revoke_api_key_requires_permission(
        self, client: Any, staff_payments_only: Staff, sample_api_key: ApiKey
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "cashier", "password": "cashier", "login": ""},
        )
        resp = client.post(
            f"/staff/meter-reading/revoke/{sample_api_key.id}",
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_revoke_nonexistent_key_404(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/meter-reading/revoke/99999", content_type="application/json"
        )
        assert resp.status_code == 404

    def test_revoked_key_not_valid_for_api(
        self, client: Any, sample_customer: Customer, sample_revoked_api_key: ApiKey
    ) -> None:
        resp = client.get(
            f"/api/customer/CUST-001?api_key={sample_revoked_api_key.key}"
        )
        assert resp.status_code == 401

    def test_key_page_lists_keys(
        self, client: Any, superuser: Staff, sample_api_key: ApiKey
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.get("/staff/meter-reading")
        assert resp.status_code == 200
        assert sample_api_key.key[:16].encode() in resp.data


# =============================================================================
# Staff CRUD Tests
# =============================================================================


class TestStaffCRUD:
    def test_create_staff(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/staff/create",
            data=json.dumps(
                {
                    "username": "newstaff",
                    "password": "securepass",
                    "can_read_meters": True,
                    "can_accept_payment": True,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["message"] == "Staff created"
        assert data["username"] == "newstaff"

        with client.application.app_context():
            s = Staff.query.filter_by(username="newstaff").first()
            assert s is not None
            assert s.can_read_meters is True
            assert s.can_accept_payment is True
            assert s.can_enroll_staff is False
            assert s.can_drop_reading is False

    def test_create_duplicate_username(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/staff/create",
            data=json.dumps(
                {
                    "username": "superuser",
                    "password": "whatever",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 409

    def test_create_staff_missing_fields(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.post(
            "/staff/staff/create",
            data=json.dumps(
                {
                    "username": "",
                    "password": "",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

        resp = client.post(
            "/staff/staff/create",
            data=json.dumps(
                {
                    "username": "noname",
                    "password": "",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_create_staff_requires_permission(
        self, client: Any, staff_read_only: Staff
    ) -> None:
        client.post(
            "/staff/login",
            data={"username": "reader", "password": "reader", "login": ""},
        )
        resp = client.post(
            "/staff/staff/create",
            data=json.dumps(
                {
                    "username": "shouldfail",
                    "password": "test123",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_staff_list_page(self, client: Any, superuser: Staff) -> None:
        client.post(
            "/staff/login",
            data={"username": "superuser", "password": "superuser", "login": ""},
        )
        resp = client.get("/staff/staff")
        assert resp.status_code == 200
        assert b"superuser" in resp.data
        assert b"can_read_meters" in resp.data or b"Permissions" in resp.data


# =============================================================================
# Billing Computation Tests
# =============================================================================


class TestBillingComputation:
    def test_compute_water_bill_zero(self):
        total, breakdown = compute_water_bill(0)
        assert total == 0.0
        assert all(b["charge"] == 0 for b in breakdown)

    def test_compute_water_bill_first_tier_flat(self):
        # 5 m3: first tier flat 150.00, all others 0
        total, breakdown = compute_water_bill(5)
        assert total == 150.0
        assert breakdown[0]["charge"] == 150.0
        assert breakdown[0]["units"] == 5
        assert all(b["charge"] == 0 for b in breakdown[1:])

    def test_compute_water_bill_exact_tier_boundary(self):
        # 10 m3: first tier flat 150.00 only
        total, breakdown = compute_water_bill(10)
        assert total == 150.0
        assert breakdown[0]["units"] == 10

    def test_compute_water_bill_second_tier(self):
        # 15 m3: 10 flat (150) + 5 * 25 = 125 => 275
        total, breakdown = compute_water_bill(15)
        assert total == 275.0
        assert breakdown[0]["charge"] == 150.0
        assert breakdown[1]["charge"] == 125.0

    def test_compute_water_bill_all_tiers(self):
        # 45 m3: 150 + 10*25 + 10*30 + 10*35 + 5*40
        # = 150 + 250 + 300 + 350 + 200 = 1250
        total, breakdown = compute_water_bill(45)
        assert total == 1250.0
        assert breakdown[0]["charge"] == 150.0
        assert breakdown[1]["charge"] == 250.0
        assert breakdown[2]["charge"] == 300.0
        assert breakdown[3]["charge"] == 350.0
        assert breakdown[4]["charge"] == 200.0

    def test_compute_water_bill_large_consumption(self):
        # 999999: all tiers maxed, last tier takes the rest
        total, breakdown = compute_water_bill(999999)
        assert total > 0
        # Verify last tier has large charge
        assert breakdown[4]["charge"] > 0
        assert breakdown[4]["units"] == 999999 - 40

    def test_penalty_not_applied(self):
        from datetime import datetime

        now = datetime.utcnow()
        reading_ts = now
        assert compute_penalty(reading_ts) == 0.0

    def test_penalty_applied(self):
        from datetime import datetime, timedelta

        old_ts = datetime.utcnow() - timedelta(days=8)
        assert compute_penalty(old_ts) == 15.00

    def test_penalty_with_late_billing(self):
        from datetime import datetime, timedelta

        old_ts = datetime.utcnow() - timedelta(days=8)
        due_dt = old_ts + timedelta(days=7)
        billing = type(
            "obj", (object,), {
                "timestamp": due_dt + timedelta(seconds=1000),
                "payment_timestamp": due_dt + timedelta(seconds=1000),
                "date_paid": due_dt + timedelta(seconds=1000),
            }
        )
        assert compute_penalty(old_ts, billing) == 15.00

    def test_penalty_with_timely_billing(self):
        from datetime import datetime, timedelta

        old_ts = datetime.utcnow() - timedelta(days=8)
        due_dt = old_ts + timedelta(days=7)
        billing = type(
            "obj", (object,), {
                "timestamp": due_dt - timedelta(seconds=100),
                "payment_timestamp": due_dt - timedelta(seconds=100),
                "date_paid": due_dt - timedelta(seconds=100),
            }
        )
        assert compute_penalty(old_ts, billing) == 0.0


# =============================================================================
# API Health
# =============================================================================


class TestAPIHealth:
    def test_health_returns_ok(self, client: Any) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] in ("ok", "degraded")


# =============================================================================
# API Readings Customer Reference
# =============================================================================


class TestAPIReadingsCustomer:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/readings/customer/CUST-001")
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-NOPR-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.get(
                "/api/readings/customer/CUST-001",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_valid_request(
        self, client: Any, sample_reader_token: ApiKey, sample_customer: Customer
    ) -> None:
        resp = client.get(
            "/api/readings/customer/CUST-001",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["customer_number"] == "CUST-001"

    def test_customer_not_found(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/readings/customer/DOES-NOT-EXIST",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 404


# =============================================================================
# API Readings Sync
# =============================================================================


class TestAPISync:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.post(
            "/api/readings/sync",
            data=json.dumps({"readings": []}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-SYNC-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.post(
                "/api/readings/sync",
                data=json.dumps({"readings": []}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_empty_readings(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.post(
            "/api/readings/sync",
            data=json.dumps({"readings": []}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["synced"] == 0
        assert data["total"] == 0

    def test_missing_readings_key(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.post(
            "/api/readings/sync",
            data=json.dumps({}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400

    def test_readings_not_array(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.post(
            "/api/readings/sync",
            data=json.dumps({"readings": "not-an-array"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400

    def test_valid_sync(
        self,
        client: Any,
        sample_reader_token: ApiKey,
        sample_customer: Customer,
    ) -> None:
        now = int(datetime.utcnow().timestamp())
        resp = client.post(
            "/api/readings/sync",
            data=json.dumps(
                {
                    "readings": [
                        {
                            "customer_number": "CUST-001",
                            "reading_value": 500.0,
                            "timestamp": now,
                        }
                    ]
                }
            ),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["synced"] >= 1
        assert len(data["errors"]) == 0

    def test_invalid_customer(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        now = int(datetime.utcnow().timestamp())
        resp = client.post(
            "/api/readings/sync",
            data=json.dumps(
                {
                    "readings": [
                        {
                            "customer_number": "DOES-NOT-EXIST",
                            "reading_value": 500.0,
                            "timestamp": now,
                        }
                    ]
                }
            ),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["errors"]) >= 1


# =============================================================================
# API Readings Upload
# =============================================================================


class TestAPIUpload:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.post(
            "/api/readings/upload",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-UPL-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.post(
                "/api/readings/upload",
                data=json.dumps({}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_missing_customer_number(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.post(
            "/api/readings/upload",
            data=json.dumps({"reading_value": 500.0}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400

    def test_missing_reading_value(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.post(
            "/api/readings/upload",
            data=json.dumps({"customer_number": "CUST-001"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400

    def test_valid_upload(
        self,
        client: Any,
        sample_reader_token: ApiKey,
        sample_customer: Customer,
    ) -> None:
        now = int(datetime.utcnow().timestamp())
        resp = client.post(
            "/api/readings/upload",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "reading_value": 600.0,
                    "timestamp": now,
                }
            ),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["success"] is True
        assert data["reading_id"] is not None

    def test_customer_not_found(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        now = int(datetime.utcnow().timestamp())
        resp = client.post(
            "/api/readings/upload",
            data=json.dumps(
                {
                    "customer_number": "DOES-NOT-EXIST",
                    "reading_value": 500.0,
                    "timestamp": now,
                }
            ),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 404


# =============================================================================
# API Readings Bulk
# =============================================================================


class TestAPIBulk:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/readings/bulk?customer_numbers=CUST-001")
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-BLK-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.get(
                "/api/readings/bulk?customer_numbers=CUST-001",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_missing_customer_numbers(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/readings/bulk",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400

    def test_valid_bulk(
        self,
        client: Any,
        sample_reader_token: ApiKey,
        sample_customer: Customer,
    ) -> None:
        resp = client.get(
            "/api/readings/bulk?customer_numbers=CUST-001",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "customers" in data
        assert "CUST-001" in data["customers"]

    def test_empty_customer_list(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/readings/bulk?customer_numbers=",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400


# =============================================================================
# API Pricing
# =============================================================================


class TestAPIPricing:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/pricing")
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-PRC-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.get(
                "/api/pricing",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_returns_tiers(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/pricing",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "tiers" in data
        assert len(data["tiers"]) == 5
        assert "late_penalty" in data
        assert "due_days" in data


# =============================================================================
# API Key Info
# =============================================================================


class TestAPIKeyInfo:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/key/info")
        assert resp.status_code == 401

    def test_returns_key_and_staff_info(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/key/info",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "api_key" in data
        assert data["api_key"]["is_active"] is True
        assert "staff" in data
        assert "can_read_meters" in data["staff"]


# =============================================================================
# API Customers Changed
# =============================================================================


class TestAPIChanged:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/customers/changed?since=0")
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-CHG-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.get(
                "/api/customers/changed?since=0",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_missing_since_param(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/customers/changed",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400

    def test_valid_request(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        since = int(datetime.utcnow().timestamp()) - 3600
        resp = client.get(
            f"/api/customers/changed?since={since}",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "customer_numbers" in data
        assert "server_time" in data
        assert "total_customers" in data


# =============================================================================
# API NFC
# =============================================================================


class TestAPINFC:
    def test_config_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/nfc/config")
        assert resp.status_code == 401

    def test_config_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-NFCC-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.get(
                "/api/nfc/config",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_config_returns_secret(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/nfc/config",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "nfc_pwd_secret" in data
        assert len(data["nfc_pwd_secret"]) > 0

    def test_tags_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/nfc/tags")
        assert resp.status_code == 401

    def test_tags_returns_list(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/nfc/tags",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "tags" in data

    def test_sync_requires_auth(self, client: Any) -> None:
        resp = client.post(
            "/api/nfc/sync",
            data=json.dumps({"enrollments": []}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_sync_requires_enroll_permission(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.post(
            "/api/nfc/sync",
            data=json.dumps({"enrollments": []}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 403

    def test_sync_valid_enrollment(
        self,
        client: Any,
        staff_enroll: Staff,
        sample_customer: Customer,
    ) -> None:
        key_str = "CRDC-TEST-NFCSYNC-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_enroll.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.post(
                "/api/nfc/sync",
                data=json.dumps(
                    {
                        "enrollments": [
                            {"uid": "04AABBCCDDEEFF00", "customer_number": "CUST-001"}
                        ]
                    }
                ),
                content_type="application/json",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["synced"] == data["total"]
        finally:
            db.session.delete(ak)
            db.session.commit()


# =============================================================================
# API Customer Details
# =============================================================================


class TestAPICustomerDetails:
    def test_requires_auth(self, client: Any) -> None:
        resp = client.get("/api/customer/CUST-001/details")
        assert resp.status_code == 401

    def test_requires_permission(
        self, client: Any, staff_payments_only: Staff
    ) -> None:
        key_str = "CRDC-TEST-DET-" + secrets.token_hex(16).upper()
        ak = ApiKey(key=key_str, staff_id=staff_payments_only.id, is_active=True)
        db.session.add(ak)
        db.session.commit()
        try:
            resp = client.get(
                "/api/customer/CUST-001/details",
                headers={"Authorization": f"Bearer {key_str}"},
            )
            assert resp.status_code == 403
        finally:
            db.session.delete(ak)
            db.session.commit()

    def test_valid_request(
        self, client: Any, sample_reader_token: ApiKey, sample_customer: Customer
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001/details",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "customer" in data
        assert data["customer"]["customer_number"] == "CUST-001"
        assert "readings" in data

    def test_customer_not_found(
        self, client: Any, sample_reader_token: ApiKey
    ) -> None:
        resp = client.get(
            "/api/customer/DOES-NOT-EXIST/details",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 404

    def test_invalid_history_param(
        self, client: Any, sample_reader_token: ApiKey, sample_customer: Customer
    ) -> None:
        resp = client.get(
            "/api/customer/CUST-001/details?history=abc",
            headers={"Authorization": f"Bearer {sample_reader_token.key}"},
        )
        assert resp.status_code == 400


# =============================================================================
# Landing Page
# =============================================================================


class TestLanding:
    def test_landing_page_renders(self, client: Any) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_post_missing_customer_number(self, client: Any) -> None:
        resp = client.post("/", data={"customer_number": "", "last_receipt": ""})
        assert resp.status_code == 200

    def test_post_customer_not_found(self, client: Any) -> None:
        resp = client.post(
            "/",
            data={"customer_number": "NONEXISTENT", "last_receipt": "RCP-123"},
        )
        assert resp.status_code == 200

    def test_post_valid_customer(
        self, client: Any, sample_customer: Customer
    ) -> None:
        resp = client.post(
            "/", data={"customer_number": "CUST-001", "last_receipt": ""}
        )
        assert resp.status_code == 200


# =============================================================================
# Offerings (Landing Page)
# =============================================================================


class TestOfferings:
    def test_offerings_page_renders(self, client: Any) -> None:
        resp = client.get("/offerings")
        assert resp.status_code == 200

    def test_invalid_slug_returns_404(self, client: Any) -> None:
        resp = client.get("/offerings/does-not-exist")
        assert resp.status_code == 404


# =============================================================================
# Billing Portal API
# =============================================================================


class TestBillingPortal:
    def test_lookup_missing_customer_number(self, client: Any) -> None:
        resp = client.post(
            "/billing/api/lookup",
            data=json.dumps({"customer_number": "", "last_receipt": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_lookup_customer_not_found(self, client: Any) -> None:
        resp = client.post(
            "/billing/api/lookup",
            data=json.dumps(
                {"customer_number": "NONEXISTENT", "last_receipt": "RCP-123"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_lookup_valid_no_receipt(
        self, client: Any, sample_customer: Customer
    ) -> None:
        resp = client.post(
            "/billing/api/lookup",
            data=json.dumps({"customer_number": "CUST-001", "last_receipt": ""}),
            content_type="application/json",
        )
        assert resp.status_code in (200, 400)

    def test_confirm_missing_customer_number(self, client: Any) -> None:
        resp = client.post(
            "/billing/api/confirm",
            data=json.dumps({"customer_number": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_confirm_sets_signed_cookie(
        self, client: Any, sample_customer: Customer
    ) -> None:
        resp = client.post(
            "/billing/api/confirm",
            data=json.dumps({"customer_number": "CUST-001"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["customer_number"] == "CUST-001"
        assert data["redirect"] == "/billing/CUST-001"
        cookie = resp.headers.get("Set-Cookie", "")
        assert "billing_session" in cookie

    def test_readings_without_cookie_returns_403(self, client: Any) -> None:
        resp = client.get("/billing/api/CUST-001/readings")
        assert resp.status_code == 403

    def test_payments_without_cookie_returns_403(self, client: Any) -> None:
        resp = client.get("/billing/api/CUST-001/payments")
        assert resp.status_code == 403

    def test_history_without_cookie_returns_403(self, client: Any) -> None:
        resp = client.get("/billing/api/CUST-001/history")
        assert resp.status_code == 403


# =============================================================================
# Billing Page (Cookie Auth)
# =============================================================================


class TestBillingPage:
    def test_billing_page_without_cookie_redirects(
        self, client: Any
    ) -> None:
        resp = client.get("/billing/CUST-001")
        assert resp.status_code == 302

    def test_billing_page_with_valid_cookie(
        self, client: Any, sample_customer: Customer
    ) -> None:
        from itsdangerous import URLSafeTimedSerializer

        s = URLSafeTimedSerializer("test-secret-key-for-testing", salt="billing-cookie")
        signed = s.dumps(
            {"customer_number": "CUST-001", "receipt_number": "RCP-TEST"}
        )
        client.set_cookie("billing_session", signed)
        resp = client.get("/billing/CUST-001")
        assert resp.status_code == 200


# =============================================================================
# Auth Redirects
# =============================================================================


class TestAuthRedirects:
    def test_login_redirects_to_staff_login(self, client: Any) -> None:
        resp = client.get("/login")
        assert resp.status_code == 302
        assert "/staff/login" in resp.headers["Location"]

    def test_logout_redirects_to_staff_logout(self, client: Any) -> None:
        resp = client.get("/logout")
        assert resp.status_code == 302
        assert "/staff/logout" in resp.headers["Location"]


# =============================================================================
# Staff Customer CRUD
# =============================================================================


class TestStaffCustomerCRUD:
    def _login(self, client: Any, user: str, pw: str) -> None:
        client.post(
            "/staff/login",
            data={"username": user, "password": pw, "login": ""},
        )

    def test_create_customer(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            "/staff/customers/create",
            data=json.dumps(
                {
                    "customer_number": "NEW-CUST-001",
                    "name": "Test Customer",
                    "address": "123 Test St",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["customer_number"] == "NEW-CUST-001"

    def test_create_duplicate_customer_number(
        self, client: Any, superuser: Staff, sample_customer: Customer
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            "/staff/customers/create",
            data=json.dumps(
                {
                    "customer_number": "CUST-001",
                    "name": "Duplicate",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code in (400, 409)

    def test_create_customer_unauthorized(
        self, client: Any, staff_read_only: Staff
    ) -> None:
        self._login(client, "reader", "reader")
        resp = client.post(
            "/staff/customers/create",
            data=json.dumps({"customer_number": "TEST", "name": "Test"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_edit_customer(
        self, client: Any, superuser: Staff, sample_customer: Customer
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            f"/staff/manage-customers/{sample_customer.id}/edit",
            data=json.dumps({"name": "Updated Name"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_edit_customer_not_found(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            "/staff/manage-customers/99999/edit",
            data=json.dumps({"name": "Ghost"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_toggle_active(
        self, client: Any, superuser: Staff, sample_customer: Customer
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            f"/staff/manage-customers/{sample_customer.id}/toggle-active",
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "is_active" in data

    def test_toggle_active_not_found(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            "/staff/manage-customers/99999/toggle-active",
            content_type="application/json",
        )
        assert resp.status_code == 404


# =============================================================================
# Staff Edit
# =============================================================================


class TestStaffEdit:
    def _login(self, client: Any, user: str, pw: str) -> None:
        client.post(
            "/staff/login",
            data={"username": user, "password": pw, "login": ""},
        )

    def test_get_staff_details(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.get(f"/staff/staff/{superuser.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["username"] == "superuser"

    def test_get_staff_not_found(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.get("/staff/staff/99999")
        assert resp.status_code == 404

    def test_edit_staff_update_name(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            f"/staff/staff/{superuser.id}",
            data=json.dumps({"username": "superuser", "name": "Updated Superuser"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["name"] == "Updated Superuser"

    def test_edit_staff_duplicate_username(
        self, client: Any, superuser: Staff, staff_read_only: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.post(
            f"/staff/staff/{superuser.id}",
            data=json.dumps({"username": "reader", "name": "Collision"}),
            content_type="application/json",
        )
        assert resp.status_code == 409


# =============================================================================
# Cashier Tally
# =============================================================================


class TestCashierTally:
    def _login(self, client: Any, user: str, pw: str) -> None:
        client.post(
            "/staff/login",
            data={"username": user, "password": pw, "login": ""},
        )

    def test_tally_requires_auth(self, client: Any) -> None:
        resp = client.get("/staff/cashier-tally")
        assert resp.status_code == 302

    def test_tally_requires_permission(
        self, client: Any, staff_read_only: Staff
    ) -> None:
        self._login(client, "reader", "reader")
        resp = client.get("/staff/cashier-tally")
        assert resp.status_code == 302

    def test_tally_page_renders(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        resp = client.get("/staff/cashier-tally")
        assert resp.status_code == 200

    def test_tally_with_date_range(
        self, client: Any, superuser: Staff
    ) -> None:
        self._login(client, "superuser", "superuser")
        today = datetime.utcnow().strftime("%Y-%m-%d")
        resp = client.get(
            f"/staff/cashier-tally?period=daily&date={today}"
        )
        assert resp.status_code == 200
