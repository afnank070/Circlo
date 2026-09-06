"""CancellationRequest model — a request to cancel a booking after money moved.

Blueprint §5, §7. Cancellation rules depend on the booking's stage:

* REQUESTED / ACCEPTED  — either party cancels instantly, no money involved.
  No row here: the booking just goes straight to CANCELLED.
* AWAITING_PAYMENT / PAID — money has moved, so an admin must confirm the
  refund by hand (same manual pattern as the M4 payout step). Either party
  raises a ``CancellationRequest`` (``pending``); an admin then confirms the
  refund was sent and the booking moves to CANCELLED (``confirmed``), or
  declines it (``rejected``) and the booking carries on.
* HANDED_OVER or later — the item is already exchanged; cancellation is gone,
  users are pointed at the dispute flow instead. No row here either.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"


class CancellationRequest(db.Model):
    __tablename__ = "cancellation_requests"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True
    )
    requested_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    reason = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(20), nullable=False, default=STATUS_PENDING, index=True
    )

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    booking = db.relationship("Booking", backref="cancellation_requests")
    requester = db.relationship("User", foreign_keys=[requested_by])
    resolver = db.relationship("User", foreign_keys=[resolved_by])

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<CancellationRequest {self.id} booking={self.booking_id} "
            f"{self.status}>"
        )
