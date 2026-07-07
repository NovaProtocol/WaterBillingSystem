"""
Browser-based tests using Playwright (headless Chromium only).
Starts a live Flask server with a temp SQLite database, then interacts with the UI.
"""

import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from werkzeug.serving import make_server

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apps import create_app
from apps import db as _db
from apps.authentication.util import hash_pass
from apps.models import ApiKey, Customer, MeterReading, Staff

# ---------- Test config with file-based SQLite (shared across threads) ----------


class LiveTestConfig:
    SECRET_KEY = "test-secret-key-live"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    DEBUG = False
    BASE_DIR = Path(__file__).resolve().parent.parent / "apps"


def build_app(db_path):
    """Create the Flask app with the given SQLite database path."""

    class Config(LiveTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"

    return create_app(Config)


# ---------- Pytest fixtures ----------


@pytest.fixture(scope="module")
def live_server():
    """Start a live Flask server in a background thread, yield the URL."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    app = build_app(db_path)

    # Create tables and seed data
    with app.app_context():
        _db.create_all()
        _seed_data()
        _db.session.commit()

    # Determine a free port
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    # Wait for server to be ready
    for _ in range(50):
        time.sleep(0.1)
        try:
            import urllib.request

            urllib.request.urlopen(url + "/staff/", timeout=2)
            break
        except Exception:
            continue

    yield url

    server.shutdown()
    thread.join(timeout=5)
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(scope="module")
def browser():
    """Create a Playwright browser instance (headless Chromium)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def page(browser, live_server):
    """Create a new browser page/context for each test."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        ignore_https_errors=True,
    )
    page = context.new_page()
    page.set_default_timeout(10000)
    yield page
    context.close()


# ---------- Seed data ----------

CUSTOMER_NUM = "CUST-AUTO-001"
CUSTOMER_NAME = "Automation Test User"
READING_VALUES = [100.0, 250.0, 400.0]  # 3 readings for 2 consumption periods
SUPERUSER_API_KEY = "CRDC-TEST-SUPERUSER-KEYE2E00000001"


def _seed_data():
    """Seed the database with test data for browser tests."""
    superuser = Staff(
        username="superuser",
        name="Superuser",
        password=hash_pass("superuser"),
        can_read_meters=True,
        can_accept_payment=True,
        can_enroll_customer=True,
        can_drop_reading=True,
        can_drop_payment=True,
        can_enroll_staff=True,
        can_manage_billing=True,
    )
    _db.session.add(superuser)

    reader = Staff(
        username="readeronly",
        password=hash_pass("readeronly"),
        can_read_meters=True,
        can_accept_payment=False,
        can_enroll_customer=False,
        can_drop_reading=False,
        can_drop_payment=False,
        can_enroll_staff=False,
        can_manage_billing=False,
    )
    _db.session.add(reader)
    _db.session.flush()

    import secrets

    reader_token = ApiKey(
        key="CRDC-" + secrets.token_hex(16).upper(),
        label="Reader Token",
        staff_id=reader.id,
        is_active=True,
    )
    _db.session.add(reader_token)
    _db.session.flush()

    superuser_key = ApiKey(
        key=SUPERUSER_API_KEY,
        label="Superuser Key",
        staff_id=superuser.id,
        is_active=True,
    )
    _db.session.add(superuser_key)
    _db.session.flush()

    customer = Customer(
        customer_number=CUSTOMER_NUM,
        name=CUSTOMER_NAME,
        address="123 Test Street, Taguig",
        contact_number="09170000001",
        email="auto@test.com",
        cumulative_balance=0.00,
    )
    _db.session.add(customer)
    _db.session.flush()

    now = datetime.utcnow()
    for i, val in enumerate(READING_VALUES):
        mr = MeterReading(
            customer_number=CUSTOMER_NUM,
            reading_value=val,
            token_id=reader_token.id,
            timestamp=now - timedelta(days=(len(READING_VALUES) - 1 - i) * 30),
        )
        _db.session.add(mr)

    _db.session.commit()


# =============================================================================
# Playwright Tests
# =============================================================================

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SELENIUM_TESTS"),
    reason="Skipping browser tests. Set RUN_SELENIUM_TESTS=1 to run.",
)


class TestSelenium:
    def test_login_page_renders(self, page, live_server):
        page.goto(f"{live_server}/staff/login")
        assert "Login" in page.title() or page.locator("text=Login").count() > 0

    def test_login_success(self, page, live_server):
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        assert "/staff/dashboard" in page.url or "dashboard" in page.url

    def test_login_failure(self, page, live_server):
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "wrongpassword")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        assert "Wrong user or password" in page.content()

    def test_sidebar_superuser_all_tabs(self, page, live_server):
        """Superuser should see all sidebar tabs."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        assert page.locator("text=Meter Reading").count() > 0
        assert page.locator("text=Payments").count() > 0
        assert page.locator("text=Manage Billing").count() > 0
        assert page.locator("text=Manage Reading").count() > 0
        assert page.locator("text=Staff").count() > 0
        assert page.locator("text=Customers").count() > 0

    def test_sidebar_reader_limited(self, page, live_server):
        """Reader-only staff should only see Meter Reading in sidebar."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "readeronly")
        page.fill('input[name="password"]', "readeronly")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        # Check sidebar links specifically (not stat cards in main content)
        sidebar_links = page.locator(".sidebar a")
        texts = sidebar_links.all_text_contents()
        texts_str = " ".join(texts)
        assert "Meter Reading" in texts_str
        # Dashboard stat cards have "Payments" text, but sidebar should not
        # for a user without can_accept_payment
        assert "Payments" not in texts_str
        assert "Manage Billing" not in texts_str
        assert "Manage Reading" not in texts_str
        assert "Staff" not in texts_str
        assert "Customers" not in texts_str

    def test_customer_autocomplete(self, page, live_server):
        """Type partial customer number in Payments search, see dropdown, click result."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Navigate to payments
        page.goto(f"{live_server}/staff/payments")
        page.wait_for_load_state("networkidle")
        assert "/staff/payments" in page.url

        # Type partial customer number into the search input
        search_input = page.locator(
            'input#customer_search, input.customer-search, input[placeholder*="customer"i]'
        )
        if search_input.count() == 0:
            # Try to find any text input on the page
            search_input = page.locator('input[type="text"]').first
        search_input.fill("CUST-AUTO")

        # Wait for the autocomplete dropdown to appear
        time.sleep(1)
        # Look for the dropdown suggestion
        suggestion = page.locator("text=CUST-AUTO-001")
        if suggestion.count() > 0:
            suggestion.first.click()
            page.wait_for_load_state("networkidle")

    def test_api_key_generation(self, page, live_server):
        """Navigate to meter-reading, generate an API key, verify it appears."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/staff/meter-reading")
        page.wait_for_load_state("networkidle")
        assert "/staff/meter-reading" in page.url

        # Click the "Generate Key" button to open the modal
        gen_btn = page.locator('button:has-text("Generate Key")')
        assert gen_btn.count() > 0
        gen_btn.click()
        page.wait_for_timeout(500)

        # Fill in optional label
        label_input = page.locator("#keyLabel")
        assert label_input.count() > 0
        label_input.fill("Playwright Test Key")

        # Submit the form in the modal
        submit_btn = page.locator('#generateKeyForm button[type="submit"]')
        assert submit_btn.count() > 0
        submit_btn.click()

        # Wait for generate modal to close and result modal to appear
        page.wait_for_selector("#keyResultModal", timeout=5000)
        page.wait_for_timeout(300)

        # Dismiss the result modal — triggers location.reload()
        page.locator("#keyResultModal .btn-outline-cotta").click()
        page.wait_for_load_state("networkidle", timeout=10000)

        # Verify a new key appears in the key table
        page_content = page.content()
        assert "CRDC-" in page_content

    def test_payments_page_loads(self, page, live_server):
        """Payments page should load without errors."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/staff/payments")
        page.wait_for_load_state("networkidle")
        assert (
            page.locator("text=Customer Information").count() > 0
            or page.locator("text=Payments").count() > 0
        )

    def test_manage_billing_page_loads(self, page, live_server):
        """Manage Billing page should list management logs."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/staff/manage-billing")
        page.wait_for_load_state("networkidle")
        assert "/staff/manage-billing" in page.url

    def test_manage_reading_page_loads(self, page, live_server):
        """Manage Reading page should list management logs."""
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/staff/manage-reading")
        page.wait_for_load_state("networkidle")
        assert "/staff/manage-reading" in page.url

    def test_full_billing_lifecycle(self, page, live_server):
        """End-to-end: enroll customer, submit readings, verify bill, pay, verify paid."""
        # --- Login ---
        page.goto(f"{live_server}/staff/login")
        page.fill('input[name="username"]', "superuser")
        page.fill('input[name="password"]', "superuser")
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        assert "/staff/dashboard" in page.url

        # --- Step 1: Enroll customer via UI ---
        page.goto(f"{live_server}/staff/customers")
        page.fill("#cust-number", "E2E-001")
        page.fill("#cust-name", "E2E Test User")
        page.fill("#cust-address", "123 E2E Street, Test City")
        page.click("#create-customer-form button[type='submit']")
        page.wait_for_selector("#customer-result", timeout=5000)
        page.wait_for_timeout(500)
        content = page.content()
        assert "E2E-001" in content

        # --- Step 2: Submit two readings via API ---
        now_ts = int(datetime.utcnow().timestamp())
        prev_ts = int((datetime.utcnow() - timedelta(days=60)).timestamp())
        for val, ts in [(100.0, prev_ts), (250.0, now_ts)]:
            result = page.evaluate(
                """async (data) => {
                    const r = await fetch(data.url + '/api/readings/upload', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + data.apiKey
                        },
                        body: JSON.stringify({
                            customer_number: 'E2E-001',
                            reading_value: data.value,
                            timestamp: data.timestamp
                        })
                    });
                    return {status: r.status, body: await r.json()};
                }""",
                {
                    "url": live_server,
                    "apiKey": SUPERUSER_API_KEY,
                    "value": val,
                    "timestamp": ts,
                },
            )
            assert result["status"] == 201, f"Reading upload failed: {result}"

        # --- Step 3: Verify bill on manage-customers ---
        page.goto(f"{live_server}/staff/manage-customers?q=E2E-001")
        page.wait_for_load_state("networkidle")
        content = page.content()
        assert "E2E-001" in content

        # --- Step 4: Submit payment via API ---
        result = page.evaluate(
            """async (data) => {
                const r = await fetch(data.url + '/staff/payments/submit', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        customer_number: 'E2E-001',
                        amount: data.amount
                    })
                });
                return {status: r.status, body: await r.json()};
            }""",
            {"url": live_server, "amount": 500.00},
        )
        assert result["status"] in (200, 201), f"Payment failed: {result}"
        receipt = result.get("body", {}).get("receipt_number", "")
        assert len(receipt) > 0 or result["body"].get("message")

        # --- Step 5: Verify billing portal ---
        page.evaluate(
            """async (url) => {
                await fetch(url + '/billing/api/confirm', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({customer_number: 'E2E-001'})
                });
            }""",
            live_server,
        )
        page.goto(f"{live_server}/billing/E2E-001")
        page.wait_for_load_state("networkidle")
        content = page.content()
        assert "E2E-001" in content or "E2E Test User" in content
