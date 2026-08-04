import os, sys
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['INTERNAL_API_KEY'] = 'test'
os.environ['API_BASE_URL'] = 'http://api:8008'
os.environ['CACHE_TYPE'] = 'SimpleCache'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
sys.path.insert(0, os.path.join(BASE, 'staff-portal'))
from app import app
import pytest
from fastapi.testclient import TestClient
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
