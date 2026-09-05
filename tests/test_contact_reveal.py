"""Smoke tests — contact (phone) + pickup location reveal on an accepted booking.

Gating rule (app/services/booking.py CONTACT_REVEAL_STATUSES): a renter and
owner should NOT see each other's phone number or the listing's pickup
details while a request is still REQUESTED, but should once the owner
accepts it. No messaging/chat is involved — this is a plain data reveal.
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

OWNER_PHONE = "03001112222"
RENTER_PHONE = "03003334444"


def _make_category(app):
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _signup_verified(client, email, phone):
    client.post(
        "/signup",
        data={"name": email.split("@")[0], "email": email, "phone": phone,
              "password": "supersecret", "confirm": "supersecret"},
        follow_redirects=True,
    )
    user = auth_service.get_user_by_email(email)
    user.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return user


def _make_listing(app, owner_email, category_id, pickup_location="F-7 Markaz", map_link="https://maps.app.goo.gl/test"):
    with app.app_context():
        owner = auth_service.get_user_by_email(owner_email)
        listing = Listing(
            owner_id=owner.id, title="Bosch Hammer Drill", description="desc",
            category_id=category_id, city="Islamabad", area="F-8",
            price_per_day=800, deposit_amount=5000, status="active",
            pickup_location=pickup_location, map_link=map_link,
        )
        db.session.add(listing)
        db.session.commit()
        return listing.id


def _request(client, listing_id):
    return client.post(
        f"/listings/{listing_id}/request",
        data={"start_date": START, "end_date": END, "message": "Please"},
        follow_redirects=True,
    )


def test_contact_not_revealed_before_acceptance(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com", OWNER_PHONE)
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com", RENTER_PHONE)
    _request(client, listing_id)

    resp = client.get("/my-rentals")
    assert resp.status_code == 200
    # Still just a pending request — no phone or pickup details leaked.
    assert OWNER_PHONE.encode() not in resp.data
    assert b"F-7 Markaz" not in resp.data
    assert b"Contact &amp; pickup" not in resp.data


def test_contact_revealed_after_acceptance(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com", OWNER_PHONE)
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com", RENTER_PHONE)
    _request(client, listing_id)

    with app.app_context():
        renter = auth_service.get_user_by_email("renter@example.com")
        booking_id = renter.rental_requests[0].id

    client.post("/logout")
    client.post("/login", data={"email": "owner@example.com", "password": "supersecret"})
    client.post(f"/bookings/{booking_id}/accept", follow_redirects=True)

    # Owner's view: sees the renter's phone.
    owner_page = client.get("/my-rentals")
    assert RENTER_PHONE.encode() in owner_page.data
    assert b"F-7 Markaz" in owner_page.data
    assert b"View on map" in owner_page.data

    # Renter's view: sees the owner's phone + the same pickup details.
    client.post("/logout")
    client.post("/login", data={"email": "renter@example.com", "password": "supersecret"})
    renter_page = client.get("/my-rentals")
    assert OWNER_PHONE.encode() in renter_page.data
    assert b"F-7 Markaz" in renter_page.data


def test_contact_reveal_helper_matches_status(app):
    """Unit-level check of the gating function itself, statuses in and out."""
    with app.app_context():
        from app.models.booking import (
            STATUS_ACCEPTED, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_REQUESTED,
        )

        class _Fake:
            def __init__(self, status):
                self.status = status

        assert booking_service.can_reveal_contact(_Fake(STATUS_REQUESTED)) is False
        assert booking_service.can_reveal_contact(_Fake(STATUS_CANCELLED)) is False
        assert booking_service.can_reveal_contact(_Fake(STATUS_ACCEPTED)) is True
        assert booking_service.can_reveal_contact(_Fake(STATUS_COMPLETED)) is True
