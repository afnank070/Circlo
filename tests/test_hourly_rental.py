"""Hourly rental-unit smoke tests.

The rental unit is hours, not days:

* the rental subtotal is ``price_per_hour * duration_hours``;
* double-booking is checked as datetime-range overlap at hour precision
  (2pm-4pm conflicts with an existing 3pm-5pm, but not with a 5pm-7pm);
* the flat owner-set deposit does NOT scale with the number of hours.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Booking, Category, Listing, User
from app.models.booking import STATUS_ACCEPTED, STATUS_REQUESTED
from app.services import booking as booking_service


BASE = (datetime.now() + timedelta(days=2)).replace(
    hour=0, minute=0, second=0, microsecond=0
)


@pytest.fixture()
def world(app):
    """An owner, a renter and one listing at Rs 250/hour, Rs 3000 deposit."""
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        owner = User(name="Owen Owner", email="owner@h.test",
                     phone="03001112222", verification_status="approved")
        renter = User(name="Rita Renter", email="renter@h.test",
                      phone="03003334444", verification_status="approved")
        owner.set_password("x"); renter.set_password("x")
        db.session.add_all([cat, owner, renter])
        db.session.flush()
        listing = Listing(
            owner_id=owner.id, title="Pressure Washer", description="d",
            category_id=cat.id, city="Islamabad", area="F-8",
            price_per_hour=Decimal("250"), deposit_amount=Decimal("3000"),
            status="active",
        )
        db.session.add(listing)
        db.session.commit()
        return {"listing_id": listing.id, "owner_id": owner.id,
                "renter_id": renter.id}


def _at(hour):
    return BASE + timedelta(hours=hour)


def _book(world, *, start_hour, hours, status=STATUS_REQUESTED):
    b = Booking(
        listing_id=world["listing_id"], renter_id=world["renter_id"],
        owner_id=world["owner_id"], status=status,
        start_datetime=_at(start_hour), duration_hours=hours,
        deposit_amount=Decimal("3000"),
    )
    b.rental_amount = Decimal("250") * hours
    db.session.add(b)
    db.session.commit()
    return b


# --- subtotal -------------------------------------------------------------
def test_subtotal_is_price_per_hour_times_hours(app, world):
    with app.app_context():
        listing = db.session.get(Listing, world["listing_id"])
        renter = db.session.get(User, world["renter_id"])
        b = booking_service.request_to_rent(
            listing, renter, start_datetime=_at(9), duration_hours=5,
        )
        assert Decimal(b.rental_amount) == Decimal("1250.00")  # 250 * 5
        assert booking_service.rental_amount_for(b) == Decimal("1250")


def test_deposit_is_flat_and_does_not_scale_with_hours(app, world):
    with app.app_context():
        listing = db.session.get(Listing, world["listing_id"])
        renter = db.session.get(User, world["renter_id"])
        short = booking_service.request_to_rent(
            listing, renter, start_datetime=_at(8), duration_hours=1,
        )
        long = booking_service.request_to_rent(
            listing, renter, start_datetime=_at(20), duration_hours=12,
        )
        assert Decimal(short.deposit_amount) == Decimal("3000")
        assert Decimal(long.deposit_amount) == Decimal("3000")


def test_minimum_rental_is_one_hour(app, world):
    with app.app_context():
        listing = db.session.get(Listing, world["listing_id"])
        renter = db.session.get(User, world["renter_id"])
        with pytest.raises(booking_service.InvalidBookingRequest):
            booking_service.request_to_rent(
                listing, renter, start_datetime=_at(9), duration_hours=0,
            )


def test_request_requires_renter_phone(app, world):
    with app.app_context():
        listing = db.session.get(Listing, world["listing_id"])
        renter = db.session.get(User, world["renter_id"])
        renter.phone = None
        db.session.commit()
        with pytest.raises(booking_service.InvalidBookingRequest):
            booking_service.request_to_rent(
                listing, renter, start_datetime=_at(9), duration_hours=2,
            )


def test_accept_requires_owner_phone(app, world):
    with app.app_context():
        owner = db.session.get(User, world["owner_id"])
        b = _book(world, start_hour=9, hours=2)
        owner.phone = ""
        db.session.commit()
        with pytest.raises(booking_service.InvalidBookingTransition):
            booking_service.accept(b, owner=owner)


def test_start_time_in_the_past_is_rejected(app, world):
    with app.app_context():
        listing = db.session.get(Listing, world["listing_id"])
        renter = db.session.get(User, world["renter_id"])
        with pytest.raises(booking_service.InvalidBookingRequest):
            booking_service.request_to_rent(
                listing, renter,
                start_datetime=datetime.now() - timedelta(hours=1),
                duration_hours=2,
            )


# --- hour-level overlap --------------------------------------------------
def test_overlap_detection_at_the_hour(app, world):
    with app.app_context():
        # An accepted booking holding 3pm-5pm.
        _book(world, start_hour=15, hours=2, status=STATUS_ACCEPTED)

        # 2pm-4pm overlaps by an hour -> conflict.
        assert booking_service.has_overlapping_acceptance(
            world["listing_id"], _at(14), _at(16)
        ) is True

        # 4pm-6pm overlaps by an hour -> conflict.
        assert booking_service.has_overlapping_acceptance(
            world["listing_id"], _at(16), _at(18)
        ) is True

        # 5pm-7pm starts exactly when the held slot ends -> no conflict.
        assert booking_service.has_overlapping_acceptance(
            world["listing_id"], _at(17), _at(19)
        ) is False

        # 8am-10am, well clear -> no conflict.
        assert booking_service.has_overlapping_acceptance(
            world["listing_id"], _at(8), _at(10)
        ) is False


def test_accept_blocks_overlapping_hours_allows_back_to_back(app, world):
    with app.app_context():
        owner = db.session.get(User, world["owner_id"])
        held = _book(world, start_hour=15, hours=2)          # 3pm-5pm
        conflicting = _book(world, start_hour=14, hours=2)   # 2pm-4pm
        back_to_back = _book(world, start_hour=17, hours=2)  # 5pm-7pm

        booking_service.accept(held, owner=owner)

        with pytest.raises(booking_service.BookingConflict):
            booking_service.accept(conflicting, owner=owner)
        assert db.session.get(Booking, conflicting.id).status == STATUS_REQUESTED

        booking_service.accept(back_to_back, owner=owner)
        assert db.session.get(Booking, back_to_back.id).status == STATUS_ACCEPTED


def test_same_day_different_hours_do_not_conflict(app, world):
    """Two bookings on the same calendar day but non-overlapping hours are fine
    (the old day-based check would have blocked this)."""
    with app.app_context():
        owner = db.session.get(User, world["owner_id"])
        morning = _book(world, start_hour=9, hours=2)    # 9am-11am
        afternoon = _book(world, start_hour=14, hours=3)  # 2pm-5pm

        booking_service.accept(morning, owner=owner)
        booking_service.accept(afternoon, owner=owner)
        assert db.session.get(Booking, afternoon.id).status == STATUS_ACCEPTED


# --- end-to-end request flow through the web route ---------------------
def test_request_route_accepts_date_time_and_hours(client, app, world):
    client.post("/login", data={"email": "renter@h.test", "password": "x"})
    start_date = BASE.date().isoformat()
    resp = client.post(
        f"/listings/{world['listing_id']}/request",
        data={"start_date": start_date, "start_time": "13:00", "hours": "2",
              "message": "for the driveway"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        b = Booking.query.filter_by(listing_id=world["listing_id"]).one()
        assert b.start_datetime == datetime.combine(BASE.date(),
                                                    datetime.min.time()).replace(hour=13)
        assert b.duration_hours == 2
        assert Decimal(b.rental_amount) == Decimal("500.00")  # 250 * 2
        assert b.end_datetime == b.start_datetime + timedelta(hours=2)
