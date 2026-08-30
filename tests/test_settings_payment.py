"""M4 — admin-configurable payment details shown on the payment card."""
from datetime import date, timedelta

from app.extensions import db
from app.models import Category, Listing
from app.models.user import ROLE_ADMIN, VERIFICATION_APPROVED
from app.services import auth as auth_service
from app.services import booking as booking_service
from app.services import settings as settings_service

TODAY = date.today()
START = TODAY + timedelta(days=3)
END = TODAY + timedelta(days=5)  # 3 rental days


def _verified(email, *, admin=False):
    u = auth_service.create_user(email.split("@")[0], email, "supersecret")
    u.verification_status = VERIFICATION_APPROVED
    if admin:
        u.role = ROLE_ADMIN
    db.session.commit()
    return u


def test_settings_get_falls_back_to_config(app):
    with app.app_context():
        app.config["PAYMENT_EASYPAISA_NUMBER"] = "0300-1234567"
        assert settings_service.get("payment_easypaisa_number") == "0300-1234567"
        # DB value overrides the config fallback
        admin = _verified("a@example.com", admin=True)
        settings_service.set_value("payment_easypaisa_number", "0321-9999999", admin=admin)
        assert settings_service.get("payment_easypaisa_number") == "0321-9999999"


def test_non_admin_cannot_open_or_post_settings(client, app):
    with app.app_context():
        _verified("user@example.com")
    client.post("/login", data={"email": "user@example.com", "password": "supersecret"})
    assert client.get("/admin/settings").status_code == 403
    assert client.post("/admin/settings", data={"payment_bank_iban": "PK.."}).status_code == 403


def test_admin_saves_details_and_renter_sees_amount_and_instructions(client, app):
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _verified("owner@example.com")
        _verified("admin@example.com", admin=True)
        renter = _verified("renter@example.com")
        listing = Listing(
            owner_id=owner.id, title="Bosch Hammer Drill", description="d",
            category_id=cat.id, city="Islamabad", area="F-8",
            price_per_day=800, deposit_amount=5000, status="active",
        )
        db.session.add(listing)
        db.session.commit()
        b = booking_service.request_to_rent(listing, renter, start_date=START, end_date=END)
        booking_service.accept(b, owner=owner)

    # admin configures the collection details
    client.post("/login", data={"email": "admin@example.com", "password": "supersecret"})
    resp = client.post("/admin/settings", data={
        "payment_easypaisa_number": "0300-1112222",
        "payment_easypaisa_name": "CIRCLO Pvt Ltd",
        "payment_bank_name": "Meezan Bank",
        "payment_bank_account": "01234567890",
        "payment_bank_iban": "PK00MEZN0001234567890",
        "payment_instructions_note": "Use your booking number as the reference.",
    }, follow_redirects=True)
    assert resp.status_code == 200
    client.post("/logout")

    client.post("/login", data={"email": "renter@example.com", "password": "supersecret"})
    resp = client.get("/my-rentals")
    assert resp.status_code == 200
    body = resp.data
    assert b"Amount due" in body
    assert b"Rs 7,400" in body           # 2400 rental + 5000 deposit
    assert b"0300-1112222" in body       # EasyPaisa number from settings
    assert b"PK00MEZN0001234567890" in body
    assert b"Use your booking number as the reference." in body


def test_renter_sees_fallback_message_when_details_unset(client, app):
    with app.app_context():
        cat = Category(name="Tools", slug="tools")
        db.session.add(cat)
        db.session.commit()
        owner = _verified("owner@example.com")
        renter = _verified("renter@example.com")
        listing = Listing(
            owner_id=owner.id, title="Drill", description="d", category_id=cat.id,
            city="Islamabad", area="F-8", price_per_day=800, deposit_amount=5000,
            status="active",
        )
        db.session.add(listing)
        db.session.commit()
        b = booking_service.request_to_rent(listing, renter, start_date=START, end_date=END)
        booking_service.accept(b, owner=owner)

    client.post("/login", data={"email": "renter@example.com", "password": "supersecret"})
    resp = client.get("/my-rentals")
    assert b"Amount due" in resp.data
    assert b"aren&#39;t set up yet" in resp.data or b"aren't set up yet" in resp.data
