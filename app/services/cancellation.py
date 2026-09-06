"""Cancellation service — pull a booking out of the rental flow (blueprint §5, §7).

The rules change with the booking's stage:

============================  ==================================================
Stage                         What either party can do
============================  ==================================================
REQUESTED / ACCEPTED          Cancel instantly — no money has moved. Handled by
                              :func:`app.services.booking.cancel`.
AWAITING_PAYMENT / PAID       Raise a :class:`CancellationRequest` (``pending``).
                              An admin confirms the refund was sent by hand
                              (same manual pattern as the M4 payout step) and
                              marks the booking CANCELLED.
HANDED_OVER / ACTIVE /        No cancellation — the item is physically
RETURNED                      exchanged. Point the user at the dispute flow.
COMPLETED / CANCELLED         Nothing to do.
============================  ==================================================

All state lives here so ``/api/v1`` can reuse it. The other party is emailed
whenever a cancellation happens or is requested.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models import Booking, CancellationRequest, User
from app.models.booking import (
    STATUS_ACTIVE,
    STATUS_AWAITING_PAYMENT,
    STATUS_CANCELLED,
    STATUS_HANDED_OVER,
    STATUS_PAID,
    STATUS_RETURNED,
)
from app.models.cancellation_request import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from app.models.ledger_entry import STATUS_CONFIRMED as LEDGER_CONFIRMED
from app.models.ledger_entry import TYPE_DEPOSIT, TYPE_REFUND, TYPE_RENTAL_PAYMENT
from app.services import booking as booking_service
from app.services import ledger as ledger_service
from app.services import notifications

# Stage where cancelling still needs an admin to hand back money.
ADMIN_CANCEL_STATUSES = (STATUS_AWAITING_PAYMENT, STATUS_PAID)
# Stage where the item is already exchanged — dispute, don't cancel.
DISPUTE_ONLY_STATUSES = (STATUS_HANDED_OVER, STATUS_ACTIVE, STATUS_RETURNED)


class CancellationError(Exception):
    """Base class for cancellation-flow errors."""


class CancellationNotAllowed(CancellationError):
    """Wrong booking stage, or the user isn't a party to the booking."""


class CancellationAlreadyRequested(CancellationError):
    """This booking already has a pending cancellation request."""


def _is_party(booking: Booking, user: User) -> bool:
    return user.id in (booking.renter_id, booking.owner_id)


def _other_party(booking: Booking, user: User) -> User:
    return booking.owner if user.id == booking.renter_id else booking.renter


def open_request_for(booking: Booking) -> CancellationRequest | None:
    """The booking's pending cancellation request, if any."""
    return CancellationRequest.query.filter_by(
        booking_id=booking.id, status=STATUS_PENDING
    ).first()


def available_action(booking: Booking, user: User) -> str | None:
    """Which cancellation control to show ``user`` for ``booking`` on My Rentals.

    One of:
      * ``"cancel"``   — instant Cancel button (pre-payment).
      * ``"request"``  — "Request cancellation" (money moved, admin needed).
      * ``"pending"``  — a request is already in with the admin.
      * ``"dispute"``  — too late to cancel; use "Report a problem".
      * ``None``       — nothing to offer (not a party, completed, cancelled).
    """
    if not _is_party(booking, user):
        return None
    if booking.status in booking_service.FREE_CANCEL_STATUSES:
        return "cancel"
    if booking.status in ADMIN_CANCEL_STATUSES:
        return "pending" if open_request_for(booking) else "request"
    if booking.status in DISPUTE_ONLY_STATUSES:
        return "dispute"
    return None


def request_cancellation(
    booking: Booking, user: User, *, reason: str = ""
) -> CancellationRequest:
    """Either party asks CIRCLO to cancel a paid/awaiting-payment booking.

    :raises CancellationNotAllowed: not a party, or the booking isn't in a
        stage where a cancellation request applies.
    :raises CancellationAlreadyRequested: a request is already pending.
    """
    if not _is_party(booking, user):
        raise CancellationNotAllowed("You're not part of this booking.")
    if booking.status in booking_service.FREE_CANCEL_STATUSES:
        raise CancellationNotAllowed(
            "This booking can still be cancelled directly — no request needed."
        )
    if booking.status not in ADMIN_CANCEL_STATUSES:
        raise CancellationNotAllowed(
            "The item is already exchanged — report a problem instead of cancelling."
        )
    if open_request_for(booking) is not None:
        raise CancellationAlreadyRequested(
            "There's already a cancellation request on this booking."
        )

    req = CancellationRequest(
        booking_id=booking.id,
        requested_by=user.id,
        reason=(reason or "").strip() or None,
        status=STATUS_PENDING,
    )
    db.session.add(req)
    db.session.commit()
    notifications.cancellation_requested(booking, by_user=user)
    return req


def refundable_amount(booking: Booking) -> Decimal:
    """How much the renter has actually paid in (confirmed ledger inflows).

    Zero for an AWAITING_PAYMENT booking an admin never confirmed — the renter
    only *claimed* to have paid, so there may be nothing to send back.
    """
    total = Decimal("0")
    for entry in ledger_service.entries_for_booking(booking):
        if (
            entry.status == LEDGER_CONFIRMED
            and entry.type in (TYPE_RENTAL_PAYMENT, TYPE_DEPOSIT)
        ):
            total += Decimal(entry.amount)
    return total


# --- Admin side ---------------------------------------------------------------
def pending_requests() -> list[CancellationRequest]:
    """Admin queue: cancellation requests awaiting a manual refund + confirm."""
    return (
        CancellationRequest.query.filter_by(status=STATUS_PENDING)
        .order_by(CancellationRequest.created_at.asc())
        .all()
    )


def get_request(request_id: int) -> CancellationRequest | None:
    return db.session.get(CancellationRequest, request_id)


def confirm_cancellation(req: CancellationRequest, *, admin: User) -> CancellationRequest:
    """Admin confirms the refund was sent by hand and cancels the booking.

    Records a matching confirmed ``refund`` ledger entry (reusing the M4
    manual-refund pattern) for whatever the renter had actually paid in, moves
    the booking to CANCELLED, and emails both parties.
    """
    if req.status != STATUS_PENDING:
        raise CancellationError("This cancellation request is already resolved.")

    booking = req.booking
    refund = refundable_amount(booking)
    if refund > 0:
        entry = ledger_service.record(
            booking, TYPE_REFUND, refund, status=LEDGER_CONFIRMED, commit=False
        )
        entry.confirmed_by = admin.id
        entry.confirmed_at = datetime.utcnow()

    booking.status = STATUS_CANCELLED
    req.status = STATUS_CONFIRMED
    req.resolved_at = datetime.utcnow()
    req.resolved_by = admin.id
    db.session.commit()

    notifications.cancellation_confirmed(booking)
    return req


def reject_cancellation(req: CancellationRequest, *, admin: User) -> CancellationRequest:
    """Admin declines the request — the booking carries on unchanged."""
    if req.status != STATUS_PENDING:
        raise CancellationError("This cancellation request is already resolved.")

    req.status = STATUS_REJECTED
    req.resolved_at = datetime.utcnow()
    req.resolved_by = admin.id
    db.session.commit()

    notifications.cancellation_rejected(req.booking, requester=req.requester)
    return req
