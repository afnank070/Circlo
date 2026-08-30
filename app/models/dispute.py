"""Dispute model — a problem raised on a booking, resolved by an admin.

Blueprint §5, §6 (layer 4 — Trust & Safety Fund). Either party on an ACTIVE /
RETURNED / COMPLETED booking can open one. An admin resolves it: decide the
deposit (release to renter / withhold for owner) and, if CIRCLO compensates a
loss, record the amount drawn from the trust fund. Money movement is *tracked
only* for the MVP — no gateway payout (blueprint §7).
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"

DEPOSIT_PENDING = "pending"
DEPOSIT_RELEASED = "released"   # returned to renter
DEPOSIT_WITHHELD = "withheld"   # given to owner


class Dispute(db.Model):
    __tablename__ = "disputes"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True
    )
    opened_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    reason = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), nullable=False, default=STATUS_OPEN, index=True)

    resolution = db.Column(db.Text, nullable=True)
    deposit_decision = db.Column(db.String(20), nullable=False, default=DEPOSIT_PENDING)
    # PKR compensation paid from the Trust & Safety Fund (tracked, not gateway-paid).
    amount_from_fund = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    booking = db.relationship("Booking", backref="disputes")
    opener = db.relationship("User", foreign_keys=[opened_by])
    resolver = db.relationship("User", foreign_keys=[resolved_by])

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Dispute {self.id} booking={self.booking_id} {self.status}>"
