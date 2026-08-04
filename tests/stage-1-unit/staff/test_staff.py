class TestStaff:
    def test_login(self, client):
        r = client.get('/staff/login')
        assert r.status_code in (200, 302)
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_dashboard_requires_login(self, client):
        r = client.get('/staff/dashboard', follow_redirects=False)
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/staff/login')
    def test_login_bad_credentials(self, client):
        r = client.post('/staff/login', data={'username': 'nope', 'password': 'nope'})
        assert r.status_code == 200
        assert 'Invalid credentials' in r.text
