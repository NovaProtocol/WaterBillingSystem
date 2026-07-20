class TestCustomer:
    def test_identify(self, client):
        r = client.get('/customer/')
        assert r.status_code == 200
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
