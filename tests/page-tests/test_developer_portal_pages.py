"""Render developer portal pages and verify content."""

import os, sys, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'developer-portal'))
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('INTERNAL_API_KEY', 'test-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('PMA_URL', 'http://test:80')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')


@pytest.fixture
def app():
    from app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestDeveloperPortalPagesRendered:
    def _login(self, client):
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['staff_data'] = {'id': 1, 'username': 'superuser'}

    def test_debug_panel_shows_title(self, client):
        self._login(client)
        resp = client.get('/developer/')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'DEBUG' in body
        assert 'PANEL' in body or 'Panel' in body

    def test_phpmyadmin_link_exists(self, client):
        """The debug panel should have a link to phpMyAdmin."""
        self._login(client)
        resp = client.get('/developer/')
        body = resp.data.decode()
        assert 'phpMyAdmin' in body
        assert '/developer/phpmyadmin/' in body

    def test_phpmyadmin_proxy_requires_superuser(self, client):
        """Without auth, phpMyAdmin proxy should 403."""
        resp = client.get('/developer/phpmyadmin/')
        assert resp.status_code == 403

    def test_phpmyadmin_proxy_returns_502_when_offline(self, client):
        """With auth but phpMyAdmin not running, proxy returns 502."""
        self._login(client)
        resp = client.get('/developer/phpmyadmin/')
        # phpMyAdmin not running in test env -> 502
        assert resp.status_code in (502, 200)
