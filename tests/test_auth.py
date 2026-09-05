"""M1 smoke tests — signup, login, logout (Flask-Login sessions)."""

from app.models import User
from app.services import auth as auth_service


def test_signup_creates_user_and_logs_in(client, app):
    resp = client.post(
        "/signup",
        data={
            "name": "Ayesha Khan",
            "email": "Ayesha@Example.com",
            "phone": "03001234567",
            "password": "supersecret",
            "confirm": "supersecret",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Logged-in chrome shows the account menu ("My Listings") instead of "Sign up".
    assert b"My Listings" in resp.data

    with app.app_context():
        user = auth_service.get_user_by_email("ayesha@example.com")
        assert user is not None
        assert user.name == "Ayesha Khan"
        assert user.email == "ayesha@example.com"  # normalised
        assert user.phone == "03001234567"
        assert user.password_hash and user.password_hash != "supersecret"
        assert user.verification_status == "pending"
        assert user.role == "user"


def test_signup_requires_phone(client, app):
    resp = client.post(
        "/signup",
        data={
            "name": "No Phone",
            "email": "nophone@example.com",
            "password": "supersecret",
            "confirm": "supersecret",
        },
    )
    assert resp.status_code == 200
    assert b"phone number" in resp.data
    with app.app_context():
        assert auth_service.get_user_by_email("nophone@example.com") is None


def test_signup_rejects_mismatched_passwords(client, app):
    resp = client.post(
        "/signup",
        data={
            "name": "Bad Confirm",
            "email": "bad@example.com",
            "phone": "03001234567",
            "password": "supersecret",
            "confirm": "different",
        },
    )
    assert resp.status_code == 200
    assert b"Passwords do not match" in resp.data
    with app.app_context():
        assert auth_service.get_user_by_email("bad@example.com") is None


def test_signup_rejects_duplicate_email(client, app):
    with app.app_context():
        auth_service.create_user("First", "dupe@example.com", "supersecret")

    resp = client.post(
        "/signup",
        data={
            "name": "Second",
            "email": "dupe@example.com",
            "phone": "03001234567",
            "password": "supersecret",
            "confirm": "supersecret",
        },
    )
    assert resp.status_code == 200
    assert b"already registered" in resp.data


def test_login_with_valid_credentials(client, app):
    with app.app_context():
        auth_service.create_user("Log In", "login@example.com", "supersecret")

    resp = client.post(
        "/login",
        data={"email": "login@example.com", "password": "supersecret"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"My Listings" in resp.data


def test_login_rejects_bad_password(client, app):
    with app.app_context():
        auth_service.create_user("Log In", "login2@example.com", "supersecret")

    resp = client.post(
        "/login",
        data={"email": "login2@example.com", "password": "wrong"},
    )
    assert resp.status_code == 200
    assert b"Incorrect email or password" in resp.data


def test_logout_ends_session(client, app):
    with app.app_context():
        auth_service.create_user("Log Out", "logout@example.com", "supersecret")
    client.post("/login", data={"email": "logout@example.com", "password": "supersecret"})

    resp = client.post("/logout", follow_redirects=True)
    assert resp.status_code == 200
    # Back to logged-out chrome.
    assert b"Sign in" in resp.data
