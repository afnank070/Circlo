"""Smoke tests — account dropdown "Profile" link + the profile/account page.

Covers the newly-added dropdown entry and that the profile page, viewed by its
owner, exposes the editable account fields, verification state, a rating
breakdown, and the change-password option (hidden for OAuth-only accounts).
"""
from app.extensions import db
from app.models import User
from app.models.user import VERIFICATION_APPROVED, VERIFICATION_REJECTED
from app.services import auth as auth_service


def _signup(client, email="sam@example.com", phone="03001234567"):
    client.post(
        "/signup",
        data={"name": email.split("@")[0], "email": email, "phone": phone,
              "password": "supersecret", "confirm": "supersecret"},
        follow_redirects=True,
    )
    return auth_service.get_user_by_email(email)


def test_dropdown_has_profile_link(client, app):
    user = _signup(client)
    resp = client.get("/")
    assert resp.status_code == 200
    assert f'href="/users/{user.id}"'.encode() in resp.data
    assert b">Profile</a>" in resp.data


def test_profile_link_points_to_own_profile(client, app):
    user = _signup(client)
    resp = client.get("/", follow_redirects=True)
    # The dropdown entry resolves to this user's public profile URL.
    assert f'"/users/{user.id}"'.encode() in resp.data


def test_own_profile_shows_editable_account_fields(client, app):
    _signup(client)
    resp = client.get("/users/1")
    assert resp.status_code == 200
    assert b'action="/account"' in resp.data
    assert b'name="name"' in resp.data
    assert b'name="email"' in resp.data
    assert b'name="phone"' in resp.data


def test_unverified_profile_shows_verify_prompt(client, app):
    _signup(client)
    resp = client.get("/users/1")
    assert b'href="/verify"' in resp.data
    assert b"Verified</span>" not in resp.data


def test_verified_profile_shows_badge_not_prompt(client, app):
    _signup(client)
    # Write on the fixture's already-active session (see test_archive_listing).
    db.session.get(User, 1).verification_status = VERIFICATION_APPROVED
    db.session.commit()
    resp = client.get("/users/1")
    assert b"Verified" in resp.data
    assert b'href="/verify"' not in resp.data


def test_rejected_profile_still_prompts_verification(client, app):
    _signup(client)
    db.session.get(User, 1).verification_status = VERIFICATION_REJECTED
    db.session.commit()
    resp = client.get("/users/1")
    assert b'href="/verify"' in resp.data


def test_profile_shows_rating_breakdown(client, app):
    _signup(client)
    resp = client.get("/users/1")
    assert b"As an owner" in resp.data
    assert b"As a renter" in resp.data


def test_update_account_changes_name_email_phone(client, app):
    _signup(client)
    resp = client.post(
        "/account",
        data={"name": "Sam New", "email": "sam.new@example.com", "phone": "03009999999"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, 1)
        assert user.name == "Sam New"
        assert user.email == "sam.new@example.com"
        assert user.phone == "03009999999"


def test_update_account_rejects_duplicate_email(client, app):
    _signup(client, email="a@example.com")
    client.post("/logout")
    _signup(client, email="b@example.com")
    resp = client.post(
        "/account",
        data={"name": "B", "email": "a@example.com", "phone": "03001234567"},
        follow_redirects=True,
    )
    assert b"already registered" in resp.data
    with app.app_context():
        assert db.session.get(User, 2).email == "b@example.com"


def test_change_password_page_available_for_password_accounts(client, app):
    _signup(client)
    resp = client.get("/account/password")
    assert resp.status_code == 200
    assert b'name="current_password"' in resp.data


def test_change_password_updates_hash(client, app):
    _signup(client)
    resp = client.post(
        "/account/password",
        data={"current_password": "supersecret", "new_password": "brandnewpass",
              "confirm": "brandnewpass"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(User, 1).check_password("brandnewpass")


def test_change_password_rejects_wrong_current(client, app):
    _signup(client)
    resp = client.post(
        "/account/password",
        data={"current_password": "wrongpass", "new_password": "brandnewpass",
              "confirm": "brandnewpass"},
        follow_redirects=True,
    )
    assert b"current password is incorrect" in resp.data
    with app.app_context():
        assert db.session.get(User, 1).check_password("supersecret")


def test_change_password_hidden_and_404_for_oauth_only(client, app):
    user = auth_service.get_or_create_oauth_user("oauth@example.com", "OAuth User")
    uid = user.id
    # Log the OAuth user in via the test login mechanism: set the session.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
    resp = client.get(f"/users/{uid}")
    assert resp.status_code == 200
    assert b'href="/account/password"' not in resp.data
    assert client.get("/account/password").status_code == 404
