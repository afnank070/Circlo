"""TEMPORARY route: GET /debug/reprice-listings (gated by DEBUG_REPRICE_KEY).

Delete this file when app/web/debug.py is removed.
"""
from app.extensions import db
from app.models import Category, Listing, User
from app.services import seed as seed_service


def _listing(title, price, deposit):
    cat = Category.query.filter_by(slug="tools").first()
    if cat is None:
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.flush()
    owner = User(name="O", email=f"o{Listing.query.count()}@x.test", phone="0300")
    owner.set_password("x")
    db.session.add(owner)
    db.session.flush()
    l = Listing(title=title, description="d", category_id=cat.id, city="Islamabad",
                area="F-8", price_per_hour=price, deposit_amount=deposit,
                owner_id=owner.id, status="active")
    db.session.add(l)
    db.session.commit()
    return l.id


def test_route_404s_without_key(client, app):
    assert client.get("/debug/reprice-listings").status_code == 404
    assert client.get("/debug/reprice-listings?key=anything").status_code == 404


def test_route_404s_on_wrong_key(client, app):
    app.config["DEBUG_REPRICE_KEY"] = "s3cret"
    assert client.get("/debug/reprice-listings?key=nope").status_code == 404


def test_route_reprices_matching_listings(client, app):
    app.config["DEBUG_REPRICE_KEY"] = "s3cret"
    # A real seed title, currently mispriced (the day->hour bug).
    title, want_price, want_deposit = seed_service.LISTINGS[0][0], \
        seed_service.LISTINGS[0][4], seed_service.LISTINGS[0][5]
    with app.app_context():
        lid = _listing(title, 0, 999)
        _listing("Not A Seed Item", 123, 456)  # untouched

    resp = client.get("/debug/reprice-listings?key=s3cret")
    assert resp.status_code == 200
    assert title.encode() in resp.data

    with app.app_context():
        fixed = db.session.get(Listing, lid)
        assert int(fixed.price_per_hour) == want_price
        assert int(fixed.deposit_amount) == want_deposit
        other = Listing.query.filter_by(title="Not A Seed Item").first()
        assert int(other.price_per_hour) == 123  # unchanged


def test_reprice_is_idempotent(client, app):
    app.config["DEBUG_REPRICE_KEY"] = "s3cret"
    title = seed_service.LISTINGS[1][0]
    price, deposit = seed_service.LISTINGS[1][4], seed_service.LISTINGS[1][5]
    with app.app_context():
        _listing(title, price, deposit)  # already correct

    result = client.get("/debug/reprice-listings?key=s3cret").data.decode()
    assert "already correct" in result
