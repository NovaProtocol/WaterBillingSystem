import os, sys, types
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['INTERNAL_API_KEY'] = 'test'
os.environ['API_BASE_URL'] = 'http://api:8008'
os.environ['GATEKEEPER_INTERNAL'] = 'http://gatekeeper:7000'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
os.environ['DEBUG'] = 'true'
m = types.ModuleType('shared.gatekeeper')
m.gatekeeper_check = lambda: None
sys.modules['shared.gatekeeper'] = m
sys.path.insert(0, os.path.join(BASE, 'customer-portal'))
from app import create_app
import pytest
@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()
