"""Ledger service — record and confirm the money side of a booking.

Blueprint §7: for the MVP no gateway moves money. This service just *records*
every amount as a :class:`~app.models.ledger_entry.LedgerEntry` and lets an admin
flip entries from ``pending`` to ``confirmed`` once they've eyeballed the real
bank / JazzCash transfer. All logic lives here so ``/api/v1`` can reuse it and a
real ``PaymentProvider`` can later confirm entries automatically.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from app.extensions import db
from app.models import Booking, LedgerEntry, User
from app.models.ledger_entry import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_COMMISSION,
    TYPE_DEPOSIT,
    TYPE_PAYOUT,
    TYPE_REFUND,
    TYPE_RENTAL_PAYMENT,
)

# Blueprint §1: CIRCLO takes 20% of the rental fee (not the deposit).
COMMISSION_RATE = Decimal("0.20")


def _money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def entries_for_booking(booking: Booking) -> list[LedgerEntry]:
    return (
        LedgerEntry.query.filter_by(booking_id=booking.id)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
        .all()
    )


def record(
    booking: Booking, entry_type: str, amount, *, status: str = STATUS_PENDING,
    commit: bool = True,
) -> LedgerEntry:
    """Create a single ledger entry for ``booking``."""
    entry = LedgerEntry(
        booking_id=booking.id,
        type=entry_type,
        amount=_money(amount),
        status=status,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry


def record_payment_received(booking: Booking, *, admin: User) -> list[LedgerEntry]:
    """Rental payment + deposit, both created already ``confirmed``.

    Called when an admin confirms the renter's up-front transfer landed — the
    money is really in CIRCLO's account, so these are not pending.
    """
    from app.services import booking as booking_service

    now = datetime.utcnow()
    made = []
    for entry_type, amount in (
        (TYPE_RENTAL_PAYMENT, booking_service.rental_amount_for(booking)),
        (TYPE_DEPOSIT, booking.deposit_amount),
    ):
        entry = record(booking, entry_type, amount, status=STATUS_CONFIRMED, commit=False)
        entry.confirmed_by = admin.id
        entry.confirmed_at = now
        made.append(entry)
    db.session.commit()
    return made


def record_completion_entries(booking: Booking) -> list[LedgerEntry]:
    """Commission + owner payout + renter deposit refund, all ``pending``.

    Called from ``booking.confirm_return`` (same transaction — no commit here).
    An admin confirms the actual payout/refund later via ``/admin/payments``.
    """
    from app.services import booking as booking_service

    rental = _money(booking_service.rental_amount_for(booking))
    commission = _money(rental * COMMISSION_RATE)
    payout = _money(rental - commission)
    refund = _money(booking.deposit_amount)

    return [
        record(booking, TYPE_COMMISSION, commission, commit=False),
        record(booking, TYPE_PAYOUT, payout, commit=False),
        record(booking, TYPE_REFUND, refund, commit=False),
    ]


def confirm_entry(entry: LedgerEntry, *, admin: User) -> LedgerEntry:
    if entry.status != STATUS_CONFIRMED:
        entry.status = STATUS_CONFIRMED
        entry.confirmed_by = admin.id
        entry.confirmed_at = datetime.utcnow()
        db.session.commit()
    return entry


def confirm_all_for_booking(booking: Booking, *, admin: User) -> list[LedgerEntry]:
    """Confirm every still-pending entry on a booking (the manual payout step)."""
    pending = [e for e in entries_for_booking(booking) if e.status == STATUS_PENDING]
    now = datetime.utcnow()
    for entry in pending:
        entry.status = STATUS_CONFIRMED
        entry.confirmed_by = admin.id
        entry.confirmed_at = now
    if pending:
        db.session.commit()
    return pending


def has_pending_entries(booking: Booking) -> bool:
    return any(e.status == STATUS_PENDING for e in entries_for_booking(booking))
