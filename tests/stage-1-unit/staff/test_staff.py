class TestStaff:
    def test_login(self, client):
        r = client.get('/staff/login')
        assert r.status_code in (200, 302)
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
