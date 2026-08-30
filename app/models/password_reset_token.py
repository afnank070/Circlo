"""PasswordResetToken — a single-use, time-limited password reset token.

Only a SHA-256 *hash* of the token is stored; the raw token lives only in the
emailed link. A token is valid while ``used_at`` is NULL and ``expires_at`` is in
the future (1 hour after creation).
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User")

    def is_valid(self, *, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return self.used_at is None and self.expires_at > now

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<PasswordResetToken user={self.user_id} used={self.used_at is not None}>"
