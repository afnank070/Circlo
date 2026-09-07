"""Auth service — user signup / lookup / credential checks.

All account logic lives here (not in routes) so the future ``/api/v1`` can reuse
it verbatim (blueprint §4). Routes are thin adapters: the web routes log the user
into a Flask-Login session; a JWT-issuing API route would call the same functions.

Passwords are hashed by the ``User`` model (Werkzeug); this layer never sees a
plaintext password beyond passing it straight to the model (blueprint §8).
"""
from __future__ import annotations

import uuid

from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import User
from app.services import storage

# Profile-photo upload guardrails (mirrors the listing-image rules).
AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_AVATAR_EXT = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB
BIO_MAX_LEN = 500


class EmailAlreadyRegistered(Exception):
    """Raised by :func:`create_user` when the email is already taken."""


class InvalidAvatar(Exception):
    """Raised when an uploaded profile photo isn't a usable image."""


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


def create_user(name: str, email: str, password: str, phone: str | None = None) -> User:
    """Create and persist a new user.

    :raises EmailAlreadyRegistered: if the (normalised) email already exists.
    """
    email = normalize_email(email)
    if get_user_by_email(email):
        raise EmailAlreadyRegistered(email)

    user = User(name=name.strip(), email=email, phone=(phone or "").strip() or None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def set_phone(user: User, phone: str) -> User:
    """Set/update a user's phone number (profile self-edit)."""
    user.phone = (phone or "").strip() or None
    db.session.commit()
    return user


class IncorrectPassword(Exception):
    """Raised by :func:`change_password` when the current password doesn't match."""


def update_account(
    user: User, *, name: str, email: str, phone: str | None, bio: str | None = None
) -> User:
    """Update a user's own editable identity fields (profile self-edit).

    :raises EmailAlreadyRegistered: if ``email`` belongs to a different account.
    """
    email = normalize_email(email)
    existing = get_user_by_email(email)
    if existing is not None and existing.id != user.id:
        raise EmailAlreadyRegistered(email)

    user.name = name.strip()
    user.email = email
    user.phone = (phone or "").strip() or None
    user.bio = (bio or "").strip()[:BIO_MAX_LEN] or None
    db.session.commit()
    return user


def set_avatar(user: User, file: FileStorage | None) -> User:
    """Store an uploaded profile photo in the public bucket and point the user at it.

    Deletes the previous avatar object (best-effort) so old photos don't pile up.

    :raises InvalidAvatar: no file, or not an accepted image type.
    """
    if not isinstance(file, FileStorage) or not file.filename:
        raise InvalidAvatar("Choose an image file to upload.")
    content_type = (file.mimetype or "").lower()
    if content_type not in AVATAR_TYPES:
        raise InvalidAvatar("Use a JPEG, PNG, WebP or GIF image.")

    try:
        file.stream.seek(0, 2)
        size = file.stream.tell()
        file.stream.seek(0)
    except (OSError, ValueError):
        size = 0
    if size > MAX_AVATAR_BYTES:
        raise InvalidAvatar("That image is too large — keep it under 5 MB.")

    ext = _AVATAR_EXT[content_type]
    key = f"avatars/{user.id}/{uuid.uuid4().hex}.{ext}"
    storage.upload_fileobj(file.stream, key, content_type=content_type)

    old_key = user.avatar_key
    user.avatar_key = key
    db.session.commit()

    if old_key and old_key != key:
        try:
            storage.delete_object(old_key)
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass
    return user


def remove_avatar(user: User) -> User:
    """Clear the user's profile photo, falling back to the initials circle."""
    old_key = user.avatar_key
    user.avatar_key = None
    db.session.commit()
    if old_key:
        try:
            storage.delete_object(old_key)
        except Exception:  # noqa: BLE001
            pass
    return user


def change_password(user: User, current_password: str, new_password: str) -> User:
    """Change the password of an email/password account.

    :raises IncorrectPassword: if ``current_password`` is wrong (or the account
        is OAuth-only and has no password to verify against).
    """
    if not user.check_password(current_password):
        raise IncorrectPassword()
    user.set_password(new_password)
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
