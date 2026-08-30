"""M5 smoke tests — email, password reset, notifications, reviews, disputes,
trust-fund bookkeeping. Real SMTP is never touched: ``email.send_email`` is
mocked and its calls recorded.
"""
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Booking, Category, Dispute, Listing, PasswordResetToken, Review, User
from app.models.user import ROLE_ADMIN, VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import booking as booking_service
from app.services import disputes as disputes_service
from app.services import evidence as evidence_service
from app.services import password_reset as reset_service
from app.services import payments as payments_service
from app.services import reviews as reviews_service
from app.services import trust_fund as trust_fund_service

TODAY = date.today()
START = TODAY + timedelta(days=3)
END = TODAY + timedelta(days=5)


class _FakeUpload:
    def __init__(self):
        self.filename = "p.jpg"
        self.mimetype = "image/jpeg"
        self.stream = io.BytesIO(b"bytes")


@pytest.fixture(autouse=True)
def _mock_email(monkeypatch):
    sent = []

    def _fake_send(to, subject, body_html):
        sent.append({"to": to, "subject": subject, "body": body_html})
        return True

    monkeypatch.setattr("app.services.email.send_email", _fake_send)
    monkeypatch.setattr("app.services.storage.upload_fileobj", lambda *a, **k: "key")
    monkeypatch.setattr("app.services.storage.presigned_url", lambda k, **kw: "http://x/" + k)
    return sent


def _user(name, email, *, admin=False):
    u = auth_service.create_user(name, email, "supersecret")
    u.verification_status = VERIFICATION_APPROVED
    if admin:
        u.role = ROLE_ADMIN
    db.session.commit()
    return u


def _completed_booking(app):
    """Run a booking all the way to COMPLETED. Returns ids dict (inside no ctx)."""
    with app.test_request_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _user("Olivia Owner", "owner@example.com")
        renter = _user("Ravi Renter", "renter@example.com")
        admin = _user("Amy Admin", "admin@example.com", admin=True)
        listing = Listing(
            owner_id=owner.id, title="Bosch Drill", description="d", category_id=cat.id,
            city="Islamabad", area="F-8", price_per_day=800, deposit_amount=5000,
            status="active",
        )
        db.session.add(listing)
        db.session.commit()

        b = booking_service.request_to_rent(listing, renter, start_date=START, end_date=END)
        booking_service.accept(b, owner=owner)
        payments_service.mark_awaiting_payment(b, renter=renter)
        payments_service.confirm_payment_received(b, admin=admin)
        for phase in ("before", "after"):
            evidence_service.upload_evidence(b, renter, phase=phase, file=_FakeUpload())
            evidence_service.upload_evidence(b, owner, phase=phase, file=_FakeUpload())
        booking_service.confirm_return(b, owner=owner)
        return {"owner": owner.id, "renter": renter.id, "admin": admin.id, "booking": b.id}


