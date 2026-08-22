class TestDev:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_index(self, client):
        r = client.get("/developer/", follow_redirects=False)
        assert r.status_code in (302, 403)

    def test_pages_require_superuser(self, client):
        r = client.get("/developer/backup", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/staff/login")

    def test_auth_requires_superuser(self, client):
        r = client.get("/developer/auth", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/staff/login")
