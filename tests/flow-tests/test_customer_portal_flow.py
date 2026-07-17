"""Full end-to-end flow: customer portal through the API.

Verifies that every field the billing template expects is present
in the API response with the correct format.
"""

from datetime import datetime


class TestCustomerLoginAndBilling:
    """Customer logs in, sees billing page with complete data."""

    def test_customer_login_returns_correct_data(self, app, client):
        resp = client.post('/api/customer/login', json={
            'account_number': 'FLOW-001',
            'registered_name': 'Flow Test Customer',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['customer_number'] == 'FLOW-001'
        assert data['customer']['name'] == 'Flow Test Customer'
        assert data['customer']['address'] == '42 Flow Street, Testville'
        assert data['customer']['contact_number'] == '09171234567'
        assert data['customer']['email'] == 'flow@test.com'
        assert data['customer']['meter_serial_number'] == 'MTR-001'

    def test_billing_api_returns_all_template_fields(self, app, client):
        """The customer_info endpoint must return every field the billing.html template uses."""
        resp = client.get('/api/customer/FLOW-001', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()

        assert data['customer_number'] == 'FLOW-001'
        assert data['name'] == 'Flow Test Customer'
        assert data['address'] == '42 Flow Street, Testville'

        # Template uses: customer.name, customer.address, etc.
        assert 'customer_number' in data
        assert 'name' in data
        assert 'address' in data
        assert 'contact_number' in data
        assert 'email' in data

        # Template uses: consumption, original_water_bill, pricing_tiers
        assert isinstance(data.get('consumption'), (int, float))
        assert isinstance(data.get('original_water_bill'), (int, float))
        assert isinstance(data.get('pricing_tiers'), list)
        assert len(data['pricing_tiers']) > 0

        # Template uses: unpaid_bills[].month, .amount, .penalty
        assert isinstance(data.get('unpaid_bills'), list)
        if data['unpaid_bills']:
            b = data['unpaid_bills'][0]
            assert 'month' in b
            assert 'amount' in b
            assert 'penalty' in b

        # Template uses: total_due, carryover, cumulative_balance
        assert isinstance(data.get('total_due'), (int, float))
        assert isinstance(data.get('carryover'), (int, float))
        assert isinstance(data.get('cumulative_balance'), (int, float))

        # Template uses: due_date (nullable)
        assert 'due_date' in data
        assert 'days_remaining' in data

        # Template uses: latest_reading.reader, .reading_value, .timestamp
        lr = data.get('latest_reading')
        assert lr is not None
        assert 'reading_value' in lr
        assert 'reader' in lr
        assert 'timestamp' in lr

        # Template uses: last_reading.reader, .reading_value, .timestamp
        lr2 = data.get('last_reading')
        assert lr2 is not None
        assert 'reading_value' in lr2
        assert 'reader' in lr2

        # Template uses: recent_payments[].receipt_number, .paid_amount, .timestamp
        assert isinstance(data.get('recent_payments'), list)

        # Template uses: bill_breakdown[].label, .units, .charge
        assert isinstance(data.get('bill_breakdown'), list)
        if data['bill_breakdown']:
            bd = data['bill_breakdown'][0]
            assert 'label' in bd
            assert 'units' in bd
            assert 'charge' in bd

        # Template uses: payment_methods[].code, .label, .fee_percent, etc.
        assert isinstance(data.get('payment_methods'), list)

    def test_billing_api_has_correct_pricing_tiers(self, app, client):
        resp = client.get('/api/config/pricing', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tiers' in data
        assert len(data['tiers']) > 0
        for tier in data['tiers']:
            assert 'from_unit' in tier or 'min' in tier
            assert 'to_unit' in tier or 'max' in tier
            assert 'rate' in tier
            assert 'type' in tier or 'label' in tier


class TestStaffPortalApiContract:
    """The staff portal API must return all fields the templates expect."""

    def test_customer_all_returns_all_template_fields(self, app, client):
        """Manage customers template uses: customer_number, name, address, phase,
        block, street, contact_number, email, is_active, id, meter_serial_number,
        x_coordinate, y_coordinate, nfc_uid, total_due, cumulative_balance"""
        resp = client.get('/api/customer/all', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'data' in data
        assert 'meta' in data

        for c in data['data']:
            assert 'id' in c, f"Missing 'id' in customer {c.get('customer_number')}"
            assert 'customer_number' in c
            assert 'name' in c
            assert 'address' in c
            assert 'contact_number' in c
            assert 'email' in c
            assert 'phase' in c
            assert 'block' in c
            assert 'street' in c
            assert 'is_active' in c
            assert 'meter_serial_number' in c
            assert 'x_coordinate' in c
            assert 'y_coordinate' in c
            assert 'nfc_uid' in c
            assert 'cumulative_balance' in c, f"Missing 'cumulative_balance' in {c.get('customer_number')}"
            assert 'total_due' in c, f"Missing 'total_due' in {c.get('customer_number')}"
            assert isinstance(c['total_due'], (int, float))

        # Verify specific seeded data
        c1 = next(c for c in data['data'] if c['customer_number'] == 'FLOW-001')
        assert c1['name'] == 'Flow Test Customer'
        assert c1['nfc_uid'] == 'A1B2C3D4'
        assert c1['is_active'] is True
        assert c1['cumulative_balance'] == 50.0
        assert c1['total_due'] > 0  # Has unpaid bill

        c2 = next(c for c in data['data'] if c['customer_number'] == 'FLOW-002')
        assert c2['is_active'] is False

    def test_customer_all_meta(self, app, client):
        resp = client.get('/api/customer/all', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        data = resp.get_json()
        meta = data['meta']
        assert 'current_page' in meta
        assert 'page_size' in meta
        assert 'total_items' in meta
        assert 'total_pages' in meta
        assert meta['total_items'] >= 2

    def test_staff_all_returns_required_fields(self, app, client):
        """Staff list template expects: id, name, username, email, contact_number,
        is_active, can_read_meters, can_accept_payment, etc."""
        resp = client.get('/api/staff/all', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'staff' in data
        for s in data['staff']:
            assert 'id' in s
            assert 'name' in s
            assert 'username' in s
            assert 'email' in s
            assert 'contact_number' in s
            assert 'is_active' in s
            assert 'can_read_meters' in s
            assert 'can_accept_payment' in s
            assert 'can_enroll_customer' in s
            assert 'can_drop_reading' in s
            assert 'can_drop_payment' in s
            assert 'can_enroll_staff' in s
            assert 'can_manage_billing' in s

    def test_staff_info_returns_all_fields(self, app, client):
        resp = client.get('/api/staff/info', headers={
            'X-Internal-API-Key': 'test-internal-key',
            'X-Staff-ID': '1',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['auth_type'] == 'internal_key'
        s = data['staff']
        assert 'id' in s
        assert 'username' in s
        assert 'name' in s
        assert 'email' in s
        assert 'contact_number' in s
        assert 'is_active' in s
        assert 'can_read_meters' in s

    def test_api_keys_return_staff_nested(self, app, client):
        """Manage reading template expects t.staff.name and t.staff.username."""
        resp = client.get('/api/staff/1/api-keys', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        for k in data.get('keys', []):
            assert 'staff' in k, f"Missing nested 'staff' object in key {k.get('id')}"
            if k['staff']:
                assert 'name' in k['staff']
                assert 'username' in k['staff']

    def test_cashier_tally_returns_template_fields(self, app, client):
        resp = client.get('/api/staff/1/cashier-tally', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        # Template uses: nav_date, group_days, start_date, end_date, display,
        # prev_date, next_date, is_today, tally, use_matrix
        assert 'nav_date' in data
        assert 'group_days' in data
        assert 'start_date' in data
        assert 'end_date' in data
        assert 'display' in data
        assert 'prev_date' in data
        assert 'next_date' in data
        assert 'is_today' in data
        assert 'tally' in data

    def test_staff_login_returns_permissions(self, app, client):
        resp = client.post('/api/staff/login', json={
            'username': 'superuser', 'password': 'superuser'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'id' in data
        assert 'username' in data
        assert 'name' in data
        assert 'email' in data
        assert 'contact_number' in data
        assert 'is_active' in data
        assert 'can_read_meters' in data
        assert data['can_read_meters'] is True
        assert data['username'] == 'superuser'


class TestReadingAndBillingFlow:
    """Create readings, verify billing is generated with correct data."""

    def test_create_reading_returns_success(self, app, client):
        resp = client.post('/api/customer/FLOW-001/reading/new', json={
            'reading_value': 250.0,
            'timestamp': int(datetime(2026, 2, 1).timestamp()),
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert 'reading_id' in data
        assert data['customer_number'] == 'FLOW-001'

    def test_reading_list_returns_paginated(self, app, client):
        resp = client.get('/api/customer/FLOW-001/reading', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'data' in data
        assert 'meta' in data
        assert len(data['data']) > 0
        assert data['meta']['total_items'] > 0

    def test_billing_list_after_reading(self, app, client):
        resp = client.get('/api/customer/FLOW-001/billing', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'data' in data
        assert 'meta' in data
        for b in data['data']:
            assert 'id' in b
            assert 'reading_id' in b
            assert 'month' in b
            assert 'billed_amount' in b
            assert 'consumption' in b
            assert 'is_paid' in b
            assert 'penalty' in b
            assert 'paid_amount' in b

    def test_submit_payment(self, app, client):
        """Submit payment and verify it is recorded."""
        ts = int(datetime(2026, 3, 1).timestamp())
        resp = client.post('/api/customer/FLOW-001/reading/new', json={
            'reading_value': 300.0, 'timestamp': ts,
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 201

        billing = client.get('/api/customer/FLOW-001/billing', headers={
            'X-Internal-API-Key': 'test-internal-key'
        }).get_json()
        unpaid = [b for b in billing['data'] if not b['is_paid']]
        assert len(unpaid) > 0

        total_due = sum(b['billed_amount'] + b['penalty'] - b['paid_amount']
                       for b in unpaid)
        if total_due > 0:
            pay_resp = client.post('/api/customer/FLOW-001/billing/new', json={
                'amount': total_due, 'staff_id': 1,
            }, headers={'X-Internal-API-Key': 'test-internal-key'})
            assert pay_resp.status_code == 201


class TestDebtActivationFlow:
    """Customer deactivation/reactivation flow."""

    def test_deactivate_and_reactivate(self, app, client):
        resp = client.delete('/api/customer/delete/FLOW-002', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'is_active' in data
        # FLOW-002 starts inactive (is_active=False). Toggle makes it active.
        assert data['is_active'] is True

        resp = client.delete('/api/customer/delete/FLOW-002', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_active'] is False
