class TestDev:
    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code == 200
    def test_index(self, client):
        r = client.get('/developer/', follow_redirects=False)
        assert r.status_code in (302, 403)
    def test_pages_require_superuser(self, client):
        r = client.get('/developer/backup')
        assert r.status_code == 403
    def test_auth_requires_superuser(self, client):
        r = client.get('/developer/auth')
        assert r.status_code == 403
