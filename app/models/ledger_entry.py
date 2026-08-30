"""LedgerEntry model — every rupee that moves for a booking is tracked here.

Blueprint §7: for the MVP the *movement* of money is semi-manual (a renter pays
into CIRCLO's account; an admin confirms receipt; payouts/refunds are triggered
by hand), but every amount is *recorded* in the DB from day one. A gateway can
be dropped in later without touching this model — it would just flip entries to
``confirmed`` automatically instead of an admin doing it.

One booking has many entries:

* ``rental_payment`` + ``deposit``  — created (confirmed) when an admin confirms
  the renter's up-front transfer.
* ``commission`` / ``payout`` / ``refund`` — created (pending) when the owner
  confirms a clean return, then confirmed when the admin actually pays out.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

TYPE_RENTAL_PAYMENT = "rental_payment"
TYPE_DEPOSIT = "deposit"
TYPE_COMMISSION = "commission"
TYPE_PAYOUT = "payout"
TYPE_REFUND = "refund"

ENTRY_TYPES = (
    TYPE_RENTAL_PAYMENT,
    TYPE_DEPOSIT,
    TYPE_COMMISSION,
    TYPE_PAYOUT,
    TYPE_REFUND,
)

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"


class LedgerEntry(db.Model):
    __tablename__ = "ledger_entries"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True
    )

    # One of ENTRY_TYPES (named constants above so nothing hard-codes literals).
    type = db.Column(db.String(20), nullable=False, index=True)

    # PKR, fixed-point. Money never actually moves in code — this is the record.
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    # pending -> confirmed (an admin has verified the real-world transfer).
    status = db.Column(
        db.String(20), nullable=False, default=STATUS_PENDING, index=True
    )

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    confirmed_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    confirmed_at = db.Column(db.DateTime, nullable=True)

    booking = db.relationship("Booking", backref="ledger_entries")
    confirmer = db.relationship("User", foreign_keys=[confirmed_by])

    @property
    def is_confirmed(self) -> bool:
        return self.status == STATUS_CONFIRMED

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<LedgerEntry {self.id} booking={self.booking_id} "
            f"{self.type} {self.amount} {self.status}>"
        )
