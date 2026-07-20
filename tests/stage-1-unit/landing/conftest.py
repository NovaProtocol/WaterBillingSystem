import os, sys
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
sys.path.insert(0, os.path.join(BASE, 'landing-page'))
from app import create_app
import pytest
@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()
