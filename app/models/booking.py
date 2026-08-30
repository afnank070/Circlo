"""Booking model — a rental request/agreement between a renter and an owner.

Blueprint §5: the heart of the system. M3 implements only the front half of the
lifecycle (request → accept/reject/cancel); PAID/HANDED_OVER/ACTIVE/RETURNED/
COMPLETED/DISPUTED land with money (M4) and evidence (M4) and disputes (M5).

``owner_id`` is denormalised from ``listing.owner_id`` at request time purely for
fast "requests for my items" queries — the listing relationship remains the
source of truth. ``deposit_amount`` is copied from the listing at request time so
a later change to the listing's deposit never rewrites an existing booking.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

STATUS_REQUESTED = "requested"
STATUS_ACCEPTED = "accepted"
STATUS_CANCELLED = "cancelled"

# M4 — money & evidence lifecycle (blueprint §5).
STATUS_AWAITING_PAYMENT = "awaiting_payment"  # renter says paid; admin to confirm
STATUS_PAID = "paid"                          # CIRCLO holds rental + deposit
STATUS_HANDED_OVER = "handed_over"            # both "before" photos in (transient)
STATUS_ACTIVE = "active"                      # rental in progress
STATUS_RETURNED = "returned"                  # both "after" photos in
STATUS_COMPLETED = "completed"                # owner confirmed; payouts queued

# Statuses where the item is committed and its dates block a new acceptance.
BLOCKING_STATUSES = (
    STATUS_ACCEPTED,
    STATUS_AWAITING_PAYMENT,
    STATUS_PAID,
    STATUS_HANDED_OVER,
    STATUS_ACTIVE,
    STATUS_RETURNED,
)

# Terminal states.
CLOSED_STATUSES = (STATUS_CANCELLED, STATUS_COMPLETED)


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)

    listing_id = db.Column(
        db.Integer, db.ForeignKey("listings.id"), nullable=False, index=True
    )
    renter_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # Denormalised for the owner's "requests for my items" query.
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )

    status = db.Column(
        db.String(20), nullable=False, default=STATUS_REQUESTED, index=True
    )

    rental_date_start = db.Column(db.Date, nullable=False)
    rental_date_end = db.Column(db.Date, nullable=False)

    # Snapshot of listing.deposit_amount at request time (blueprint §5).
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Snapshot of the total rental fee (price_per_day * days) at request time, so
    # a later listing price change never rewrites an existing booking and the
    # ledger/commission maths (M4) has a fixed number to work from. Nullable for
    # rows created before M4; the booking service backfills it on read.
    rental_amount = db.Column(db.Numeric(10, 2), nullable=True)

    message_from_renter = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    listing = db.relationship("Listing", backref="bookings")
    renter = db.relationship(
        "User", foreign_keys=[renter_id], backref="rental_requests"
    )
    owner = db.relationship(
        "User", foreign_keys=[owner_id], backref="incoming_rental_requests"
    )

    @property
    def rental_days(self) -> int:
        """Inclusive number of rental days (start and end day both count)."""
        return (self.rental_date_end - self.rental_date_start).days + 1

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Booking {self.id} listing={self.listing_id} {self.status}>"
