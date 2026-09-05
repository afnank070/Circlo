"""M1 smoke tests — owner-created listings (create + ownership guard).

No images are uploaded here, so the storage backend (MinIO) is never touched —
these run against the same in-memory SQLite DB as the other smoke tests.

Listing creation is gated on identity verification (M1 part 2), so every test
here verifies the signed-up user directly (bypassing the CNIC/selfie flow,
which is covered separately in test_verification.py) before listing.
"""

from app.extensions import db
from app.models import Category, Listing
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service


def _make_category(app, name="Tools", slug="tools"):
    with app.app_context():
        cat = Category(name=name, slug=slug)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _signup(client, app, email="owner@example.com"):
    resp = client.post(
        "/signup",
        data={
            "name": "Owner Person",
            "email": email,
            "phone": "03001234567",
            "password": "supersecret",
            "confirm": "supersecret",
        },
        follow_redirects=True,
    )
    # No nested app_context() here: the `app` fixture already keeps one active
    # for the whole test, and requests reuse that same scoped session. Opening
    # a second one would create a separate session whose commit wouldn't be
    # visible to the identity map the next request reads `current_user` from.
    user = auth_service.get_user_by_email(email)
    user.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return resp


def test_create_listing_requires_login(client):
    resp = client.get("/listings/new")
    # login_required redirects anonymous users to the login view.
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_create_listing_creates_owned_active_listing(client, app):
    category_id = _make_category(app)
    _signup(client, app)

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
        # Owner was verified in _signup() to pass the listing-gate -> reflected here.
        assert listing.is_verified is True


def test_create_listing_rejects_missing_title(client, app):
    category_id = _make_category(app)
    _signup(client, app)

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
    _signup(client, app, email="ownera@example.com")
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
    _signup(client, app, email="ownerb@example.com")
    resp = client.get(f"/listings/{listing_id}/edit")
    assert resp.status_code == 403

    resp = client.post(
        f"/listings/{listing_id}/delete", follow_redirects=False
    )
    assert resp.status_code == 403


def test_delete_listing_with_bookings_is_refused_not_500(client, app):
    """A listing with rental history can't be hard-deleted (would violate the
    bookings.listing_id NOT NULL FK) — the route must flash a friendly error,
    not 500."""
    from datetime import date, timedelta

    from app.services import booking as booking_service

    category_id = _make_category(app)
    _signup(client, app, email="bookedowner@example.com")
    client.post(
        "/listings/new",
        data={
            "title": "Has A Booking",
            "category_id": str(category_id),
            "city": "Islamabad",
            "area": "F-8",
            "price_per_day": "800",
            "deposit_amount": "5000",
        },
    )
    with app.app_context():
        listing = Listing.query.filter_by(title="Has A Booking").first()
        listing_id = listing.id

    client.post("/logout")
    _signup(client, app, email="bookedrenter@example.com")
    with app.app_context():
        renter = auth_service.get_user_by_email("bookedrenter@example.com")
        renter.verification_status = VERIFICATION_APPROVED
        listing = db.session.get(Listing, listing_id)
        booking_service.request_to_rent(
            listing, renter,
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=3),
            message=None,
        )
        db.session.commit()

    client.post("/logout")
    client.post(
        "/login",
        data={"email": "bookedowner@example.com", "password": "supersecret"},
    )
    resp = client.post(
        f"/listings/{listing_id}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"can&#39;t be deleted" in resp.data or b"can't be deleted" in resp.data
    with app.app_context():
        assert db.session.get(Listing, listing_id) is not None
