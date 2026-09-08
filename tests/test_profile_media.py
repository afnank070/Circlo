"""Smoke tests — profile enhancements: photo upload, bio, member-since,
completed-rental counts."""
import io

import pytest

from app.extensions import db
from app.models import Booking, Category, Listing, User
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service


@pytest.fixture(autouse=True)
def _stub_storage(monkeypatch):
    """No MinIO in tests — record uploads/deletes, hand back a fake URL."""
    calls = {"uploaded": [], "deleted": []}
    monkeypatch.setattr(
        "app.services.storage.upload_fileobj",
        lambda fileobj, key, **k: calls["uploaded"].append(key) or key,
    )
    monkeypatch.setattr(
        "app.services.storage.delete_object",
        lambda key, **k: calls["deleted"].append(key),
    )
    monkeypatch.setattr(
        "app.services.storage.presigned_url", lambda key, **k: f"https://stub/{key}"
    )
    return calls


def _signup(client, email="sam@example.com"):
    client.post("/signup", data={
        "name": "Sam Rivera", "email": email, "phone": "03001234567",
        "password": "supersecret", "confirm": "supersecret",
    }, follow_redirects=True)
    u = auth_service.get_user_by_email(email)
    u.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return u


def _img(name="me.png", mimetype="image/png", data=b"\x89PNG\r\n\x1a\n" + b"x" * 64):
    return (io.BytesIO(data), name, mimetype)


# --- Profile photo upload --------------------------------------------------
def test_upload_avatar_sets_key_and_stores_file(client, app, _stub_storage):
    _signup(client)
    resp = client.post("/account/avatar", data={"avatar": _img()},
                       content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Profile photo updated" in resp.data

    with app.app_context():
        u = db.session.get(User, 1)
        assert u.avatar_key and u.avatar_key.startswith("avatars/1/")
        assert u.avatar_key.endswith(".png")
    assert _stub_storage["uploaded"] == [db.session.get(User, 1).avatar_key]


def test_profile_page_renders_photo_when_set(client, app, _stub_storage):
    u = _signup(client)
    client.post("/account/avatar", data={"avatar": _img()},
                content_type="multipart/form-data")
    body = client.get(f"/users/{u.id}").data
    assert b'src="https://stub/avatars/1/' in body
    # initials circle no longer the header avatar
    assert body.count(b"bg-accent2-300") <= 1  # (still used in the self-edit card)


def test_profile_page_falls_back_to_initials_when_no_photo(client):
    _signup(client)
    body = client.get("/users/1").data
    assert b"SR" in body  # Sam Rivera initials
    assert b"avatars/1/" not in body


def test_upload_avatar_rejects_non_image(client, _stub_storage):
    _signup(client)
    resp = client.post(
        "/account/avatar",
        data={"avatar": (io.BytesIO(b"not an image"), "notes.txt", "text/plain")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert b"JPEG, PNG, WebP or GIF" in resp.data
    assert _stub_storage["uploaded"] == []


def test_remove_avatar_clears_key_and_deletes_object(client, app, _stub_storage):
    _signup(client)
    client.post("/account/avatar", data={"avatar": _img()},
                content_type="multipart/form-data")
    key = db.session.get(User, 1).avatar_key

    resp = client.post("/account/avatar/remove", follow_redirects=True)
    assert b"Profile photo removed" in resp.data
    with app.app_context():
        assert db.session.get(User, 1).avatar_key is None
    assert key in _stub_storage["deleted"]


def test_replacing_avatar_deletes_the_old_one(client, app, _stub_storage):
    _signup(client)
    client.post("/account/avatar", data={"avatar": _img("first.png")},
                content_type="multipart/form-data")
    first = db.session.get(User, 1).avatar_key
    client.post("/account/avatar", data={"avatar": _img("second.jpg", "image/jpeg")},
                content_type="multipart/form-data")
    second = db.session.get(User, 1).avatar_key

    assert first != second
    assert second.endswith(".jpg")
    assert first in _stub_storage["deleted"]


# --- Bio -----------------------------------------------------------------
def test_bio_saves_and_shows_only_when_set(client, app, _stub_storage):
    u = _signup(client)

    # not set -> no bio paragraph
    assert b"A line or two about you" in client.get(f"/users/{u.id}").data  # placeholder in the form
    body = client.get(f"/users/{u.id}").data
    assert b"max-w-[62ch]" not in body  # the public bio <p> isn't rendered

    client.post("/account", data={
        "name": "Sam Rivera", "email": "sam@example.com", "phone": "03001234567",
        "bio": "  Camera nerd. I lend lenses and tripods around F-7.  ",
    }, follow_redirects=True)

    with app.app_context():
        assert db.session.get(User, 1).bio == "Camera nerd. I lend lenses and tripods around F-7."
    body = client.get(f"/users/{u.id}").data
    assert b"Camera nerd. I lend lenses and tripods around F-7." in body
    assert b"max-w-[62ch]" in body  # public bio <p> now rendered


def test_bio_is_length_capped(client, app, _stub_storage):
    _signup(client)
    client.post("/account", data={
        "name": "Sam Rivera", "email": "sam@example.com", "phone": "03001234567",
        "bio": "x" * 900,
    }, follow_redirects=True)
    with app.app_context():
        assert len(db.session.get(User, 1).bio) == 500


# --- Member since + completed counts -----------------------------------
def test_member_since_month_year_shown(client, app, _stub_storage):
    u = _signup(client)
    body = client.get(f"/users/{u.id}").data.decode()
    stamp = u.created_at.strftime("%B %Y")
    assert f"Member since {stamp}" in body


def test_completed_rental_counts_shown(client, app, _stub_storage):
    with app.app_context():
        cat = Category(name="Tools", slug="tools"); db.session.add(cat); db.session.commit()
        owner = _signup_user("owner@example.com", "Olivia Owner")
        renter = _signup_user("renter@example.com", "Ray Renter")
        listing = Listing(owner_id=owner.id, title="Drill", description="d",
                          category_id=cat.id, city="Islamabad", area="F-7",
                          price_per_hour=500, deposit_amount=1000, status="active")
        db.session.add(listing); db.session.commit()
        # 2 completed as owner, 1 completed as renter, 1 not-completed (ignored)
        for st in ("completed", "completed", "cancelled"):
            db.session.add(_bk(listing, renter, owner, st))
        db.session.add(_bk(listing, owner, renter, "completed"))  # owner is renter here
        db.session.commit()
        oid = owner.id

    body = client.get(f"/users/{oid}").data
    assert b"Reputation &amp; activity" in body
    # owner tile: 2 completed; renter tile: 1 completed
    assert b"<span class=\"font-bold text-ink\">2</span> rentals completed" in body
    assert b"<span class=\"font-bold text-ink\">1</span> rental completed" in body


# helpers for the last test (need their own app context)
def _signup_user(email, name):
    u = auth_service.create_user(name, email, "supersecret", phone="03001234567")
    u.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return u


def _bk(listing, renter, owner, status):
    from datetime import datetime, timedelta
    return Booking(
        listing_id=listing.id, renter_id=renter.id, owner_id=owner.id, status=status,
        start_datetime=datetime.utcnow() - timedelta(days=10),
        duration_hours=3,
        deposit_amount=1000, rental_amount=1500,
    )
