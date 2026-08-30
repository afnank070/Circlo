"""Payments service — the semi-manual money movement around a booking.

Blueprint §7: no gateway for the MVP. The renter transfers rental + deposit into
CIRCLO's account off-platform; an admin confirms receipt here, which creates the
ledger entries and moves the booking to PAID. On completion an admin confirms the
payout/refund the same way. Booking state transitions live in
``services.booking``; ledger writes live in ``services.ledger``; this module just
sequences them so a route (or ``/api/v1``) calls one function.
"""
from __future__ import annotations

from app.extensions import db
from app.models import Booking, User
from app.models.booking import (
    STATUS_ACCEPTED,
    STATUS_AWAITING_PAYMENT,
    STATUS_COMPLETED,
    STATUS_PAID,
)
from app.services import booking as booking_service
from app.services import ledger as ledger_service


class PaymentError(Exception):
    """Base class for payment-flow errors."""


class InvalidPaymentTransition(PaymentError):
    """Raised when the booking isn't in a state the action expects."""


class PaymentPermissionError(PaymentError):
    """Raised when a user acts on a booking they have no standing over."""


def mark_awaiting_payment(booking: Booking, *, renter: User) -> Booking:
    """Renter tells CIRCLO they've sent the rental + deposit: ACCEPTED -> AWAITING_PAYMENT."""
    if booking.renter_id != renter.id:
        raise PaymentPermissionError("You're not the renter on this booking.")
    if booking.status != STATUS_ACCEPTED:
        raise InvalidPaymentTransition("This booking isn't awaiting your payment.")
    booking.status = STATUS_AWAITING_PAYMENT
    db.session.commit()
    return booking


def bookings_awaiting_payment_confirmation() -> list[Booking]:
    """Admin queue: renters who say they've paid, awaiting a manual check."""
    return (
        Booking.query.filter_by(status=STATUS_AWAITING_PAYMENT)
        .order_by(Booking.created_at.asc())
        .all()
    )


def confirm_payment_received(booking: Booking, *, admin: User) -> Booking:
    """Admin confirms the transfer landed: AWAITING_PAYMENT -> PAID.

    Creates confirmed ``rental_payment`` + ``deposit`` ledger entries.
    """
    if booking.status != STATUS_AWAITING_PAYMENT:
        raise InvalidPaymentTransition(
            "This booking isn't awaiting payment confirmation."
        )
    booking.status = STATUS_PAID
    ledger_service.record_payment_received(booking, admin=admin)
    db.session.commit()
    return booking


def bookings_awaiting_payout() -> list[Booking]:
    """Admin queue: completed rentals with a still-pending payout / refund."""
    completed = (
        Booking.query.filter_by(status=STATUS_COMPLETED)
        .order_by(Booking.created_at.asc())
        .all()
    )
    return [b for b in completed if ledger_service.has_pending_entries(b)]


def confirm_payout(booking: Booking, *, admin: User) -> Booking:
    """Admin confirms the owner payout + renter refund have been sent."""
    if booking.status != STATUS_COMPLETED:
        raise InvalidPaymentTransition("Only completed bookings have a payout.")
    ledger_service.confirm_all_for_booking(booking, admin=admin)
    return booking
