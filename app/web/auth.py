"""Auth web routes — signup / login / logout (Flask-Login sessions).

Thin adapters over :mod:`app.services.auth`: they validate form input, call the
service, and manage the session. No account logic lives here so ``/api/v1`` can
reuse the same service to issue JWTs later (blueprint §4).
"""
from __future__ import annotations

from authlib.integrations.base_client import OAuthError
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user

from app.extensions import oauth
from app.services import auth as auth_service
from app.services import password_reset as reset_service

from . import web_bp

_OAUTH_NEXT_KEY = "oauth_next"


def _safe_next(target: str | None) -> str | None:
    """Only honour a ``next`` redirect that stays on this site (no open redirect)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@web_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        errors = []
        if not name:
            errors.append("Please enter your name.")
        if not email or "@" not in email:
            errors.append("Please enter a valid email address.")
        if not phone:
            errors.append("Please enter a phone number — the other party needs it to arrange handover.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if not errors:
            try:
                user = auth_service.create_user(name, email, password, phone=phone)
            except auth_service.EmailAlreadyRegistered:
                errors.append("That email is already registered — try logging in.")
            else:
                login_user(user)
                flash(f"Welcome to CIRCLO, {user.name.split()[0]}!", "success")
                return redirect(url_for("web.index"))

        for msg in errors:
            flash(msg, "error")
        # Re-render with the values the user already typed (except passwords).
        return render_template("auth/signup.html", name=name, email=email, phone=phone)

    return render_template("auth/signup.html", name="", email="", phone="")


@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    next_url = _safe_next(request.args.get("next"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        next_url = _safe_next(request.form.get("next")) or next_url

        user = auth_service.authenticate(email, password)
        if user is None:
            flash("Incorrect email or password.", "error")
            return render_template("auth/login.html", email=email, next=next_url)

        login_user(user)
        flash("Logged in.", "success")
        return redirect(next_url or url_for("web.index"))

    return render_template("auth/login.html", email="", next=next_url)


@web_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("web.index"))


# --- "Sign in with Google" (OAuth2 / OpenID Connect) ----------------------------
# Additional to email/password, not a replacement. The provider is only
# registered when GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are set (see the app
# factory); otherwise these routes flash a friendly message and bounce to login.

def _google_client():
    """The registered Google OAuth client, or None if it isn't configured."""
    return oauth.create_client("google")


def _google_redirect_uri() -> str:
    """Absolute callback URL registered with Google.

    Pinned to ``PUBLIC_BASE_URL`` (the canonical domain, e.g.
    ``https://www.circlo.pk``) so the redirect URI is identical no matter which
    hostname or scheme the request arrived on — otherwise ``url_for(_external)``
    echoes the request's ``Host`` header and www vs non-www drift breaks the
    flow. Falls back to the request-derived URL when the env var is unset (local
    dev / tests).
    """
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    path = url_for("web.google_callback")
    return f"{base}{path}" if base else url_for("web.google_callback", _external=True)


@web_bp.route("/auth/google/login")
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    client = _google_client()
    if client is None:
        flash("Google sign-in isn't available right now.", "error")
        return redirect(url_for("web.login"))

    # Stash a safe post-login redirect target for the callback.
    session[_OAUTH_NEXT_KEY] = _safe_next(request.args.get("next"))
    return client.authorize_redirect(_google_redirect_uri())


@web_bp.route("/auth/google/callback")
def google_callback():
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    client = _google_client()
    if client is None:
        flash("Google sign-in isn't available right now.", "error")
        return redirect(url_for("web.login"))

    try:
        # Do NOT pass redirect_uri here: Authlib persists the value used in the
        # authorize step (see _google_redirect_uri) in the session state and
        # replays it for the token exchange. Passing it again collides with that
        # and raises TypeError -> 500 at the callback.
        token = client.authorize_access_token()
    except OAuthError as exc:
        current_app.logger.warning("google oauth: authorize failed: %s", exc)
        flash("Google sign-in was cancelled or failed. Please try again.", "error")
        return redirect(url_for("web.login"))

    userinfo = (token or {}).get("userinfo") or {}
    email = userinfo.get("email")
    if not email or not userinfo.get("email_verified", True):
        current_app.logger.warning("google oauth: no verified email in userinfo")
        flash("Google didn't return a verified email address.", "error")
        return redirect(url_for("web.login"))

    user = auth_service.get_or_create_oauth_user(email, userinfo.get("name"))
    login_user(user)

    next_url = _safe_next(session.pop(_OAUTH_NEXT_KEY, None))
    flash(f"Signed in with Google. Welcome, {user.name.split()[0]}!", "success")
    return redirect(next_url or url_for("web.index"))


@web_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        # Best-effort; never reveal whether the address is registered.
        current_app.logger.info("forgot-password: reset requested for %r", email)
        try:
            reset_service.request_reset(email)
        except Exception:  # noqa: BLE001 - don't leak errors on this endpoint
            current_app.logger.exception(
                "forgot-password: request_reset raised for %r", email
            )
        flash(
            "If that email is registered, we've sent a reset link. "
            "Check your inbox (and spam).",
            "info",
        )
        return redirect(url_for("web.login"))

    return render_template("auth/forgot_password.html")


@web_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    reset = reset_service.verify(token)
    if reset is None:
        flash("That reset link is invalid or has expired. Request a new one.", "error")
        return redirect(url_for("web.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for msg in errors:
                flash(msg, "error")
            return render_template("auth/reset_password.html", token=token)

        user = reset_service.consume(token, password)
        if user is None:
            flash("That reset link is invalid or has expired. Request a new one.", "error")
            return redirect(url_for("web.forgot_password"))

        flash("Password updated — you can log in now.", "success")
        return redirect(url_for("web.login"))

    return render_template("auth/reset_password.html", token=token)
