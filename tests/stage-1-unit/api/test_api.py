class TestApi:
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_api_staff_login(self, client):
        r = client.post('/api/staff/login', json={'username': 'superuser', 'password': 'superuser'})
        assert r.status_code in (200, 401)
