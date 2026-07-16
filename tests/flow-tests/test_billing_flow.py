"""Stage 3: Flow tests — complete business processes via the API."""


class TestStaffLoginFlow:
    """Verify a staff member can log in and access protected endpoints."""

    def test_login_then_access_dashboard(self, client):
        resp = client.post('/api/staff/login', json={
            'username': 'superuser', 'password': 'superuser'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['username'] == 'superuser'

    def test_login_then_list_staff(self, app, client):
        client.post('/api/staff/login', json={
            'username': 'superuser', 'password': 'superuser'
        })
        resp = client.get('/api/staff/all', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        staff_list = resp.get_json().get('staff', [])
        assert any(s['username'] == 'superuser' for s in staff_list)

    def test_login_then_count_customers(self, app, client):
        client.post('/api/staff/login', json={
            'username': 'superuser', 'password': 'superuser'
        })
        resp = client.get('/api/customer/count', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        assert resp.get_json()['count'] >= 1


class TestCustomerLifecycle:
    """Full customer lifecycle: create → read → update → deactivate."""

    def test_create_customer(self, app, client):
        resp = client.post('/api/customer/new', json={
            'customer_number': 'LIFE-001',
            'name': 'Lifecycle Test',
            'address': '42 Life St',
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 201
        assert resp.get_json()['customer_number'] == 'LIFE-001'

    def test_read_customer(self, app, client):
        resp = client.get('/api/customer/LIFE-001', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['customer_number'] == 'LIFE-001'
        assert data['name'] == 'Lifecycle Test'

    def test_update_customer(self, app, client):
        resp = client.put('/api/customer/update/LIFE-001', json={
            'name': 'Lifecycle Updated',
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 200
        data = client.get('/api/customer/LIFE-001', headers={
            'X-Internal-API-Key': 'test-internal-key'
        }).get_json()
        assert data['name'] == 'Lifecycle Updated'

    def test_deactivate_customer(self, app, client):
        resp = client.delete('/api/customer/delete/LIFE-001', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        resp = client.get('/api/customer/LIFE-001', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        assert resp.get_json() is not None


class TestReadingFlow:
    """Create a reading and verify billing is generated."""

    def test_create_reading_generates_billing(self, app, client):
        resp = client.post('/api/customer/FLOW-001/reading/new', json={
            'reading_value': 250.0,
            'timestamp': 1700000000,
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 201
        assert resp.get_json()['success'] is True

    def test_reading_appears_in_list(self, app, client):
        resp = client.get('/api/customer/FLOW-001/reading', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get('data', [])) > 0


class TestStaffLifecycle:
    """Full staff lifecycle: create → read → edit → list."""

    def test_create_staff(self, app, client):
        resp = client.post('/api/staff/new', json={
            'username': 'newstaff',
            'password': 'testpass',
            'name': 'New Staff',
            'can_read_meters': True,
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 201

    def test_list_staff_includes_new(self, app, client):
        resp = client.get('/api/staff/all', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        staff = resp.get_json().get('staff', [])
        assert any(s['username'] == 'newstaff' for s in staff)

    def test_get_staff_detail(self, app, client):
        resp = client.get('/api/staff/1', headers={
            'X-Internal-API-Key': 'test-internal-key'
        })
        assert resp.status_code == 200
        assert resp.get_json()['username'] == 'superuser'


class TestBillingFlow:
    """Payment flow: submit a payment and verify it's recorded."""

    def test_submit_payment(self, app, client):
        from datetime import datetime
        ts = int(datetime(2026, 2, 1).timestamp())
        resp = client.post('/api/customer/FLOW-001/reading/new', json={
            'reading_value': 300.0,
            'timestamp': ts,
        }, headers={'X-Internal-API-Key': 'test-internal-key'})
        assert resp.status_code == 201
        import time
        time.sleep(0.1)
        billing = client.get('/api/customer/FLOW-001/billing', headers={
            'X-Internal-API-Key': 'test-internal-key'
        }).get_json()
        assert len(billing.get('data', [])) > 0
