class TestApi:
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_api_root(self, client):
        r = client.get('/api/')
        assert r.status_code == 200