# --- Password reset -------------------------------------------------------
def test_forgot_password_flow(client, app, _mock_email):
    client.post("/signup", data={"name": "Sam", "email": "sam@example.com",
                                 "password": "originalpass", "confirm": "originalpass"},
                follow_redirects=True)
    client.post("/logout")

    resp = client.post("/forgot-password", data={"email": "sam@example.com"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert any("sam@example.com" == m["to"] for m in _mock_email)
    body = next(m["body"] for m in _mock_email if m["to"] == "sam@example.com")
    token = re.search(r"/reset-password/([A-Za-z0-9_\-]+)", body).group(1)

    assert client.get(f"/reset-password/{token}").status_code == 200
    resp = client.post(f"/reset-password/{token}",
                       data={"password": "brandnewpass", "confirm": "brandnewpass"},
                       follow_redirects=True)
    assert b"Password updated" in resp.data

    assert auth_service.authenticate("sam@example.com", "brandnewpass") is not None
    assert auth_service.authenticate("sam@example.com", "originalpass") is None

    # token is single-use
    resp = client.post(f"/reset-password/{token}",
                       data={"password": "thirdpass123", "confirm": "thirdpass123"},
                       follow_redirects=True)
    assert b"invalid or has expired" in resp.data


def test_reset_token_expiry_and_no_enumeration(app):
    with app.test_request_context():
        u = _user("Exp", "exp@example.com")
        assert reset_service.request_reset("exp@example.com") is True
        tok = PasswordResetToken.query.filter_by(user_id=u.id).first()
        tok.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        # expired -> not valid
        assert not tok.is_valid()
        # unknown email -> silently no-op, no crash
        assert reset_service.request_reset("nobody@example.com") is False


# --- Notifications ------------------------------------------------------
def test_notifications_fire_on_events(client, app, _mock_email):
    with app.test_request_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _user("Owner", "owner@example.com")
        renter = _user("Renter", "renter@example.com")
        listing = Listing(owner_id=owner.id, title="Drill", description="d",
                          category_id=cat.id, city="Islamabad", area="F-8",
                          price_per_day=800, deposit_amount=5000, status="active")
        db.session.add(listing)
        db.session.commit()
        lid = listing.id

    _mock_email.clear()
    client.post("/login", data={"email": "renter@example.com", "password": "supersecret"})
    client.post(f"/listings/{lid}/request",
                data={"start_date": START.isoformat(), "end_date": END.isoformat()},
                follow_redirects=True)

    # owner gets a "new rental request" email
    assert any(m["to"] == "owner@example.com" and "request" in m["subject"].lower()
               for m in _mock_email)


# --- Reviews -----------------------------------------------------------
def test_reviews_after_completed_update_rating(app):
    ids = _completed_booking(app)
    with app.test_request_context():
        b = db.session.get(Booking, ids["booking"])
        owner = db.session.get(User, ids["owner"])
        renter = db.session.get(User, ids["renter"])

        reviews_service.leave_review(b, renter, rating=5, comment="Great owner")
        reviews_service.leave_review(b, owner, rating=4, comment="Fine renter")

        assert float(db.session.get(User, ids["owner"]).rating) == 5.0
        assert float(db.session.get(User, ids["renter"]).rating) == 4.0
        assert db.session.get(User, ids["owner"]).review_count == 1

        # one review per person per booking
        with pytest.raises(reviews_service.AlreadyReviewed):
            reviews_service.leave_review(b, renter, rating=3)


def test_cannot_review_incomplete_booking(app):
    with app.test_request_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _user("O", "o@example.com")
        renter = _user("R", "r@example.com")
        listing = Listing(owner_id=owner.id, title="X", description="d", category_id=cat.id,
                          city="I", area="A", price_per_day=100, deposit_amount=100,
                          status="active")
        db.session.add(listing)
        db.session.commit()
        b = booking_service.request_to_rent(listing, renter, start_date=START, end_date=END)
        assert reviews_service.can_review(b, renter) is False
        with pytest.raises(reviews_service.ReviewNotAllowed):
            reviews_service.leave_review(b, renter, rating=5)


# --- Disputes + trust fund ------------------------------------------
def test_dispute_open_resolve_and_trust_fund(app):
    ids = _completed_booking(app)
    with app.test_request_context():
        b = db.session.get(Booking, ids["booking"])
        renter = db.session.get(User, ids["renter"])
        admin = db.session.get(User, ids["admin"])

        trust_fund_service.set_starting_balance(1_000_000, admin=admin)
        assert trust_fund_service.current_balance() == Decimal("1000000")

        d = disputes_service.open_dispute(b, renter, reason="Item came back scratched badly.")
        assert [x.id for x in disputes_service.open_disputes()] == [d.id]

        # can't open a second one while the first is unresolved
        with pytest.raises(disputes_service.DisputeAlreadyOpen):
            disputes_service.open_dispute(b, renter, reason="Another problem entirely.")

        disputes_service.resolve_dispute(
            d, admin=admin, resolution="Compensated owner from fund.",
            deposit_decision="withheld", amount_from_fund=50000,
        )
        assert trust_fund_service.total_disbursed() == Decimal("50000")
        assert trust_fund_service.current_balance() == Decimal("950000")

        with pytest.raises(disputes_service.DisputeError):
            disputes_service.resolve_dispute(d, admin=admin, resolution="again")


def test_dispute_not_allowed_before_active(app):
    with app.test_request_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _user("O", "o@example.com")
        renter = _user("R", "r@example.com")
        listing = Listing(owner_id=owner.id, title="X", description="d", category_id=cat.id,
                          city="I", area="A", price_per_day=100, deposit_amount=100,
                          status="active")
        db.session.add(listing)
        db.session.commit()
        b = booking_service.request_to_rent(listing, renter, start_date=START, end_date=END)
        with pytest.raises(disputes_service.DisputeNotAllowed):
            disputes_service.open_dispute(b, renter, reason="Too early to dispute this.")


def test_admin_only_pages(client, app):
    with app.app_context():
        _user("U", "u@example.com")
        _user("A", "a@example.com", admin=True)

    for path in ("/admin/disputes", "/admin/trust-fund"):
        assert client.get(path).status_code == 302  # anon -> login

    client.post("/login", data={"email": "u@example.com", "password": "supersecret"})
    for path in ("/admin/disputes", "/admin/trust-fund"):
        assert client.get(path).status_code == 403
    client.post("/logout")

    client.post("/login", data={"email": "a@example.com", "password": "supersecret"})
    for path in ("/admin/disputes", "/admin/trust-fund"):
        assert client.get(path).status_code == 200
