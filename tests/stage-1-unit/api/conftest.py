import os, sys
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'test-secret')
os.environ['NFC_PWD_SECRET'] = os.environ.get('NFC_PWD_SECRET', 'a' * 64)
os.environ['XENDIT_API_KEY'] = os.environ.get('XENDIT_API_KEY', 'test')
os.environ['XENDIT_WEBHOOK_TOKEN'] = os.environ.get('XENDIT_WEBHOOK_TOKEN', 'test')
os.environ['CACHE_TYPE'] = os.environ.get('CACHE_TYPE', 'SimpleCache')
os.environ['DEPLOYMENT_TYPE'] = os.environ.get('DEPLOYMENT_TYPE', 'DEBUG')
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))
from app import app
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:
        yield c
