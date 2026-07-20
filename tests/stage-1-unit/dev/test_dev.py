class TestDev:
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_index(self, client):
        r = client.get('/developer/')
        assert r.status_code in (200, 403)
