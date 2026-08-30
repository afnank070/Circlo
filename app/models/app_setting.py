"""AppSetting — a small key/value store for admin-configurable settings.

Blueprint §9 keeps *environment*-specific values (DSNs, endpoints, secrets) in
env vars. This table is for *operational* values an admin edits from the panel
without a redeploy — e.g. where renters send the rental + deposit (CIRCLO's
EasyPaisa number / bank account), which changes once the company account is
ready. Values are short strings; anything sensitive enough to be a secret still
belongs in env.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<AppSetting {self.key!r}>"
