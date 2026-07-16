import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'developer-portal'))

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INTERNAL_API_KEY', 'test-internal-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('PMA_URL', 'http://test:80')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')

@pytest.fixture
def app():
    from app import create_app
    application = create_app()
    return application

@pytest.fixture
def client(app):
    return app.test_client()

class TestDeveloperPortal:
    def test_health(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
