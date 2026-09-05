"""User model — an authenticated CIRCLO member (blueprint §5).

Owners list items and renters book them; both are the same ``User``. Passwords
are never stored in plaintext — only a Werkzeug hash (blueprint §8).

``verification_status`` is present from M1 but NOT yet enforced: the manual
CNIC/selfie review that gates listing/renting needs external tooling and lands in
a later milestone. The field is kept so that flow has a home to slot into — every
new user simply starts ``pending`` and can still list for now.

``rating`` is a denormalised cache of the owner's reputation. Real ratings come
from the Review model (M5); until then it is ``None`` for new users (rendered as
"New") and pre-filled only for seeded demo owners so the marketplace UI keeps its
star ratings.
"""
from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

# Roles and verification states, named here so services/templates don't hard-code
# the literals in multiple places.
ROLE_USER = "user"
ROLE_ADMIN = "admin"

VERIFICATION_PENDING = "pending"
VERIFICATION_APPROVED = "approved"
VERIFICATION_REJECTED = "rejected"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    # Required at signup going forward (see app/web/auth.py); nullable in the DB
    # so accounts created before this field existed (and OAuth signups, which
    # skip the phone step) don't violate a NOT NULL constraint. Used to let a
    # renter/owner reach each other once a booking is accepted (blueprint: no
    # in-app messaging, just a plain data reveal).
    phone = db.Column(db.String(20), nullable=True)
    # Nullable: accounts created via "Sign in with Google" have no password —
    # they authenticate through the OAuth provider. Email/password accounts
    # always have a hash. See ``has_password`` / ``check_password``.
    password_hash = db.Column(db.String(255), nullable=True)

    # user / admin (blueprint §5). Default keeps signups as plain users.
    role = db.Column(db.String(20), nullable=False, default=ROLE_USER)

    # pending / approved / rejected. Kept for the deferred identity-verification
    # flow; not enforced yet (see module docstring).
    verification_status = db.Column(
        db.String(20), nullable=False, default=VERIFICATION_PENDING
    )

    # Cached owner reputation (0.0–5.0). None until Reviews land in M5.
    rating = db.Column(db.Numeric(2, 1), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    listings = db.relationship(
        "Listing",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    # --- Password handling (never store plaintext — blueprint §8) -----------
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """False for OAuth-only accounts (no hash) — they can't password-login."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def has_password(self) -> bool:
        """True for email/password accounts; False for Google-only accounts."""
        return bool(self.password_hash)

    # --- Convenience --------------------------------------------------------
    @property
    def is_verified(self) -> bool:
        """True once an admin has approved this user's identity (future flow)."""
        return self.verification_status == VERIFICATION_APPROVED

    @property
    def review_count(self) -> int:
        """How many reviews other people have left about this user (M5)."""
        return len(self.reviews_received)

    @property
    def initials(self) -> str:
        """Up to two uppercase initials for avatar chips."""
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<User {self.id} {self.email!r}>"
