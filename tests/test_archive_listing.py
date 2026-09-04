"""Archive/reactivate a listing — the reversible alternative to delete.

Archiving takes a listing off browse/search without deleting it (so listings
with rental history, which can't be hard-deleted, still have a way off the
marketplace). It stays viewable by direct link for the owner and anyone with
a booking on it, but 404s for everyone else — same as a nonexistent listing.
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import Category, Listing
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import booking as booking_service

TODAY = date.today()
START = (TODAY + timedelta(days=3)).isoformat()
END = (TODAY + timedelta(days=5)).isoformat()


def _make_category(app, name="Tools", slug="tools"):
    with app.app_context():
        cat = Category(name=name, slug=slug)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _signup_verified(client, app, email):
    client.post(
        "/signup",
        data={"name": email.split("@")[0], "email": email,
              "password": "supersecret", "confirm": "supersecret"},
        follow_redirects=True,
    )
    # No nested app_context() here — see test_listings_crud.py's _signup for
    # why: the `app` fixture already keeps one active for the whole test, and
    # requests reuse that same scoped session.
    user = auth_service.get_user_by_email(email)
    user.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return user.id


def _create_listing(client, category_id, title="Archive Me"):
    client.post(
        "/listings/new",
        data={
            "title": title,
            "category_id": str(category_id),
            "city": "Islamabad",
            "area": "F-8",
            "price_per_day": "800",
            "deposit_amount": "5000",
        },
    )


def test_owner_can_archive_and_it_leaves_browse_and_detail(client, app):
    category_id = _make_category(app)
    _signup_verified(client, app, "archiveowner@example.com")
    _create_listing(client, category_id)
    with app.app_context():
        listing_id = Listing.query.filter_by(title="Archive Me").first().id

    resp = client.post(f"/listings/{listing_id}/archive", follow_redirects=True)
    assert resp.status_code == 200
    assert b"archived" in resp.data.lower()
    with app.app_context():
        assert db.session.get(Listing, listing_id).status == "paused"

    # Gone from public browse.
    assert b"Archive Me" not in client.get("/").data

    # Still viewable by the owner directly.
    assert client.get(f"/listings/{listing_id}").status_code == 200

    # 404 for a logged-out visitor.
    client.post("/logout")
    assert client.get(f"/listings/{listing_id}").status_code == 404


def test_reactivate_restores_browse_visibility(client, app):
    category_id = _make_category(app)
    _signup_verified(client, app, "reactivateowner@example.com")
    _create_listing(client, category_id, title="Reactivate Me")
    with app.app_context():
        listing_id = Listing.query.filter_by(title="Reactivate Me").first().id

    client.post(f"/listings/{listing_id}/archive")
    assert b"Reactivate Me" not in client.get("/").data

    resp = client.post(f"/listings/{listing_id}/reactivate", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Listing, listing_id).status == "active"
    assert b"Reactivate Me" in client.get("/").data


def test_non_owner_cannot_archive_or_reactivate(client, app):
    category_id = _make_category(app)
    _signup_verified(client, app, "archiveowner2@example.com")
    _create_listing(client, category_id, title="Owned By A2")
    with app.app_context():
        listing_id = Listing.query.filter_by(title="Owned By A2").first().id

    client.post("/logout")
    _signup_verified(client, app, "archiveintruder@example.com")
    assert client.post(f"/listings/{listing_id}/archive").status_code == 403
    assert client.post(f"/listings/{listing_id}/reactivate").status_code == 403


def test_renter_with_booking_can_view_archived_listing_stranger_cannot(client, app):
    category_id = _make_category(app)
    owner_id = _signup_verified(client, app, "archivebookedowner@example.com")
    _create_listing(client, category_id, title="Booked Then Archived")
    with app.app_context():
        listing = Listing.query.filter_by(title="Booked Then Archived").first()
        listing_id = listing.id

    client.post("/logout")
    _signup_verified(client, app, "archiverenter@example.com")
    with app.app_context():
        renter = auth_service.get_user_by_email("archiverenter@example.com")
        listing = db.session.get(Listing, listing_id)
        booking_service.request_to_rent(
            listing, renter,
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=3),
            message=None,
        )
        db.session.commit()

    # Owner archives it.
    client.post("/logout")
    client.post(
        "/login",
        data={"email": "archivebookedowner@example.com", "password": "supersecret"},
    )
    client.post(f"/listings/{listing_id}/archive")
    client.post("/logout")

    # The renter (has a real booking on it) can still see it.
    client.post(
        "/login",
        data={"email": "archiverenter@example.com", "password": "supersecret"},
    )
    assert client.get(f"/listings/{listing_id}").status_code == 200

    # An unrelated verified user cannot.
    client.post("/logout")
    _signup_verified(client, app, "archivestranger@example.com")
    assert client.get(f"/listings/{listing_id}").status_code == 404


def test_my_listings_hides_delete_when_booking_history_exists(client, app):
    category_id = _make_category(app)
    _signup_verified(client, app, "mylistingsowner@example.com")
    _create_listing(client, category_id, title="No Bookings Here")
    with app.app_context():
        listing_id = Listing.query.filter_by(title="No Bookings Here").first().id

    resp = client.get("/my/listings")
    assert resp.status_code == 200
    assert b"Delete" in resp.data
    assert b"Archive" in resp.data

    client.post("/logout")
    _signup_verified(client, app, "mylistingsrenter@example.com")
    with app.app_context():
        renter = auth_service.get_user_by_email("mylistingsrenter@example.com")
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
        data={"email": "mylistingsowner@example.com", "password": "supersecret"},
    )
    resp = client.get("/my/listings")
    assert b"Delete" not in resp.data
    assert b"Archive" in resp.data
