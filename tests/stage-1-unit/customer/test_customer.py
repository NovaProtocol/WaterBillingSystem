class TestCustomer:
    def test_identify(self, client):
        r = client.get('/customer/')
        assert r.status_code == 200
    def test_login_page(self, client):
        r = client.get('/customer/login')
        assert r.status_code == 200
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_context_requires_session(self, client):
        r = client.get('/customer/api/context')
        assert r.status_code == 401
    def test_readings_requires_session(self, client):
        r = client.get('/customer/api/readings')
        assert r.status_code == 401
    def test_login_requires_account_number(self, client):
        r = client.post('/customer/api/login', json={})
        assert r.status_code == 400
    def test_old_billing_url_redirects(self, client):
        r = client.get('/customer/billing/1')
        assert r.status_code == 301
        assert r.headers['Location'].endswith('/customer/')
    def test_maintenance_requires_session(self, client):
        r = client.get('/customer/maintenance')
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/customer/login')
    def test_report_requires_session(self, client):
        r = client.get('/customer/report')
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/customer/login')
