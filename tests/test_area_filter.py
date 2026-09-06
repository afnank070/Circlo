"""Location-filter smoke tests — standardized areas actually filter correctly.

Area used to be free text, so "F-7" / "F7" / "F-7 Islamabad" never matched in
the browse filter. Now every listing's area is one of
``app.services.areas.CANONICAL_AREAS`` and the filter matches it exactly.
"""
import pytest

from app.extensions import db
from app.models import Area, Category, Listing, User
from app.services import areas as areas_service
from app.services import auth as auth_service
from app.services import listings as listings_service
from app.services.seed import seed_all
from app.models.user import VERIFICATION_APPROVED


def _cat(slug="tools", name="Tools"):
    c = Category(name=name, slug=slug)
    db.session.add(c)
    db.session.commit()
    return c


def _owner():
    u = auth_service.create_user("Owner", "owner@example.com", "supersecret", phone="03001234567")
    u.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return u


def _listing(cat, owner, *, title, area, city="Islamabad", status="active"):
    l = Listing(
        owner_id=owner.id, title=title, description="d", category_id=cat.id,
        city=city, area=area, price_per_day=500, deposit_amount=1000, status=status,
    )
    db.session.add(l)
    db.session.commit()
    return l


# --- The canonical vocabulary ----------------------------------------------
def test_canonical_areas_cover_both_cities():
    cities = {a["city"] for a in areas_service.CANONICAL_AREAS}
    assert cities == {"Islamabad", "Rawalpindi"}
    names = areas_service.area_names()
    for expected in ("F-7", "F-8", "G-11", "E-11", "DHA Phase 2", "Bahria Town",
                     "Satellite Town", "Saddar", "Chaklala Scheme 3"):
        assert expected in names


def test_is_valid_area_rejects_free_text_variants():
    assert areas_service.is_valid_area("F-7")
    assert not areas_service.is_valid_area("F7")
    assert not areas_service.is_valid_area("F-7 Islamabad")
    assert not areas_service.is_valid_area("somewhere else")
    assert not areas_service.is_valid_area("")


def test_closest_area_maps_common_variants():
    assert areas_service.closest_area("F-7") == "F-7"
    assert areas_service.closest_area("F7") == "F-7"
    assert areas_service.closest_area("f-7 islamabad") == "F-7"
    assert areas_service.closest_area("F-7 Markaz") == "F-7"
    assert areas_service.closest_area("Bahria Town", city="Rawalpindi") == "Bahria Town"
    assert areas_service.closest_area("satellite town") == "Satellite Town"
    # Unrecognised -> a safe canonical fallback for the city, never left as-is.
    fallback = areas_service.closest_area("Nowheresville", city="Rawalpindi")
    assert areas_service.is_valid_area(fallback)
    assert areas_service.city_for_area(fallback) == "Rawalpindi"


def test_city_is_derived_from_area():
    assert areas_service.city_for_area("F-7") == "Islamabad"
    assert areas_service.city_for_area("Saddar") == "Rawalpindi"


