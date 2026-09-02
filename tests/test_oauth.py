"""Smoke tests for "Sign in with Google" (OAuth2 / OIDC).

Google is an *additional* sign-in option — the email/password flow
(``tests/test_auth.py``) must keep working unchanged. The real Google round-trip
can't run in tests, so ``app.web.auth._google_client`` is monkeypatched with a
stub that returns a canned ``userinfo`` payload (what Authlib hands back after
``authorize_access_token()``).
"""
from app.models import User
from app.services import auth as auth_service


class _FakeGoogleClient:
    """Stands in for Authlib's registered Google client in the callback."""

    def __init__(self, userinfo: dict):
        self._userinfo = userinfo

    def authorize_access_token(self) -> dict:
        return {"userinfo": self._userinfo}


def _enable_google(app) -> None:
    """Flip the config flags the templates/context-processor check."""
    app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"


def _patch_google(monkeypatch, userinfo: dict) -> None:
    monkeypatch.setattr(
        "app.web.auth._google_client", lambda: _FakeGoogleClient(userinfo)
    )


def test_google_button_hidden_when_not_configured(client):
    assert b"Sign in with Google" not in client.get("/login").data
    assert b"Sign up with Google" not in client.get("/signup").data


def test_google_button_shown_when_configured(client, app):
    _enable_google(app)
    assert b"Sign in with Google" in client.get("/login").data
    assert b"Sign up with Google" in client.get("/signup").data


def test_google_login_redirects_to_provider(client, app, monkeypatch):
    _enable_google(app)
    captured = {}

    class _Redirector:
        def authorize_redirect(self, redirect_uri):
            from flask import redirect

            captured["redirect_uri"] = redirect_uri
            return redirect("https://accounts.google.com/o/oauth2/v2/auth?stub=1")

    monkeypatch.setattr("app.web.auth._google_client", lambda: _Redirector())

    resp = client.get("/auth/google/login")
    assert resp.status_code == 302
    assert "accounts.google.com" in resp.headers["Location"]
    assert captured["redirect_uri"].endswith("/auth/google/callback")


def test_google_login_when_unconfigured_bounces_to_login(client, monkeypatch):
    monkeypatch.setattr("app.web.auth._google_client", lambda: None)
    resp = client.get("/auth/google/login", follow_redirects=True)
    assert b"isn&#39;t available" in resp.data or b"isn't available" in resp.data


def test_google_callback_creates_unverified_passwordless_user(client, app, monkeypatch):
    _patch_google(
        monkeypatch,
        {"email": "New.User@Gmail.com", "name": "New User", "email_verified": True},
    )

    resp = client.get("/auth/google/callback", follow_redirects=True)
    assert resp.status_code == 200
    assert b"My Listings" in resp.data  # logged in (account menu chrome)

    with app.app_context():
        user = auth_service.get_user_by_email("new.user@gmail.com")
        assert user is not None
        assert user.name == "New User"
        assert user.email == "new.user@gmail.com"  # normalised
        assert user.password_hash is None
        assert user.has_password is False
        assert user.check_password("anything") is False
        assert user.verification_status == "pending"  # still needs CNIC/selfie
        assert user.role == "user"


def test_google_callback_logs_into_existing_email_account(client, app, monkeypatch):
    with app.app_context():
        auth_service.create_user("Existing Person", "person@example.com", "supersecret")

    _patch_google(
        monkeypatch,
        {"email": "person@example.com", "name": "Totally Different", "email_verified": True},
    )
    resp = client.get("/auth/google/callback", follow_redirects=True)
    assert resp.status_code == 200
    assert b"My Listings" in resp.data

    with app.app_context():
        rows = User.query.filter_by(email="person@example.com").all()
        assert len(rows) == 1  # no duplicate account
        assert rows[0].name == "Existing Person"  # not overwritten
        assert rows[0].check_password("supersecret")  # password intact


def test_oauth_user_cannot_use_password_login(client, app, monkeypatch):
    _patch_google(
        monkeypatch, {"email": "g@gmail.com", "name": "G", "email_verified": True}
    )
    client.get("/auth/google/callback")
    client.post("/logout")

    resp = client.post(
        "/login", data={"email": "g@gmail.com", "password": "guessing"}
    )
    assert b"Incorrect email or password" in resp.data


def test_email_password_signup_still_works(client, app):
    resp = client.post(
        "/signup",
        data={
            "name": "Normal Signup",
            "email": "normal@example.com",
            "password": "supersecret",
            "confirm": "supersecret",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = auth_service.get_user_by_email("normal@example.com")
        assert user is not None and user.has_password


def test_google_callback_rejects_missing_email(client, monkeypatch):
    _patch_google(monkeypatch, {"name": "No Email Provided"})
    resp = client.get("/auth/google/callback", follow_redirects=True)
    assert b"verified email" in resp.data
