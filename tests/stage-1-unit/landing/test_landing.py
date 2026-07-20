class TestLanding:
    def test_home(self, client):
        r = client.get('/')
        assert r.status_code == 200
    def test_offerings(self, client):
        r = client.get('/offerings')
        assert r.status_code == 200
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_model_detail(self, client):
        r = client.get('/offerings/catherine-4')
        assert r.status_code == 200
    def test_model_404(self, client):
        r = client.get('/offerings/nope')
        assert r.status_code == 404
