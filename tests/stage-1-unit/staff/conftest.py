import os, sys
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['INTERNAL_API_KEY'] = 'test'
os.environ['API_BASE_URL'] = 'http://api:8008'
os.environ['CACHE_TYPE'] = 'SimpleCache'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
sys.path.insert(0, os.path.join(BASE, 'staff-portal'))
from app import create_app
import pytest
@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()
