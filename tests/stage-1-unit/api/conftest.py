import os, sys
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['NFC_PWD_SECRET'] = 'a' * 64
os.environ['XENDIT_API_KEY'] = 'test'
os.environ['XENDIT_WEBHOOK_TOKEN'] = 'test'
os.environ['CACHE_TYPE'] = 'SimpleCache'
os.environ['PYTHON_GIL'] = '1'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
os.environ['DB_ENGINE'] = 'sqlite'
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_PORT'] = '3306'
os.environ['DB_NAME'] = ':memory:'
os.environ['DB_USERNAME'] = 'root'
os.environ['DB_PASS'] = 'test'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))
from app import create_app
import pytest
@pytest.fixture(scope='module')
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        from apps import create_all
        create_all()
    return app.test_client()
