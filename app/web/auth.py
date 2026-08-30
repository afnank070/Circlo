"""Auth web routes — signup / login / logout (Flask-Login sessions).

Thin adapters over :mod:`app.services.auth`: they validate form input, call the
service, and manage the session. No account logic lives here so ``/api/v1`` can
reuse the same service to issue JWTs later (blueprint §4).
"""
from __future__ import annotations

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_user, logout_user

from app.services import auth as auth_service
from app.services import password_reset as reset_service

from . import web_bp


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
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        errors = []
        if not name:
            errors.append("Please enter your name.")
        if not email or "@" not in email:
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if not errors:
            try:
                user = auth_service.create_user(name, email, password)
            except auth_service.EmailAlreadyRegistered:
                errors.append("That email is already registered — try logging in.")
            else:
                login_user(user)
                flash(f"Welcome to CIRCLO, {user.name.split()[0]}!", "success")
                return redirect(url_for("web.index"))

        for msg in errors:
            flash(msg, "error")
        # Re-render with the values the user already typed (except passwords).
        return render_template("auth/signup.html", name=name, email=email)

    return render_template("auth/signup.html", name="", email="")


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


@web_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("web.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        # Best-effort; never reveal whether the address is registered.
        try:
            reset_service.request_reset(email)
        except Exception:  # noqa: BLE001 - don't leak errors on this endpoint
            pass
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
