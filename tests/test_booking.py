"""M3 smoke tests — rental request / accept / reject / cancel state machine.

The rental unit is hours: a request carries a start date + start time + a
number of hours (minimum 1).
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import Booking, Category, Listing
from app.models.booking import STATUS_ACCEPTED, STATUS_CANCELLED, STATUS_REQUESTED
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service

TODAY = date.today()
START = (TODAY + timedelta(days=3)).isoformat()
START_TIME = "09:00"
HOURS = "4"


def _make_category(app, name="Tools", slug="tools"):
    with app.app_context():
        cat = Category(name=name, slug=slug)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _signup_verified(client, email):
    client.post(
        "/signup",
        data={"name": email.split("@")[0], "email": email, "phone": "03001234567",
              "password": "supersecret", "confirm": "supersecret"},
        follow_redirects=True,
    )
    user = auth_service.get_user_by_email(email)
    user.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return user


def _make_listing(app, owner_email, category_id, title="Bosch Hammer Drill"):
    with app.app_context():
        owner = auth_service.get_user_by_email(owner_email)
        listing = Listing(
            owner_id=owner.id, title=title, description="desc",
            category_id=category_id, city="Islamabad", area="F-8",
            price_per_hour=100, deposit_amount=5000, status="active",
        )
        db.session.add(listing)
        db.session.commit()
        return listing.id


def _request(client, listing_id, start=START, start_time=START_TIME, hours=HOURS,
             message="Please"):
    return client.post(
        f"/listings/{listing_id}/request",
        data={"start_date": start, "start_time": start_time, "hours": hours,
              "message": message},
        follow_redirects=True,
    )


def test_request_requires_login(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")

    resp = client.post(f"/listings/{listing_id}/request", data={"start_date": START, "start_time": START_TIME, "hours": HOURS})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_request_requires_verification(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")

    client.post("/signup", data={"name": "Unverified", "email": "unverified@example.com",
                                  "phone": "03001234567",
                                  "password": "supersecret", "confirm": "supersecret"},
                follow_redirects=True)
    resp = _request(client, listing_id)
    assert resp.status_code == 200
    assert b"Verify your identity to rent items" in resp.data
    with app.app_context():
        assert Booking.query.count() == 0


def test_owner_cannot_rent_own_listing(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)

    resp = _request(client, listing_id)
    assert resp.status_code == 200
    assert b"can&#39;t rent your own listing" in resp.data or b"can't rent your own listing" in resp.data
    with app.app_context():
        assert Booking.query.count() == 0


def test_request_creates_pending_booking(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com")

    resp = _request(client, listing_id)
    assert resp.status_code == 200
    assert b"Rental request sent" in resp.data

    with app.app_context():
        booking = Booking.query.filter_by(listing_id=listing_id).first()
        assert booking is not None
        assert booking.status == STATUS_REQUESTED
        assert booking.message_from_renter == "Please"
        assert int(booking.deposit_amount) == 5000
        owner = auth_service.get_user_by_email("owner@example.com")
        assert booking.owner_id == owner.id


def test_owner_accepts_request(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com")
    _request(client, listing_id)
    client.post("/logout")

    client.post("/login", data={"email": "owner@example.com", "password": "supersecret"})
    with app.app_context():
        booking_id = Booking.query.filter_by(listing_id=listing_id).first().id

    resp = client.post(f"/bookings/{booking_id}/accept", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Rental request accepted" in resp.data
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == STATUS_ACCEPTED


def test_owner_rejects_request(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com")
    _request(client, listing_id)
    client.post("/logout")

    client.post("/login", data={"email": "owner@example.com", "password": "supersecret"})
    with app.app_context():
        booking_id = Booking.query.filter_by(listing_id=listing_id).first().id

    resp = client.post(f"/bookings/{booking_id}/reject", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Rental request rejected" in resp.data
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == STATUS_CANCELLED


def test_non_owner_cannot_accept(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com")
    _request(client, listing_id)
    with app.app_context():
        booking_id = Booking.query.filter_by(listing_id=listing_id).first().id

    # renter (not the owner) tries to accept their own request
    resp = client.post(f"/bookings/{booking_id}/accept")
    assert resp.status_code == 403


def test_renter_can_cancel_pending_request(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com")
    _request(client, listing_id)
    with app.app_context():
        booking_id = Booking.query.filter_by(listing_id=listing_id).first().id

    resp = client.post(f"/bookings/{booking_id}/cancel", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Booking cancelled" in resp.data
    with app.app_context():
        assert db.session.get(Booking, booking_id).status == STATUS_CANCELLED


def test_accept_rejects_overlapping_hours_but_allows_back_to_back(client, app):
    """2pm-4pm conflicts with an accepted 3pm-5pm; a 5pm-7pm slot does not."""
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")

    # renter A: 3pm, 2 hours (3pm-5pm)
    _signup_verified(client, "renterA@example.com")
    _request(client, listing_id, start=START, start_time="15:00", hours="2")
    client.post("/logout")

    # renter B: 2pm, 2 hours (2pm-4pm) — overlaps A by an hour
    _signup_verified(client, "renterB@example.com")
    _request(client, listing_id, start=START, start_time="14:00", hours="2")
    client.post("/logout")

    # renter C: 5pm, 2 hours (5pm-7pm) — starts exactly when A ends, no overlap
    _signup_verified(client, "renterC@example.com")
    _request(client, listing_id, start=START, start_time="17:00", hours="2")
    client.post("/logout")

    client.post("/login", data={"email": "owner@example.com", "password": "supersecret"})
    with app.app_context():
        b = Booking.query.filter_by(listing_id=listing_id).order_by(Booking.id).all()
        a_id, b_id, c_id = b[0].id, b[1].id, b[2].id

    resp = client.post(f"/bookings/{a_id}/accept", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Booking, a_id).status == STATUS_ACCEPTED

    resp = client.post(f"/bookings/{b_id}/accept", follow_redirects=True)
    assert b"overlapping hours" in resp.data
    with app.app_context():
        assert db.session.get(Booking, b_id).status == STATUS_REQUESTED

    resp = client.post(f"/bookings/{c_id}/accept", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Booking, c_id).status == STATUS_ACCEPTED


def test_my_rentals_requires_login(client):
    resp = client.get("/my-rentals")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_my_rentals_shows_owner_and_renter_sections(client, app):
    category_id = _make_category(app)
    _signup_verified(client, "owner@example.com")
    listing_id = _make_listing(app, "owner@example.com", category_id)
    client.post("/logout")
    _signup_verified(client, "renter@example.com")
    _request(client, listing_id)

    resp = client.get("/my-rentals")
    assert resp.status_code == 200
    assert b"Bosch Hammer Drill" in resp.data
    assert b"Pending" in resp.data
    assert b"As a renter" in resp.data