# --- The filter actually filters -----------------------------------------
def test_browse_filters_by_exact_area(app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        _listing(cat, owner, title="Drill in F-7", area="F-7")
        _listing(cat, owner, title="Drill in F-8", area="F-8")
        _listing(cat, owner, title="Grinder in Saddar", area="Saddar", city="Rawalpindi")

        f7 = listings_service.browse_listings(area="F-7")
        assert [l.title for l in f7] == ["Drill in F-7"]

        f8 = listings_service.browse_listings(area="F-8")
        assert [l.title for l in f8] == ["Drill in F-8"]

        # No cross-contamination: F-7 filter never returns F-8 / Saddar.
        assert "Drill in F-8" not in [l.title for l in f7]
        assert "Grinder in Saddar" not in [l.title for l in f7]


def test_browse_filters_by_city(app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        _listing(cat, owner, title="ISB item", area="F-7", city="Islamabad")
        _listing(cat, owner, title="RWP item", area="Saddar", city="Rawalpindi")

        isb = listings_service.browse_listings(city="Islamabad")
        assert [l.title for l in isb] == ["ISB item"]
        rwp = listings_service.browse_listings(city="Rawalpindi")
        assert [l.title for l in rwp] == ["RWP item"]


def test_browse_area_and_category_combine(app):
    with app.app_context():
        tools = _cat("tools", "Tools")
        cams = _cat("cameras", "Cameras")
        owner = _owner()
        _listing(tools, owner, title="Drill F-7", area="F-7")
        _listing(cams, owner, title="Camera F-7", area="F-7")

        res = listings_service.browse_listings(area="F-7", category_slug="cameras")
        assert [l.title for l in res] == ["Camera F-7"]


def test_browse_ignores_archived_listings_in_area_filter(app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        _listing(cat, owner, title="Active F-7", area="F-7")
        _listing(cat, owner, title="Archived F-7", area="F-7", status="paused")

        res = listings_service.browse_listings(area="F-7")
        assert [l.title for l in res] == ["Active F-7"]


# --- Listing create/edit is locked to the standardized list --------------
def test_create_listing_rejects_non_canonical_area(app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        with pytest.raises(listings_service.InvalidArea):
            listings_service.create_listing(
                owner=owner, title="X", description="d", category_id=cat.id,
                city="Islamabad", area="F7", price_per_day=100, deposit_amount=100,
            )


def test_create_listing_derives_city_from_area(app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        l = listings_service.create_listing(
            owner=owner, title="X", description="d", category_id=cat.id,
            city="Islamabad",  # deliberately wrong — should be overridden
            area="Saddar", price_per_day=100, deposit_amount=100,
        )
        assert l.area == "Saddar"
        assert l.city == "Rawalpindi"


def test_update_listing_rejects_non_canonical_area(app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        l = _listing(cat, owner, title="X", area="F-7")
        with pytest.raises(listings_service.InvalidArea):
            listings_service.update_listing(
                l, title="X", description="d", category_id=cat.id,
                city="Islamabad", area="F-7 Islamabad",
                price_per_day=100, deposit_amount=100,
            )


# --- Route + dropdown -----------------------------------------------------
def test_browse_route_area_filter(client, app):
    with app.app_context():
        cat = _cat()
        owner = _owner()
        _listing(cat, owner, title="Findme F7 listing", area="F-7")
        _listing(cat, owner, title="Hidden F8 listing", area="F-8")

    page = client.get("/?area=F-7").data
    assert b"Findme F7 listing" in page
    assert b"Hidden F8 listing" not in page


def test_browse_dropdown_lists_standardized_areas_grouped_by_city(client, app):
    page = client.get("/").data
    assert b"<optgroup label=\"Islamabad\"" in page
    assert b"<optgroup label=\"Rawalpindi\"" in page
    assert b"<option value=\"F-7\"" in page
    assert b"<option value=\"Saddar\"" in page
    # The old free-text "All areas" span is now a real select control.
    assert b"name=\"area\"" in page


def test_listing_form_area_is_a_select_not_free_text(client, app):
    with app.app_context():
        _cat()
        u = auth_service.create_user("O", "o@example.com", "supersecret", phone="03001234567")
        u.verification_status = VERIFICATION_APPROVED
        db.session.commit()
    client.post("/login", data={"email": "o@example.com", "password": "supersecret"})
    page = client.get("/listings/new").data
    assert b"<select id=\"area\" name=\"area\"" in page
    assert b"<option value=\"G-11\"" in page
    assert b"type=\"text\"" not in page.split(b'name="area"')[0][-400:]  # area isn't a text input


def test_post_listing_with_free_text_area_is_rejected(client, app):
    with app.app_context():
        cat = _cat()
        u = auth_service.create_user("O", "o@example.com", "supersecret", phone="03001234567")
        u.verification_status = VERIFICATION_APPROVED
        db.session.commit()
        cat_id = cat.id
    client.post("/login", data={"email": "o@example.com", "password": "supersecret"})
    resp = client.post("/listings/new", data={
        "title": "Sneaky", "description": "d", "category_id": str(cat_id),
        "city": "Islamabad", "area": "F7 near the market",
        "price_per_day": "100", "deposit_amount": "100",
    }, follow_redirects=True)
    assert b"choose an area from the list" in resp.data.lower()
    with app.app_context():
        assert Listing.query.filter_by(title="Sneaky").first() is None


# --- Sync into the DB ----------------------------------------------------
def test_sync_areas_populates_table(app):
    with app.app_context():
        n = areas_service.sync_areas()
        assert n == len(areas_service.CANONICAL_AREAS)
        assert Area.query.count() == n
        # idempotent
        areas_service.sync_areas()
        assert Area.query.count() == n


def test_seeded_listings_all_have_canonical_areas(app, monkeypatch):
    monkeypatch.setattr("app.services.seed._fetch_unsplash_photo", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.storage.ensure_buckets", lambda *a, **k: None)
    monkeypatch.setattr("app.services.storage.upload_fileobj", lambda *a, **k: "k")
    with app.app_context():
        seed_all()
        for l in Listing.query.all():
            assert areas_service.is_valid_area(l.area), l.area
            assert l.city == areas_service.city_for_area(l.area)
