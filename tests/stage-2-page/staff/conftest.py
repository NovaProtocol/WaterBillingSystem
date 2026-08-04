import os, sys, types, pytest, threading, time
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['INTERNAL_API_KEY'] = 'test'
os.environ['API_BASE_URL'] = 'http://api:8008'
os.environ['CACHE_TYPE'] = 'SimpleCache'
os.environ['DEPLOYMENT_TYPE'] = 'DEBUG'
sys.path.insert(0, os.path.join(BASE, 'staff-portal'))
from app import create_app
app = create_app()
import werkzeug.serving
t = threading.Thread(target=werkzeug.serving.run_simple,
                     args=('127.0.0.1', 9103, app),
                     kwargs={'use_reloader': False}, daemon=True)
t.start()
time.sleep(1)

@pytest.fixture(scope='session')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()

@pytest.fixture
def page(browser):
    p = browser.new_page()
    yield p
    p.close()
