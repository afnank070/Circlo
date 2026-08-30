"""Review model — a mutual rating left after a booking completes (blueprint §5, §6).

Each COMPLETED booking allows exactly two reviews: renter → owner and owner →
renter. ``direction`` records which, and the unique constraint on
``(booking_id, author_id)`` enforces one review per person per booking.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

DIRECTION_RENTER_ON_OWNER = "renter_on_owner"
DIRECTION_OWNER_ON_RENTER = "owner_on_renter"


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True
    )
    author_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    subject_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    direction = db.Column(db.String(20), nullable=False)

    rating = db.Column(db.Integer, nullable=False)  # 1..5
    comment = db.Column(db.Text, nullable=False, default="")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    booking = db.relationship("Booking", backref="reviews")
    author = db.relationship("User", foreign_keys=[author_id])
    subject = db.relationship("User", foreign_keys=[subject_id], backref="reviews_received")

    __table_args__ = (
        db.UniqueConstraint("booking_id", "author_id", name="uq_review_booking_author"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Review booking={self.booking_id} {self.direction} {self.rating}★>"
