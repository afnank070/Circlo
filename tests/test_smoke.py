"""Foundation + M2 smoke tests: the app boots and its routes answer."""


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_home_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"CIRCLO" in resp.data


def test_browse_empty_marketplace_shows_empty_state(client):
    # No seed data in tests -> browse renders its empty state, not a 500.
    resp = client.get("/?q=nothing-here")
    assert resp.status_code == 200
    assert b"No listings match your search" in resp.data


def test_missing_listing_returns_404(client):
    resp = client.get("/listings/424242")
    assert resp.status_code == 404
