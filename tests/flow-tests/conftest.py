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


@pytest.fixture(scope='module')
def app():
    from app import create_app, db
    application = create_app()
    with application.app_context():
        db.create_all()
        from models import Staff, Customer, ApiKey, MeterReading, Billing, NfcTag, Config
        from werkzeug.security import generate_password_hash
        from pricing import compute_water_bill

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

        flow_key = ApiKey.query.filter_by(key='CRDC-FLOWTEST').first()

        if not Customer.query.filter_by(customer_number='FLOW-001').first():
            cust = Customer(
                customer_number='FLOW-001', name='Flow Test Customer',
                address='42 Flow Street, Testville',
                contact_number='09171234567',
                email='flow@test.com',
                phase='Phase 1', block='Block A', street='Main St',
                meter_serial_number='MTR-001',
                cumulative_balance=50.00,
                is_active=True,
            )
            db.session.add(cust)

        if not Customer.query.filter_by(customer_number='FLOW-002').first():
            cust2 = Customer(
                customer_number='FLOW-002', name='Second Customer',
                address='99 Second Ave',
                contact_number='09179876543',
                cumulative_balance=0.00, is_active=False,
            )
            db.session.add(cust2)

        if not NfcTag.query.filter_by(uid='A1B2C3D4').first():
            nfc = NfcTag(uid='A1B2C3D4', customer_number='FLOW-001', enrolled_by_id=staff.id)
            db.session.add(nfc)

        if not MeterReading.query.filter_by(customer_number='FLOW-001').first():
            prev = MeterReading(
                customer_number='FLOW-001', reading_value=100.0,
                token_id=flow_key.id, timestamp=datetime(2025, 12, 1))
            db.session.add(prev)
            db.session.flush()

            curr = MeterReading(
                customer_number='FLOW-001', reading_value=175.5,
                token_id=flow_key.id, timestamp=datetime(2026, 1, 15))
            db.session.add(curr)
            db.session.flush()

            consumption = 175.5 - 100.0
            wb, _ = compute_water_bill(consumption)
            bill = Billing(
                customer_number='FLOW-001', reading_id=curr.id,
                previous_reading_value=100.0,
                current_reading_value=175.5,
                consumption=round(consumption, 2),
                billed_amount=round(wb, 2),
                penalty=0, paid_amount=0, is_paid=False,
            )
            db.session.add(bill)
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
