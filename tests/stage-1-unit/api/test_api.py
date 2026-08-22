class TestApi:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_api_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_api_staff_login(self, client):
        r = client.post("/api/staff/login", json={"username": "superuser", "password": "superuser"})
        assert r.status_code in (200, 401)
        if r.status_code == 200:
            assert r.json()["username"] == "superuser"

    def test_requires_auth(self, client):
        r = client.get("/api/customer/count")
        assert r.status_code == 401

    def test_internal_key(self, client):
        r = client.get("/api/customer/count", headers={"X-Internal-API-Key": "test"})
        assert r.status_code == 200

    def test_openapi(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "/api/staff/login" in str(r.json()["paths"])

    def test_preflight_runs_on_startup(self, client):
        # lifespan boots preflight; if it crashed, TestClient would fail
        r = client.get("/api/health")
        assert r.status_code == 200
