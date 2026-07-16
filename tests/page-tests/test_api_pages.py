"""Stage 2: Page render tests — verify the API renders correct HTML/JSON pages."""


class TestHealthPage:
    def test_health_endpoint_renders(self, page, api_url):
        resp = page.goto(f'{api_url}/health')
        assert resp.status == 200
        body = page.content()
        assert 'ok' in body or 'degraded' in body

    def test_health_returns_json(self, api_url):
        import requests
        r = requests.get(f'{api_url}/health')
        assert r.status_code == 200
        data = r.json()
        assert 'status' in data
        assert 'db' in data


class TestLoginPage:
    def test_staff_login_returns_json(self, api_url):
        import requests
        r = requests.post(f'{api_url}/api/staff/login', json={
            'username': 'superuser', 'password': 'superuser'
        })
        assert r.status_code == 200
        data = r.json()
        assert data['username'] == 'superuser'
        assert data['can_read_meters'] is True

    def test_customer_login_page_get_returns_401(self, page, api_url):
        resp = page.goto(f'{api_url}/api/customer/login',
                          wait_until='networkidle')
        assert resp.status == 401


class TestCustomerPage:
    def test_customer_list_page(self, page, api_url):
        resp = page.goto(f'{api_url}/api/customer/all',
                          wait_until='networkidle')
        assert resp.status == 401
        body = page.content()
        assert 'Authentication required' in body


class TestStaffPage:
    def test_staff_info_no_auth(self, page, api_url):
        resp = page.goto(f'{api_url}/api/staff/info',
                          wait_until='networkidle')
        assert resp.status == 401
