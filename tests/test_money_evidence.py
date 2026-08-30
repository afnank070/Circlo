"""M4 smoke tests — money (ledger, semi-manual payment) + before/after evidence.

State-machine focused: exercises the service layer directly (the future
``/api/v1`` calls the same functions). Storage is stubbed so no MinIO is needed.
"""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Booking, Category, EvidenceMedia, LedgerEntry, Listing, User
from app.models.booking import (
    STATUS_ACTIVE,
    STATUS_AWAITING_PAYMENT,
    STATUS_COMPLETED,
    STATUS_PAID,
    STATUS_REQUESTED,
    STATUS_RETURNED,
)
from app.models.ledger_entry import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_COMMISSION,
    TYPE_DEPOSIT,
    TYPE_PAYOUT,
    TYPE_REFUND,
    TYPE_RENTAL_PAYMENT,
)
from app.models.user import ROLE_ADMIN, VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import booking as booking_service
from app.services import evidence as evidence_service
from app.services import ledger as ledger_service
from app.services import payments as payments_service

TODAY = date.today()
START = TODAY + timedelta(days=3)
END = TODAY + timedelta(days=5)  # inclusive -> 3 rental days


class _FakeUpload:
    def __init__(self, name="photo.jpg", mimetype="image/jpeg"):
        self.filename = name
        self.mimetype = mimetype
        self.stream = io.BytesIO(b"fake-image-bytes")


@pytest.fixture(autouse=True)
def _stub_storage(monkeypatch):
    monkeypatch.setattr(
        "app.services.storage.upload_fileobj",
        lambda *a, **k: (k.get("key") or (a[1] if len(a) > 1 else "k")),
    )
    monkeypatch.setattr(
        "app.services.storage.presigned_url", lambda key, **k: f"https://stub/{key}"
    )


def _user(name, email, *, admin=False):
    u = auth_service.create_user(name, email, "supersecret")
    u.verification_status = VERIFICATION_APPROVED
    if admin:
        u.role = ROLE_ADMIN
    db.session.commit()
    return u


def _scenario(app):
    """Owner + renter + admin + an accepted booking. Returns their ids."""
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()

        owner = _user("Owner", "owner@example.com")
        renter = _user("Renter", "renter@example.com")
        admin = _user("Admin", "admin@example.com", admin=True)

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
        booking_service.accept(b, owner=owner)
        return {"owner": owner.id, "renter": renter.id, "admin": admin.id, "booking": b.id}


def test_request_snapshots_rental_amount(app):
    ids = _scenario(app)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        assert Decimal(b.rental_amount) == Decimal("2400.00")  # 800 * 3 days


def test_renter_marks_paid_then_admin_confirms(app):
    ids = _scenario(app)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        payments_service.mark_awaiting_payment(b, renter=renter)
        assert b.status == STATUS_AWAITING_PAYMENT

        assert [x.id for x in payments_service.bookings_awaiting_payment_confirmation()] == [b.id]

        admin = db.session.get(User, ids["admin"])
        payments_service.confirm_payment_received(b, admin=admin)
        assert b.status == STATUS_PAID

        entries = {e.type: e for e in ledger_service.entries_for_booking(b)}
        assert entries[TYPE_RENTAL_PAYMENT].status == STATUS_CONFIRMED
        assert Decimal(entries[TYPE_RENTAL_PAYMENT].amount) == Decimal("2400.00")
        assert Decimal(entries[TYPE_DEPOSIT].amount) == Decimal("5000.00")
        assert entries[TYPE_DEPOSIT].confirmed_by == admin.id


def test_confirm_payment_wrong_state_raises(app):
    ids = _scenario(app)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        admin = db.session.get(User, ids["admin"])
        with pytest.raises(payments_service.InvalidPaymentTransition):
            payments_service.confirm_payment_received(b, admin=admin)


def _advance_to_paid(app, ids):
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        admin = db.session.get(User, ids["admin"])
        payments_service.mark_awaiting_payment(b, renter=renter)
        payments_service.confirm_payment_received(b, admin=admin)


