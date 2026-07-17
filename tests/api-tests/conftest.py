import os, sys, pytest, warnings
from sqlalchemy import exc as sa_exc

warnings.filterwarnings('ignore', category=DeprecationWarning,
                        message='.*datetime.datetime.utcnow.*')
warnings.filterwarnings('ignore', category=DeprecationWarning,
                        message='.*datetime.datetime.utcfromtimestamp.*')
warnings.filterwarnings('ignore', category=ResourceWarning,
                        message='.*unclosed database.*')
warnings.filterwarnings('ignore', category=sa_exc.LegacyAPIWarning)

# Point to shared/ for models, pricing, services
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api'))

# Set env vars before any imports
os.environ.setdefault('SECRET_KEY', 'test-secret-key-32-chars-min!!')
os.environ.setdefault('DB_ENGINE', 'sqlite')
os.environ.setdefault('DB_HOST', '')
os.environ.setdefault('DB_PORT', '')
os.environ.setdefault('DB_NAME', ':memory:')
os.environ.setdefault('DB_USERNAME', '')
os.environ.setdefault('DB_PASS', '')
# Override URI construction for SQLite
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ.setdefault('NFC_PWD_SECRET', 'a' * 64)
os.environ.setdefault('XENDIT_API_KEY', 'test-xendit-key')
os.environ.setdefault('XENDIT_WEBHOOK_TOKEN', 'test-webhook-token')
os.environ.setdefault('CACHE_TYPE', 'SimpleCache')
os.environ.setdefault('PYTHON_GIL', '1')
os.environ.setdefault('DEPLOYMENT_TYPE', 'DEBUG')
os.environ.setdefault('INTERNAL_API_KEY', 'test-internal-key')
os.environ.setdefault('API_BASE_URL', 'http://test:8008')


@pytest.fixture
def app():
    from app import create_app, db
    application = create_app()
    with application.app_context():
        from models import Staff, Customer
        db.create_all()

        from werkzeug.security import generate_password_hash
        if not Staff.query.filter_by(username='superuser').first():
            staff = Staff(
                username='superuser',
                name='Superuser',
                password=generate_password_hash('superuser').encode('utf-8'),
                can_read_meters=True, can_accept_payment=True,
                can_enroll_customer=True, can_drop_reading=True,
                can_drop_payment=True, can_enroll_staff=True,
                can_manage_billing=True, is_active=True,
            )
            db.session.add(staff)

        if not Customer.query.filter_by(customer_number='TEST-001').first():
            cust = Customer(
                customer_number='TEST-001', name='Test Customer',
                address='123 Test St', contact_number='09170000001',
                cumulative_balance=0.00,
            )
            db.session.add(cust)
        db.session.commit()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def api_key(app):
    from models import ApiKey, Staff
    from app import db
    with app.app_context():
        staff = Staff.query.filter_by(username='superuser').first()
        key = ApiKey(key='CRDC-TESTKEY1234567890ABCDEF12345678', label='test', staff_id=staff.id)
        db.session.add(key)
        db.session.commit()
        return key.key
