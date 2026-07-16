import os, sys, pytest
from datetime import datetime

os.environ.setdefault('SECRET_KEY', 'test-secret-key-32-chars-min!!')
os.environ.setdefault('DB_ENGINE', 'sqlite')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '3306')
os.environ.setdefault('DB_NAME', ':memory:')
os.environ.setdefault('DB_USERNAME', 'root')
os.environ.setdefault('DB_PASS', 'test')
os.environ.setdefault('NFC_PWD_SECRET', 'a' * 64)
os.environ.setdefault('XENDIT_API_KEY', 'test-xendit-key')
os.environ.setdefault('XENDIT_WEBHOOK_TOKEN', 'test-webhook-token')
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')
os.environ.setdefault('PYTHON_GIL', '1')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ.setdefault('INTERNAL_API_KEY', 'test-internal-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')
os.environ.setdefault('SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api'))


@pytest.fixture(scope='class')
def app():
    from app import create_app, db
    application = create_app()
    with application.app_context():
        db.create_all()
        from models import Staff, Customer, ApiKey, MeterReading
        from werkzeug.security import generate_password_hash

        staff = Staff.query.filter_by(username='superuser').first()
        if not staff:
            staff = Staff(
                username='superuser', name='Superuser',
                password=generate_password_hash('superuser').encode('utf-8'),
                can_read_meters=True, can_accept_payment=True,
                can_enroll_customer=True, can_drop_reading=True,
                can_drop_payment=True, can_enroll_staff=True,
                can_manage_billing=True, is_active=True,
            )
            db.session.add(staff)
            db.session.flush()

        if not ApiKey.query.filter_by(key='CRDC-FLOWTEST').first():
            key = ApiKey(key='CRDC-FLOWTEST', label='flow', staff_id=staff.id)
            db.session.add(key)
            db.session.commit()

        if not Customer.query.filter_by(customer_number='FLOW-001').first():
            cust = Customer(customer_number='FLOW-001', name='Flow Test',
                           address='1 Flow St', cumulative_balance=0.00)
            db.session.add(cust)
            db.session.commit()

        flow_key = ApiKey.query.filter_by(key='CRDC-FLOWTEST').first()
        if flow_key and not MeterReading.query.filter_by(customer_number='FLOW-001').first():
            prev = MeterReading(
                customer_number='FLOW-001', reading_value=100.0,
                token_id=flow_key.id, timestamp=datetime(2025, 12, 1))
            db.session.add(prev)
            db.session.commit()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def api_key(app):
    from models import ApiKey
    with app.app_context():
        key = ApiKey.query.filter_by(key='CRDC-FLOWTEST').first()
        return key.key if key else 'CRDC-FLOWTEST'
