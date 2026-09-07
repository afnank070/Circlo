"""Cancellation-flow smoke tests (blueprint §5, §7).

Stage-dependent rules:

* REQUESTED / ACCEPTED   — either party cancels instantly, no money involved.
* AWAITING_PAYMENT / PAID — either party raises a request; an admin confirms the
  refund and cancels the booking.
* HANDED_OVER / ACTIVE /  — no cancellation; the dispute flow takes over.
  RETURNED

The other party is emailed whenever a cancellation happens or is requested.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Booking, CancellationRequest, Category, Listing, User
from app.models.booking import (
    STATUS_ACTIVE,
    STATUS_AWAITING_PAYMENT,
    STATUS_CANCELLED,
    STATUS_PAID,
    STATUS_REQUESTED,
)
from app.models.cancellation_request import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from app.models.ledger_entry import STATUS_CONFIRMED as LEDGER_CONFIRMED
from app.models.ledger_entry import TYPE_REFUND
from app.models.user import ROLE_ADMIN, VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import booking as booking_service
from app.services import cancellation as cancellation_service
from app.services import ledger as ledger_service
from app.services import payments as payments_service

TODAY = date.today()
START = TODAY + timedelta(days=3)
END = TODAY + timedelta(days=5)  # inclusive -> 3 rental days


@pytest.fixture()
def sent_emails(monkeypatch):
    """Capture every outbound email (overrides the conftest no-op stub)."""
    box = []
    monkeypatch.setattr(
        "app.services.email.send_email",
        lambda to, subject, body_html, **kw: box.append((to, subject)) or True,
        raising=True,
    )
    return box


def _user(name, email, *, admin=False):
    u = auth_service.create_user(name, email, "supersecret", phone="03001234567")
    u.verification_status = VERIFICATION_APPROVED
    if admin:
        u.role = ROLE_ADMIN
    db.session.commit()
    return u


def _scenario(app):
    """Owner + renter + admin + a fresh REQUESTED booking. Returns ids."""
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()

        owner = _user("Olivia Owner", "owner@example.com")
        renter = _user("Ravi Renter", "renter@example.com")
        admin = _user("Amy Admin", "admin@example.com", admin=True)

        listing = Listing(
            owner_id=owner.id, title="Bosch Hammer Drill", description="d",
            category_id=cat.id, city="Islamabad", area="F-8",
            price_per_day=800, deposit_amount=5000, status="active",
        )
        db.session.add(listing)
        db.session.commit()

        b = booking_service.request_to_rent(
            listing, renter, start_date=START, end_date=END, message="hi"
        )
        return {
            "owner": owner.id, "renter": renter.id,
            "admin": admin.id, "booking": b.id,
        }


def _set_status(app, booking_id, status):
    # Write on the fixture's already-active session (a nested app_context can
    # land on a separate SQLite connection whose commit a later request misses).
    db.session.get(Booking, booking_id).status = status
    db.session.commit()


def _to_paid(app, ids):
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        admin = db.session.get(User, ids["admin"])
        booking_service.accept(b, owner=db.session.get(User, ids["owner"]))
        payments_service.mark_awaiting_payment(b, renter=renter)
        payments_service.confirm_payment_received(b, admin=admin)


# --- Stage 1: REQUESTED / ACCEPTED — free instant cancel ----------------------
def test_requested_either_party_cancels_freely(app, sent_emails):
    ids = _scenario(app)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        booking_service.cancel(b, user=renter)
        assert b.status == STATUS_CANCELLED
    # The owner (the other party) got an email.
    assert any(to == "owner@example.com" for to, _ in sent_emails)


def test_accepted_owner_cancels_freely(app, sent_emails):
    ids = _scenario(app)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        owner = db.session.get(User, ids["owner"])
        booking_service.accept(b, owner=owner)
        booking_service.cancel(b, user=owner)
        assert b.status == STATUS_CANCELLED
    assert any(to == "renter@example.com" for to, _ in sent_emails)


def test_available_action_is_cancel_before_payment(app):
    ids = _scenario(app)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        assert cancellation_service.available_action(b, renter) == "cancel"
        booking_service.accept(b, owner=db.session.get(User, ids["owner"]))
        assert cancellation_service.available_action(b, renter) == "cancel"


# --- Stage 2: AWAITING_PAYMENT / PAID — admin-confirmed request ---------------
def test_cannot_instant_cancel_once_awaiting_payment(app):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_AWAITING_PAYMENT)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        with pytest.raises(booking_service.InvalidBookingTransition):
            booking_service.cancel(b, user=renter)
        assert cancellation_service.available_action(b, renter) == "request"


def test_request_cancellation_creates_pending_and_notifies(app, sent_emails):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_AWAITING_PAYMENT)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        req = cancellation_service.request_cancellation(b, renter, reason="Changed plans")
        assert req.status == STATUS_PENDING
        assert b.status == STATUS_AWAITING_PAYMENT  # unchanged until admin acts
        assert cancellation_service.available_action(b, renter) == "pending"
        assert [r.id for r in cancellation_service.pending_requests()] == [req.id]
    assert any(to == "owner@example.com" for to, _ in sent_emails)


def test_double_request_is_rejected(app):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_PAID)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        owner = db.session.get(User, ids["owner"])
        cancellation_service.request_cancellation(b, renter)
        with pytest.raises(cancellation_service.CancellationAlreadyRequested):
            cancellation_service.request_cancellation(b, owner)


def test_admin_confirms_cancellation_records_refund_and_cancels(app, sent_emails):
    ids = _scenario(app)
    _to_paid(app, ids)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        admin = db.session.get(User, ids["admin"])

        req = cancellation_service.request_cancellation(b, renter)
        cancellation_service.confirm_cancellation(req, admin=admin)

        assert b.status == STATUS_CANCELLED
        assert db.session.get(CancellationRequest, req.id).status == STATUS_CONFIRMED

        refunds = [
            e for e in ledger_service.entries_for_booking(b)
            if e.type == TYPE_REFUND
        ]
        assert len(refunds) == 1
        # rental 2400 + deposit 5000 was paid in -> full refund recorded, confirmed
        assert Decimal(refunds[0].amount) == Decimal("7400.00")
        assert refunds[0].status == LEDGER_CONFIRMED
        assert refunds[0].confirmed_by == admin.id
    # both parties emailed
    tos = {to for to, _ in sent_emails}
    assert {"owner@example.com", "renter@example.com"} <= tos


def test_admin_rejects_cancellation_leaves_booking(app, sent_emails):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_PAID)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        admin = db.session.get(User, ids["admin"])
        req = cancellation_service.request_cancellation(b, renter)
        cancellation_service.reject_cancellation(req, admin=admin)
        assert db.session.get(CancellationRequest, req.id).status == STATUS_REJECTED
        assert b.status == STATUS_PAID
        assert cancellation_service.pending_requests() == []
    assert any(to == "renter@example.com" for to, _ in sent_emails)


def test_awaiting_payment_refund_is_zero_when_never_confirmed(app):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_AWAITING_PAYMENT)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        admin = db.session.get(User, ids["admin"])
        req = cancellation_service.request_cancellation(b, renter)
        cancellation_service.confirm_cancellation(req, admin=admin)
        assert b.status == STATUS_CANCELLED
        # No confirmed inflow entries -> no refund entry created.
        assert [e for e in ledger_service.entries_for_booking(b)] == []


# --- Stage 3: HANDED_OVER or later — no cancellation, dispute instead ---------
def test_active_booking_cannot_be_cancelled(app):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_ACTIVE)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        with pytest.raises(booking_service.InvalidBookingTransition):
            booking_service.cancel(b, user=renter)
        with pytest.raises(cancellation_service.CancellationNotAllowed):
            cancellation_service.request_cancellation(b, renter)
        assert cancellation_service.available_action(b, renter) == "dispute"


def test_completed_booking_offers_no_cancel_action(app):
    ids = _scenario(app)
    _set_status(app, ids["booking"], "completed")
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        assert cancellation_service.available_action(b, renter) is None


# --- Permissions -------------------------------------------------------------
def test_non_party_cannot_request_or_see_action(app):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_PAID)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        stranger = _user("Nosy Neighbour", "nosy@example.com")
        assert cancellation_service.available_action(b, stranger) is None
        with pytest.raises(cancellation_service.CancellationNotAllowed):
            cancellation_service.request_cancellation(b, stranger)


# --- Route + template smoke -------------------------------------------------
def _login(client, email):
    client.post("/login", data={"email": email, "password": "supersecret"})


def test_my_rentals_shows_correct_control_per_stage(client, app):
    ids = _scenario(app)

    # ACCEPTED -> instant "Cancel booking"
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        booking_service.accept(b, owner=db.session.get(User, ids["owner"]))
    _login(client, "renter@example.com")
    page = client.get("/my-rentals").data
    assert b"Cancel booking" in page
    assert b"Request cancellation" not in page

    # PAID -> "Request cancellation", no instant cancel
    _set_status(app, ids["booking"], STATUS_PAID)
    page = client.get("/my-rentals").data
    assert b"Request cancellation" in page
    assert b"Cancel booking" not in page

    # ACTIVE -> no cancel control at all; the dispute flow ("Report a problem")
    # is the only way out once the item is handed over.
    _set_status(app, ids["booking"], STATUS_ACTIVE)
    page = client.get("/my-rentals").data
    assert b"Request cancellation" not in page
    assert b"Cancel booking" not in page
    assert b"Report a problem" in page


def test_request_cancellation_route_creates_request(client, app, sent_emails):
    ids = _scenario(app)
    _set_status(app, ids["booking"], STATUS_PAID)
    _login(client, "renter@example.com")
    resp = client.post(
        f"/bookings/{ids['booking']}/request-cancellation",
        data={"reason": "Trip got cancelled"}, follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Cancellation requested" in resp.data
    with app.app_context():
        reqs = CancellationRequest.query.filter_by(booking_id=ids["booking"]).all()
        assert len(reqs) == 1 and reqs[0].status == STATUS_PENDING


def test_admin_payments_page_lists_and_confirms_cancellation(client, app):
    ids = _scenario(app)
    _to_paid(app, ids)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        req = cancellation_service.request_cancellation(b, renter)
        req_id = req.id

    _login(client, "admin@example.com")
    page = client.get("/admin/payments").data
    assert b"Cancellation requests" in page
    assert b"Bosch Hammer Drill" in page

    resp = client.post(
        f"/admin/cancellations/{req_id}/confirm", follow_redirects=True
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Booking, ids["booking"]).status == STATUS_CANCELLED
