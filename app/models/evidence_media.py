"""EvidenceMedia model — before/after handover photos for a booking.

Blueprint §5, §6 (layer 3), §8: both parties upload photos *before* the item
changes hands and *after* it comes back. Stored in the **private** bucket (only
the object key is persisted), timestamped, and never overwritten or deleted by
users so it holds up in a dispute.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

PHASE_BEFORE = "before"
PHASE_AFTER = "after"
PHASES = (PHASE_BEFORE, PHASE_AFTER)

MEDIA_PHOTO = "photo"
MEDIA_VIDEO = "video"


class EvidenceMedia(db.Model):
    __tablename__ = "evidence_media"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True
    )

    # "before" (handover) or "after" (return).
    phase = db.Column(db.String(10), nullable=False, index=True)

    uploaded_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )

    # Private-bucket object key only, never a URL (blueprint §9).
    object_key = db.Column(db.String(255), nullable=False)

    media_type = db.Column(db.String(10), nullable=False, default=MEDIA_PHOTO)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    booking = db.relationship("Booking", backref="evidence_media")
    uploader = db.relationship("User", foreign_keys=[uploaded_by])

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<EvidenceMedia {self.id} booking={self.booking_id} "
            f"{self.phase} by={self.uploaded_by}>"
        )
