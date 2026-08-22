import os
import sys

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "..")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEBUG"] = "true"
os.environ["DEPLOYMENT_TYPE"] = "DEBUG"
os.environ["SESSION_COOKIE_SECURE"] = "true"
os.environ["REVERSE_PROXY_PREFIX"] = ""
os.environ["SHARED_STATIC_DIR"] = ""
os.environ["SHARED_TEMPLATES_DIR"] = ""
sys.path.insert(0, os.path.join(BASE, "landing-page"))
import shared.logger as shared_logger

shared_logger._LOG_DIR = "/tmp/wbs-logs"
import pytest
from app import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
