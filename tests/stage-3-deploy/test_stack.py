import urllib.request

class TestPublicEndpoints:
    def test_landing_page(self, public):
        r = urllib.request.urlopen(f'{public}/')
        assert r.status == 200
        body = r.read().decode()
        assert 'COTTA' in body or 'Cotta' in body

    def test_customer_portal(self, public):
        r = urllib.request.urlopen(f'{public}/customer/')
        assert r.status == 200

    def test_health(self, public):
        r = urllib.request.urlopen(f'{public}/health')
        assert r.status == 200

    def test_webhook_not_found(self, public):
        try:
            r = urllib.request.urlopen(f'{public}/webhook/nonexistent')
            assert r.status in (404, 405)
        except urllib.error.HTTPError as e:
            assert e.code in (404, 405)

class TestPrivateEndpoints:
    def test_staff_login(self, private):
        """Unauthenticated request is redirected by the Caddy forward-auth gate"""
        try:
            r = urllib.request.urlopen(f'{private}/staff/login')
            assert r.status == 200
        except urllib.error.HTTPError as e:
            assert e.code in (302, 307)

    def test_dev_portal(self, private):
        try:
            r = urllib.request.urlopen(f'{private}/developer/')
            assert r.status == 200
        except urllib.error.HTTPError as e:
            assert e.code in (302, 307)

    def test_documentation(self, private):
        try:
            r = urllib.request.urlopen(f'{private}/documentation/')
            assert r.status == 200
        except urllib.error.HTTPError as e:
            assert e.code in (301, 302, 404)
