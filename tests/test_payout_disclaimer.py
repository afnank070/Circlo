"""Smoke tests — owner payout-timing disclaimer (copy only, no logic change).

Owners must never expect payment on acceptance. Two touch-points:
  1. the flash shown when an owner accepts a request, and
  2. a persistent note on the owner's booking card in /my-rentals while the
     rental is in flight (accepted → returned), gone once completed.
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import Booking, Category, Listing
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service

TODAY = date.today()
START = (TODAY + timedelta(days=3)).isoformat()
END = (TODAY + timedelta(days=5)).isoformat()

NOTE = b"Your payout is released after the rental completes"


def _cat(app):
    with app.app_context():
        c = Category(name="Tools", slug="tools")
        db.session.add(c)
        db.session.commit()
        return c.id


def _verified(client, email):
    client.post("/signup", data={
        "name": email.split("@")[0], "email": email, "phone": "03001234567",
        "password": "supersecret", "confirm": "supersecret",
    }, follow_redirects=True)
    u = auth_service.get_user_by_email(email)
    u.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return u


def _listing(app, owner_email, cat_id):
    with app.app_context():
        owner = auth_service.get_user_by_email(owner_email)
        l = Listing(owner_id=owner.id, title="Bosch Hammer Drill", description="d",
                    category_id=cat_id, city="Islamabad", area="F-8",
                    price_per_day=800, deposit_amount=5000, status="active")
        db.session.add(l)
        db.session.commit()
        return l.id


def _booking_between(client, app, cat_id):
    """owner@ + renter@ + a REQUESTED booking. Returns booking id, leaves the
    owner logged in."""
    _verified(client, "owner@example.com")
    listing_id = _listing(app, "owner@example.com", cat_id)
    client.post("/logout")
    _verified(client, "renter@example.com")
    client.post(f"/listings/{listing_id}/request",
                data={"start_date": START, "end_date": END, "message": "hi"},
                follow_redirects=True)
    client.post("/logout")
    client.post("/login", data={"email": "owner@example.com", "password": "supersecret"})
    with app.app_context():
        return Booking.query.filter_by(listing_id=listing_id).first().id


def test_accept_flash_sets_payout_expectation(client, app):
    cat_id = _cat(app)
    bid = _booking_between(client, app, cat_id)

    resp = client.post(f"/bookings/{bid}/accept", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.data
    assert b"Rental request accepted" in body  # existing copy still there
    assert b"not immediately on acceptance" in body
    assert b"returned in good condition" in body


def test_card_note_shown_while_in_flight_for_owner(client, app):
    cat_id = _cat(app)
    bid = _booking_between(client, app, cat_id)
    client.post(f"/bookings/{bid}/accept", follow_redirects=True)

    # accepted -> note visible on the owner's card
    assert NOTE in client.get("/my-rentals").data

    # advance through the in-flight states -> still visible
    for status in ("awaiting_payment", "paid", "active", "returned"):
        db.session.get(Booking, bid).status = status
        db.session.commit()
        assert NOTE in client.get("/my-rentals").data, status


def test_card_note_absent_when_requested_or_completed(client, app):
    cat_id = _cat(app)
    bid = _booking_between(client, app, cat_id)

    # still REQUESTED (not yet accepted) -> no note
    assert NOTE not in client.get("/my-rentals").data

    client.post(f"/bookings/{bid}/accept", follow_redirects=True)
    db.session.get(Booking, bid).status = "completed"
    db.session.commit()
    assert NOTE not in client.get("/my-rentals").data


def test_card_note_not_shown_to_renter(client, app):
    cat_id = _cat(app)
    bid = _booking_between(client, app, cat_id)
    client.post(f"/bookings/{bid}/accept", follow_redirects=True)

    client.post("/logout")
    client.post("/login", data={"email": "renter@example.com", "password": "supersecret"})
    assert NOTE not in client.get("/my-rentals").data
