"""IdentityDocument model — a CNIC + selfie submission for manual review (blueprint §5, §8).

CNIC and selfie images are highly sensitive PII: only the object **key** is
stored, and uploads go to the *private* MinIO bucket (never the public listing
bucket), accessed only via short-lived presigned URLs (blueprint §8).

A user may resubmit after rejection — each submission is a new row, so the
review history is preserved. ``User.verification_status`` is the fast/denormalised
field routes check for gating; this table is the underlying evidence + audit trail.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class IdentityDocument(db.Model):
    __tablename__ = "identity_documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # Object keys in the private bucket — never full URLs (blueprint §8, §9).
    cnic_image_key = db.Column(db.String(255), nullable=False)
    selfie_image_key = db.Column(db.String(255), nullable=False)

    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)

    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)

    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref="identity_documents")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<IdentityDocument {self.id} user={self.user_id} {self.status}>"
