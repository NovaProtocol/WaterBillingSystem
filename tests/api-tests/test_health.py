import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api'))

def test_health_endpoint():
    from app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] in ('ok', 'degraded')
