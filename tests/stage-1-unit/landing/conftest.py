import os, sys
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
sys.path.insert(0, os.path.join(BASE, 'landing-page'))
from app import app
import pytest
from fastapi.testclient import TestClient
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
