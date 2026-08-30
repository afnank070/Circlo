"""Disputes service — raise a problem on a booking, admin resolves it.

Blueprint §5 (side path: any active state -> DISPUTED -> admin resolves) and §6
(Trust & Safety Fund). For the MVP the booking's own status is left unchanged —
the Dispute row is the record — and any compensation is *tracked* via
``amount_from_fund``, not paid through a gateway.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models import Booking, Dispute, User
from app.models.booking import STATUS_ACTIVE, STATUS_COMPLETED, STATUS_RETURNED
from app.models.dispute import (
    DEPOSIT_PENDING,
    DEPOSIT_RELEASED,
    DEPOSIT_WITHHELD,
    STATUS_OPEN,
    STATUS_RESOLVED,
)

# A dispute can be opened while the item is out or recently back.
DISPUTABLE_STATUSES = (STATUS_ACTIVE, STATUS_RETURNED, STATUS_COMPLETED)
VALID_DEPOSIT_DECISIONS = (DEPOSIT_PENDING, DEPOSIT_RELEASED, DEPOSIT_WITHHELD)


class DisputeError(Exception):
    """Base class for dispute-flow errors."""


class DisputeNotAllowed(DisputeError):
    """Wrong booking state, or the user isn't a party to the booking."""


class DisputeAlreadyOpen(DisputeError):
    """This booking already has an unresolved dispute."""


def open_dispute(booking: Booking, opener: User, *, reason: str) -> Dispute:
    if opener.id not in (booking.renter_id, booking.owner_id):
        raise DisputeNotAllowed("You're not part of this booking.")
    if booking.status not in DISPUTABLE_STATUSES:
        raise DisputeNotAllowed(
            "A problem can only be reported once the rental is active or has ended."
        )
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise DisputeNotAllowed("Please describe the problem (at least a sentence).")
    if Dispute.query.filter_by(booking_id=booking.id, status=STATUS_OPEN).first():
        raise DisputeAlreadyOpen("There's already an open dispute for this booking.")

    dispute = Dispute(
        booking_id=booking.id,
        opened_by=opener.id,
        reason=reason,
        status=STATUS_OPEN,
    )
    db.session.add(dispute)
    db.session.commit()
    return dispute


def get_dispute(dispute_id: int) -> Dispute | None:
    return db.session.get(Dispute, dispute_id)


def open_disputes() -> list[Dispute]:
    return (
        Dispute.query.filter_by(status=STATUS_OPEN)
        .order_by(Dispute.created_at.asc())
        .all()
    )


def resolved_disputes() -> list[Dispute]:
    return (
        Dispute.query.filter_by(status=STATUS_RESOLVED)
        .order_by(Dispute.resolved_at.desc())
        .all()
    )


def disputes_for_user(user: User) -> list[Dispute]:
    booking_ids = [
        b.id for b in Booking.query.filter(
            (Booking.renter_id == user.id) | (Booking.owner_id == user.id)
        ).all()
    ]
    if not booking_ids:
        return []
    return (
        Dispute.query.filter(Dispute.booking_id.in_(booking_ids))
        .order_by(Dispute.created_at.desc())
        .all()
    )


def resolve_dispute(
    dispute: Dispute, *, admin: User, resolution: str,
    deposit_decision: str = DEPOSIT_PENDING, amount_from_fund=0,
) -> Dispute:
    if dispute.status == STATUS_RESOLVED:
        raise DisputeError("This dispute is already resolved.")
    resolution = (resolution or "").strip()
    if not resolution:
        raise DisputeError("Please record how the dispute was resolved.")
    if deposit_decision not in VALID_DEPOSIT_DECISIONS:
        raise DisputeError("Invalid deposit decision.")
    try:
        amount = Decimal(str(amount_from_fund or "0"))
    except Exception:  # noqa: BLE001
        raise DisputeError("Trust-fund amount must be a number.")
    if amount < 0:
        raise DisputeError("Trust-fund amount can't be negative.")

    dispute.status = STATUS_RESOLVED
    dispute.resolution = resolution
    dispute.deposit_decision = deposit_decision
    dispute.amount_from_fund = amount
    dispute.resolved_at = datetime.utcnow()
    dispute.resolved_by = admin.id
    db.session.commit()
    return dispute