def test_evidence_advances_state_only_when_both_upload(app):
    ids = _scenario(app)
    _advance_to_paid(app, ids)

    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        owner = db.session.get(User, ids["owner"])

        evidence_service.upload_evidence(b, renter, phase="before", file=_FakeUpload())
        assert b.status == STATUS_PAID  # owner hasn't uploaded yet
        evidence_service.upload_evidence(b, owner, phase="before", file=_FakeUpload())
        assert b.status == STATUS_ACTIVE

        # after phase
        evidence_service.upload_evidence(b, renter, phase="after", file=_FakeUpload())
        assert b.status == STATUS_ACTIVE
        evidence_service.upload_evidence(b, owner, phase="after", file=_FakeUpload())
        assert b.status == STATUS_RETURNED

        assert EvidenceMedia.query.filter_by(booking_id=b.id).count() == 4


def test_evidence_rejects_non_party_and_wrong_phase_state(app):
    ids = _scenario(app)
    _advance_to_paid(app, ids)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        stranger = _user("Nosy", "nosy@example.com")
        with pytest.raises(evidence_service.EvidencePermissionError):
            evidence_service.upload_evidence(b, stranger, phase="before", file=_FakeUpload())

        renter = db.session.get(User, ids["renter"])
        with pytest.raises(evidence_service.InvalidEvidenceUpload):
            evidence_service.upload_evidence(b, renter, phase="after", file=_FakeUpload())


def test_full_cycle_completion_and_payout(app):
    ids = _scenario(app)
    _advance_to_paid(app, ids)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        owner = db.session.get(User, ids["owner"])
        admin = db.session.get(User, ids["admin"])

        for phase in ("before", "after"):
            evidence_service.upload_evidence(b, renter, phase=phase, file=_FakeUpload())
            evidence_service.upload_evidence(b, owner, phase=phase, file=_FakeUpload())
        assert b.status == STATUS_RETURNED

        booking_service.confirm_return(b, owner=owner)
        assert b.status == STATUS_COMPLETED

        entries = {e.type: e for e in ledger_service.entries_for_booking(b)}
        assert Decimal(entries[TYPE_COMMISSION].amount) == Decimal("480.00")   # 20% of 2400
        assert Decimal(entries[TYPE_PAYOUT].amount) == Decimal("1920.00")      # 2400 - 480
        assert Decimal(entries[TYPE_REFUND].amount) == Decimal("5000.00")      # full deposit
        for t in (TYPE_COMMISSION, TYPE_PAYOUT, TYPE_REFUND):
            assert entries[t].status == STATUS_PENDING

        assert [x.id for x in payments_service.bookings_awaiting_payout()] == [b.id]

        payments_service.confirm_payout(b, admin=admin)
        assert not ledger_service.has_pending_entries(b)
        assert payments_service.bookings_awaiting_payout() == []


def test_confirm_return_requires_returned_state(app):
    ids = _scenario(app)
    _advance_to_paid(app, ids)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        owner = db.session.get(User, ids["owner"])
        with pytest.raises(booking_service.InvalidBookingTransition):
            booking_service.confirm_return(b, owner=owner)


def test_cannot_cancel_after_payment_confirmed(app):
    ids = _scenario(app)
    _advance_to_paid(app, ids)
    with app.app_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        with pytest.raises(booking_service.InvalidBookingTransition):
            booking_service.cancel(b, user=renter)


def test_admin_payments_page_requires_admin(client, app):
    ids = _scenario(app)
    # not logged in
    resp = client.get("/admin/payments")
    assert resp.status_code == 302

    client.post("/login", data={"email": "renter@example.com", "password": "supersecret"})
    assert client.get("/admin/payments").status_code == 403

    client.post("/logout")
    client.post("/login", data={"email": "admin@example.com", "password": "supersecret"})
    resp = client.get("/admin/payments")
    assert resp.status_code == 200
    assert b"Awaiting payment confirmation" in resp.data
