"""Smoke tests — the listing-detail owner card's contact link.

The old static "Message" button did nothing. It's replaced by a phone /
"View contact info" link that only appears when the viewer actually has an
ACCEPTED-or-later booking with this owner for this listing (reusing
booking_service.CONTACT_REVEAL_STATUSES). No accepted booking => no button.
"""
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Category, Listing
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import booking as booking_service

OWNER_PHONE = "03009998888"
START = datetime.now().replace(microsecond=0) + timedelta(days=2)


def _verified(email, phone="03001112222"):
    u = auth_service.create_user(email.split("@")[0], email, "supersecret", phone=phone)
    u.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return u


def _setup(app):
    """owner + listing + renter; returns (listing_id, renter_email)."""
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _verified("owner@example.com", phone=OWNER_PHONE)
        _verified("renter@example.com")
        listing = Listing(
            owner_id=owner.id, title="Bosch Drill", description="d",
            category_id=cat.id, city="Islamabad", area="F-8",
            price_per_hour=100, deposit_amount=5000, status="active",
        )
        db.session.add(listing)
        db.session.commit()
        return listing.id


def _login(client, email):
    client.post("/login", data={"email": email, "password": "supersecret"})


def _book(app, listing_id, *, accept=False, status=None):
    with app.app_context():
        listing = db.session.get(Listing, listing_id)
        renter = auth_service.get_user_by_email("renter@example.com")
        owner = auth_service.get_user_by_email("owner@example.com")
        b = booking_service.request_to_rent(
            listing, renter, start_datetime=START, duration_hours=2,
        )
        if accept:
            booking_service.accept(b, owner=owner)
        if status:
            b.status = status
            db.session.commit()
        return b.id


NO_LINK_MARKERS = (b"View contact info", OWNER_PHONE.encode())


def test_no_message_button_for_anonymous_viewer(client, app):
    listing_id = _setup(app)
    body = client.get(f"/listings/{listing_id}").data
    # the old dead <button>Message</button> is gone
    assert b">Message<" not in body
    assert b"Message\n        </button>" not in body
    assert all(m not in body for m in NO_LINK_MARKERS)


def test_no_link_for_logged_in_viewer_without_a_booking(client, app):
    listing_id = _setup(app)
    _login(client, "renter@example.com")
    body = client.get(f"/listings/{listing_id}").data
    assert all(m not in body for m in NO_LINK_MARKERS)


def test_no_link_while_booking_is_only_requested(client, app):
    listing_id = _setup(app)
    _book(app, listing_id, accept=False)
    _login(client, "renter@example.com")
    body = client.get(f"/listings/{listing_id}").data
    assert all(m not in body for m in NO_LINK_MARKERS)


def test_link_appears_once_booking_is_accepted(client, app):
    listing_id = _setup(app)
    booking_id = _book(app, listing_id, accept=True)
    _login(client, "renter@example.com")
    body = client.get(f"/listings/{listing_id}").data
    assert OWNER_PHONE.encode() in body
    assert f"/my-rentals#booking-{booking_id}".encode() in body


def test_link_appears_for_completed_booking_too(client, app):
    listing_id = _setup(app)
    _book(app, listing_id, accept=True, status="completed")
    _login(client, "renter@example.com")
    body = client.get(f"/listings/{listing_id}").data
    assert OWNER_PHONE.encode() in body


def test_service_only_returns_reveal_stage_bookings(app):
    listing_id = _setup(app)
    booking_id = _book(app, listing_id, accept=False)
    with app.app_context():
        renter = auth_service.get_user_by_email("renter@example.com")
        owner = auth_service.get_user_by_email("owner@example.com")
        rid = renter.id

        # Not signed in / still-pending booking -> nothing.
        assert booking_service.contact_reveal_booking(None, listing_id) is None
        assert booking_service.contact_reveal_booking(rid, listing_id) is None

        booking_service.accept(booking_service.get_booking(booking_id), owner=owner)
        found = booking_service.contact_reveal_booking(rid, listing_id)
        assert found is not None and found.id == booking_id

        # Cancelled -> nothing again.
        found.status = "cancelled"
        db.session.commit()
        assert booking_service.contact_reveal_booking(rid, listing_id) is None
