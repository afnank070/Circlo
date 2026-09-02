"""Password-reset service — issue, verify and consume single-use reset tokens.

Flow (blueprint §8 — auth hardening):
  1. ``request_reset(email)`` — always returns quietly (no account enumeration);
     if the email exists, a token is created and a reset link emailed.
  2. ``verify(raw_token)`` — returns the token row if valid (unused, unexpired).
  3. ``consume(raw_token, new_password)`` — sets the new password and marks the
     token used. Any other outstanding tokens for that user are invalidated too.

Only a SHA-256 hash of the token is stored.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from flask import current_app, url_for

from app.extensions import db
from app.models import PasswordResetToken, User
from app.services import auth as auth_service
from app.services import email as email_service

TOKEN_TTL = timedelta(hours=1)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_reset_url(raw_token: str) -> str:
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    try:
        path = url_for("web.reset_password", token=raw_token)
    except Exception:  # noqa: BLE001 - fall back to a hand-built path outside a request
        path = f"/reset-password/{raw_token}"
    return f"{base}{path}" if base else path


def request_reset(email: str) -> bool:
    """Create + email a reset token for ``email`` if it maps to a user.

    Returns True if an email was actually sent (useful for tests); the web route
    ignores the result and shows the same message either way.
    """
    user = auth_service.get_user_by_email(email)
    if user is None:
        current_app.logger.info(
            "password reset requested for unknown email %r — no token issued", email
        )
        return False

    raw = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash(raw),
        expires_at=datetime.utcnow() + TOKEN_TTL,
    )
    db.session.add(token)
    db.session.commit()

    reset_url = _build_reset_url(raw)
    current_app.logger.info(
        "password reset token issued for user id=%s (%s) — sending reset email",
        user.id, user.email,
    )
    body = (
        f"<p>Hi {user.name.split()[0] if user.name else 'there'},</p>"
        f"<p>We received a request to reset your CIRCLO password. "
        f"Click the link below within the next hour to choose a new one:</p>"
        f'<p><a href="{reset_url}">{reset_url}</a></p>'
        f"<p>If you didn't ask for this, you can ignore this email — your "
        f"password won't change.</p>"
    )
    sent = email_service.send_email(user.email, "Reset your CIRCLO password", body)
    if not sent:
        current_app.logger.error(
            "password reset email NOT sent for user id=%s (%s) — see send_email log above",
            user.id, user.email,
        )
    return sent


def verify(raw_token: str) -> PasswordResetToken | None:
    if not raw_token:
        return None
    token = PasswordResetToken.query.filter_by(token_hash=_hash(raw_token)).first()
    if token is None or not token.is_valid():
        return None
    return token


def consume(raw_token: str, new_password: str) -> User | None:
    """Set the user's new password and burn the token. Returns the user or None."""
    token = verify(raw_token)
    if token is None:
        return None

    user = token.user
    user.set_password(new_password)
    token.used_at = datetime.utcnow()

    # Invalidate any other outstanding tokens for this user.
    others = PasswordResetToken.query.filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.id != token.id,
    ).all()
    for other in others:
        other.used_at = datetime.utcnow()

    db.session.commit()
    return user
