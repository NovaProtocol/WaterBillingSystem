"""Render every landing page and verify 200 status."""

import os, sys, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'landing-page'))
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')


@pytest.fixture
def app():
    from app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestLandingPages:
    def test_home(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_offerings(self, client):
        resp = client.get('/offerings')
        assert resp.status_code == 200

    def test_model_page(self, client):
        resp = client.get('/offerings/tristen')
        assert resp.status_code == 200

    def test_post_customer_lookup(self, client):
        resp = client.post('/', data={'customer_number': 'TEST-001'}, follow_redirects=False)
        assert resp.status_code == 302
