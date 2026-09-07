"""Browse-page sort smoke tests.

The old "Sort by: distance" control was decorative (distance is never computed).
It's replaced by a real sort on data we store: newest / price low→high /
price high→low / highest owner rating. Each option must actually return
listings in the right order, and the choice must round-trip through ``?sort=``.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import Category, Listing, User
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import listings as listings_service

BASE = datetime(2026, 1, 1, 12, 0, 0)


def _cat():
    c = Category(name="Tools", slug="tools")
    db.session.add(c)
    db.session.commit()
    return c


def _owner(email, rating=None):
    u = auth_service.create_user(email.split("@")[0], email, "supersecret", phone="03001234567")
    u.verification_status = VERIFICATION_APPROVED
    if rating is not None:
        u.rating = Decimal(str(rating))
    db.session.commit()
    return u


def _listing(cat, owner, *, title, price, days_old, area="F-7"):
    l = Listing(
        owner_id=owner.id, title=title, description="d", category_id=cat.id,
        city="Islamabad", area=area, price_per_day=Decimal(str(price)),
        deposit_amount=1000, status="active",
        created_at=BASE - timedelta(days=days_old),
    )
    db.session.add(l)
    db.session.commit()
    return l


def _seed(app):
    """Three listings with distinct price / age / owner-rating. Returns titles."""
    with app.app_context():
        cat = _cat()
        o_hi = _owner("hi@example.com", rating=4.9)
        o_mid = _owner("mid@example.com", rating=3.2)
        o_new = _owner("new@example.com", rating=None)  # unrated owner

        # (title, price, days_old, owner)
        _listing(cat, o_mid, title="Cheap old drill", price=300, days_old=30)
        _listing(cat, o_hi, title="Pricey mid saw", price=2500, days_old=10)
        _listing(cat, o_new, title="Midprice fresh sander", price=1200, days_old=1)


def _titles(results):
    return [l.title for l in results]


def test_default_sort_is_newest_first(app):
    _seed(app)
    with app.app_context():
        assert _titles(listings_service.browse_listings()) == [
            "Midprice fresh sander", "Pricey mid saw", "Cheap old drill",
        ]


def test_unknown_sort_falls_back_to_newest(app):
    _seed(app)
    with app.app_context():
        assert listings_service.normalized_sort("distance") == "newest"
        assert listings_service.normalized_sort(None) == "newest"
        assert _titles(listings_service.browse_listings(sort="distance")) == \
            _titles(listings_service.browse_listings(sort="newest"))


def test_sort_price_low_to_high(app):
    _seed(app)
    with app.app_context():
        results = listings_service.browse_listings(sort="price_low")
        assert _titles(results) == ["Cheap old drill", "Midprice fresh sander", "Pricey mid saw"]
        prices = [float(l.price_per_day) for l in results]
        assert prices == sorted(prices)


def test_sort_price_high_to_low(app):
    _seed(app)
    with app.app_context():
        results = listings_service.browse_listings(sort="price_high")
        assert _titles(results) == ["Pricey mid saw", "Midprice fresh sander", "Cheap old drill"]
        prices = [float(l.price_per_day) for l in results]
        assert prices == sorted(prices, reverse=True)


def test_sort_highest_rated_puts_unrated_last(app):
    _seed(app)
    with app.app_context():
        results = listings_service.browse_listings(sort="rating")
        # 4.9 owner, then 3.2 owner, then the unrated owner's listing last
        assert _titles(results) == ["Pricey mid saw", "Cheap old drill", "Midprice fresh sander"]


def test_sort_combines_with_filters(app):
    _seed(app)
    with app.app_context():
        cat = Category.query.first()
        o = _owner("extra@example.com", rating=5.0)
        _listing(cat, o, title="G-11 budget clamp", price=100, days_old=5, area="G-11")

        # area filter + price_low: only the F-7 listings, cheapest first
        f7 = listings_service.browse_listings(area="F-7", sort="price_low")
        assert _titles(f7) == ["Cheap old drill", "Midprice fresh sander", "Pricey mid saw"]
        assert "G-11 budget clamp" not in _titles(f7)


# --- route / template ----------------------------------------------------
def test_route_reflects_sort_in_page_and_select(client, app):
    _seed(app)
    resp = client.get("/?sort=price_low")
    assert resp.status_code == 200
    body = resp.data.decode()
    # cheapest appears before priciest in the rendered grid
    assert body.index("Cheap old drill") < body.index("Pricey mid saw")
    # the <select> shows the active choice
    assert '<option value="price_low" selected>' in body
    # no trace of distance sorting anywhere
    assert "distance" not in body.lower()


def test_route_default_has_no_sort_query_needed(client, app):
    _seed(app)
    body = client.get("/").data.decode()
    assert body.index("Midprice fresh sander") < body.index("Cheap old drill")
    assert '<option value="newest" selected>' in body
