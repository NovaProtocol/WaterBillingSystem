import json


class TestHealth:
    def test_health(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.get_json()['status'] in ('ok', 'degraded')


class TestStaffLogin:
    def test_login_valid(self, client, app):
        resp = client.post('/api/staff/login', json={
            'username': 'superuser', 'password': 'superuser'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['username'] == 'superuser'
        assert data['can_read_meters'] is True

    def test_login_invalid_password(self, client):
        resp = client.post('/api/staff/login', json={
            'username': 'superuser', 'password': 'wrong'
        })
        assert resp.status_code == 401

    def test_login_invalid_user(self, client):
        resp = client.post('/api/staff/login', json={
            'username': 'nobody', 'password': 'x'
        })
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post('/api/staff/login', json={})
        assert resp.status_code == 400


class TestStaffInfo:
    def test_staff_info_with_api_key(self, client, api_key):
        resp = client.get('/api/staff/info', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['auth_type'] == 'api_key'
        assert data['staff']['username'] == 'superuser'

    def test_staff_info_with_internal_key(self, client):
        resp = client.get('/api/staff/info', headers={
            'X-Internal-API-Key': 'test-internal-key',
            'X-Staff-ID': '1'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['auth_type'] == 'internal_key'

    def test_staff_info_no_auth(self, client):
        resp = client.get('/api/staff/info')
        assert resp.status_code == 401


class TestCustomer:
    def test_customer_count(self, client, api_key):
        resp = client.get('/api/customer/count', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        assert resp.get_json()['count'] >= 1

    def test_customer_all(self, client, api_key):
        resp = client.get('/api/customer/all', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'data' in data
        assert 'meta' in data

    def test_customer_get(self, client, api_key):
        resp = client.get('/api/customer/TEST-001', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['customer_number'] == 'TEST-001'

    def test_customer_get_not_found(self, client, api_key):
        resp = client.get('/api/customer/NONEXIST', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 404

    def test_customer_new(self, client, api_key):
        resp = client.post('/api/customer/new', json={
            'customer_number': 'NEW-001',
            'name': 'New Customer',
            'address': '456 New St',
        }, headers={'Authorization': f'Bearer {api_key}'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['customer_number'] == 'NEW-001'

    def test_customer_login(self, client, app):
        resp = client.post('/api/customer/login', json={
            'account_number': 'TEST-001',
            'registered_name': 'Test Customer',
        })
        assert resp.status_code == 200
        assert resp.get_json()['customer_number'] == 'TEST-001'

    def test_customer_login_not_found(self, client):
        resp = client.post('/api/customer/login', json={
            'account_number': 'NONEXIST'
        })
        assert resp.status_code == 404

    def test_customers_changed(self, client, api_key):
        resp = client.get('/api/customers/changed?since=0', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'customer_numbers' in data


class TestReadings:
    def test_customer_reading_new(self, client, api_key):
        resp = client.post('/api/customer/TEST-001/reading/new', json={
            'reading_value': 150.5,
            'timestamp': 1700000000,
        }, headers={'Authorization': f'Bearer {api_key}'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True

    def test_customer_reading_list(self, client, api_key):
        resp = client.get('/api/customer/TEST-001/reading', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'data' in data
        assert 'meta' in data


class TestBilling:
    def test_customer_billing(self, client, api_key):
        resp = client.get('/api/customer/TEST-001/billing', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'data' in data


class TestConfig:
    def test_pricing(self, client, api_key):
        resp = client.get('/api/config/pricing', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tiers' in data

    def test_nfc_secret(self, client, api_key):
        resp = client.get('/api/config/nfc_secret', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 200


class TestPermissions:
    def test_unauthorized_no_key(self, client):
        resp = client.get('/api/customer/count')
        assert resp.status_code == 401

    def test_forbidden_no_permission(self, client, app):
        from models import Staff, ApiKey
        with app.app_context():
            from app import db
            staff = Staff(username='noperm', name='No Perm',
                          password=b'noperm', is_active=True)
            db.session.add(staff)
            db.session.flush()
            key = ApiKey(key='CRDC-NOPERM1234567890', label='noperm', staff_id=staff.id)
            db.session.add(key)
            db.session.commit()
            api_key = key.key
        resp = client.get('/api/customer/count', headers={
            'Authorization': f'Bearer {api_key}'
        })
        assert resp.status_code == 403
