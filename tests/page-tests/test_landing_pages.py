"""Render landing pages and verify content."""

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


class TestLandingPagesRendered:
    """Render landing pages and verify expected content."""

    def test_home_shows_company_name(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'COTTA' in body or 'Cotta' in body
        assert 'REALTY' in body or 'Realty' in body

    def test_home_has_view_offerings_button(self, client):
        resp = client.get('/')
        body = resp.data.decode()
        assert 'View Offerings' in body or 'offerings' in body.lower()

    def test_home_has_check_my_bill_button(self, client):
        resp = client.get('/')
        body = resp.data.decode()
        assert 'Check My Bill' in body or 'bill' in body.lower()

    def test_offerings_page_shows_models(self, client):
        resp = client.get('/offerings')
        assert resp.status_code == 200
        body = resp.data.decode()
        # At least one model name should appear
        assert any(name in body for name in ['Tristen', 'Claire', 'Amelia', 'Sophia'])

    def test_model_detail_page(self, client):
        resp = client.get('/offerings/tristen')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Tristen' in body

    def test_post_customer_lookup_redirects(self, client):
        resp = client.post('/', data={'customer_number': 'C001'},
                          follow_redirects=False)
        assert resp.status_code == 302

    def test_home_has_footer(self, client):
        resp = client.get('/')
        body = resp.data.decode()
        assert 'COTTA REALTY' in body or 'Cotta' in body
