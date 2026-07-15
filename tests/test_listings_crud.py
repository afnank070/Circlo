"""M1 smoke tests — owner-created listings (create + ownership guard).

No images are uploaded here, so the storage backend (MinIO) is never touched —
these run against the same in-memory SQLite DB as the other smoke tests.
"""

from app.extensions import db
from app.models import Category, Listing
from app.services import auth as auth_service


def _make_category(app, name="Tools", slug="tools"):
    with app.app_context():
        cat = Category(name=name, slug=slug)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _signup(client, email="owner@example.com"):
    return client.post(
        "/signup",
        data={
            "name": "Owner Person",
            "email": email,
            "password": "supersecret",
            "confirm": "supersecret",
        },
        follow_redirects=True,
    )


def test_create_listing_requires_login(client):
    resp = client.get("/listings/new")
    # login_required redirects anonymous users to the login view.
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_create_listing_creates_owned_active_listing(client, app):
    category_id = _make_category(app)
    _signup(client)

    resp = client.post(
        "/listings/new",
        data={
            "title": "Bosch Hammer Drill",
            "description": "Corded 750W drill.",
            "category_id": str(category_id),
            "city": "Islamabad",
            "area": "F-8",
            "price_per_day": "800",
            "deposit_amount": "5000",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Listing published" in resp.data
    assert b"Bosch Hammer Drill" in resp.data

    with app.app_context():
        listing = Listing.query.filter_by(title="Bosch Hammer Drill").first()
        assert listing is not None
        assert listing.status == "active"
        assert int(listing.price_per_day) == 800
        assert int(listing.deposit_amount) == 5000
        owner = auth_service.get_user_by_email("owner@example.com")
        assert listing.owner_id == owner.id
        # New owner has no rating yet -> listing renders "New".
        assert listing.owner_rating is None
        assert listing.is_verified is False


def test_create_listing_rejects_missing_title(client, app):
    category_id = _make_category(app)
    _signup(client)

    resp = client.post(
        "/listings/new",
        data={
            "title": "",
            "category_id": str(category_id),
            "city": "Islamabad",
            "area": "F-8",
            "price_per_day": "800",
            "deposit_amount": "5000",
        },
    )
    assert resp.status_code == 200
    assert b"Title is required" in resp.data
    with app.app_context():
        assert Listing.query.count() == 0


def test_non_owner_cannot_edit_listing(client, app):
    category_id = _make_category(app)
    # Owner A creates a listing.
    _signup(client, email="ownera@example.com")
    client.post(
        "/listings/new",
        data={
            "title": "Owned by A",
            "category_id": str(category_id),
            "city": "Islamabad",
            "area": "F-8",
            "price_per_day": "800",
            "deposit_amount": "5000",
        },
    )
    with app.app_context():
        listing_id = Listing.query.filter_by(title="Owned by A").first().id

    # Owner B logs in (signup swaps the session) and tries to edit A's listing.
    client.post("/logout")
    _signup(client, email="ownerb@example.com")
    resp = client.get(f"/listings/{listing_id}/edit")
    assert resp.status_code == 403

    resp = client.post(
        f"/listings/{listing_id}/delete", follow_redirects=False
    )
    assert resp.status_code == 403
