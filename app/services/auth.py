"""Auth service — user signup / lookup / credential checks.

All account logic lives here (not in routes) so the future ``/api/v1`` can reuse
it verbatim (blueprint §4). Routes are thin adapters: the web routes log the user
into a Flask-Login session; a JWT-issuing API route would call the same functions.

Passwords are hashed by the ``User`` model (Werkzeug); this layer never sees a
plaintext password beyond passing it straight to the model (blueprint §8).
"""
from __future__ import annotations

from app.extensions import db
from app.models import User


class EmailAlreadyRegistered(Exception):
    """Raised by :func:`create_user` when the email is already taken."""


def normalize_email(email: str) -> str:
    """Canonical form used for storage and lookup (trimmed + lower-cased)."""
    return (email or "").strip().lower()


def get_user(user_id) -> User | None:
    """Resolve a primary-key id to a User (used by the Flask-Login loader)."""
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def get_user_by_email(email: str) -> User | None:
    return User.query.filter_by(email=normalize_email(email)).first()


def create_user(name: str, email: str, password: str) -> User:
    """Create and persist a new user.

    :raises EmailAlreadyRegistered: if the (normalised) email already exists.
    """
    email = normalize_email(email)
    if get_user_by_email(email):
        raise EmailAlreadyRegistered(email)

    user = User(name=name.strip(), email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(email: str, password: str) -> User | None:
    """Return the user if the email exists and the password matches, else None."""
    user = get_user_by_email(email)
    if user is None or not user.check_password(password):
        return None
    return user


def get_or_create_oauth_user(email: str, name: str | None) -> User:
    """Resolve a verified OAuth identity (e.g. Google) to a CIRCLO user.

    If an account with this email already exists it is returned as-is (the same
    person may have signed up with email/password earlier — we just log them in).
    Otherwise a new passwordless account is created: ``password_hash`` stays
    ``None`` and ``verification_status`` starts ``pending``, so a Google signup
    still has to pass the same CNIC/selfie identity check as any other user.
    """
    email = normalize_email(email)
    user = get_user_by_email(email)
    if user is not None:
        return user

    display_name = (name or "").strip() or email.split("@")[0]
    user = User(name=display_name, email=email)  # no set_password() -> OAuth-only
    db.session.add(user)
    db.session.commit()
    return user
