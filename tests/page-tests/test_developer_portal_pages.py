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
    def test_debug_panel_shows_title(self, client):
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['staff_data'] = {'id': 1, 'username': 'superuser', 'is_superuser': True}
        resp = client.get('/developer/')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'DEBUG' in body
        assert 'PANEL' in body or 'Panel' in body
