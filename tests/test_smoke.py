"""M0 foundation smoke tests: the app boots and its two routes answer."""


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_home_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"CIRCLO" in resp.data
