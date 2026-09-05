"""Booking service — the rental request / accept / reject / cancel flow.

All state-machine logic lives here (not in routes) so the future ``/api/v1`` can
reuse it verbatim (blueprint §4). Only the front half of the lifecycle exists
yet (blueprint §5):

    REQUESTED --(owner accepts)--> ACCEPTED
    REQUESTED --(owner rejects)--> CANCELLED
    REQUESTED/ACCEPTED --(either party cancels)--> CANCELLED

PAID/HANDED_OVER/ACTIVE/RETURNED/COMPLETED/DISPUTED land with M4/M5.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date

from sqlalchemy import or_

from app.extensions import db
from app.models import Booking, Listing, User
from app.services import notifications
from app.models.booking import (
    BLOCKING_STATUSES,
    STATUS_ACCEPTED,
    STATUS_ACTIVE,
    STATUS_AWAITING_PAYMENT,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PAID,
    STATUS_REQUESTED,
    STATUS_RETURNED,
)


class BookingError(Exception):
    """Base class for booking-flow errors."""


class InvalidBookingRequest(BookingError):
    """Raised when the requested dates or listing don't make sense."""


class BookingPermissionError(BookingError):
    """Raised when a user acts on a booking they have no standing over."""


class InvalidBookingTransition(BookingError):
    """Raised when a status change isn't legal from the booking's current state."""


class BookingConflict(BookingError):
    """Raised when accepting would double-book an item's dates."""


def _dates_overlap(start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
    return start_a <= end_b and start_b <= end_a


def rental_amount_for(booking: Booking) -> Decimal:
    """The booking's total rental fee.

    Uses the snapshot taken at request time; falls back to
    ``listing.price_per_day * days`` for pre-M4 rows that never got one.
    """
    if booking.rental_amount is not None:
        return Decimal(booking.rental_amount)
    return Decimal(booking.listing.price_per_day) * booking.rental_days


def has_overlapping_acceptance(
    listing_id: int, start_date: date, end_date: date, *, exclude_booking_id: int | None = None
) -> bool:
    """True if the listing already has a committed booking overlapping this range.

    "Committed" = any status past REQUESTED that hasn't been cancelled/completed
    (see :data:`BLOCKING_STATUSES`), so a second request can't be accepted onto
    dates an in-flight rental already holds.
    """
    q = Booking.query.filter(
        Booking.listing_id == listing_id,
        Booking.status.in_(BLOCKING_STATUSES),
    )
    if exclude_booking_id is not None:
        q = q.filter(Booking.id != exclude_booking_id)
    return any(
        _dates_overlap(start_date, end_date, b.rental_date_start, b.rental_date_end)
        for b in q.all()
    )


def request_to_rent(
    listing: Listing, renter: User, *, start_date: date, end_date: date,
    message: str | None = None,
) -> Booking:
    """Create a REQUESTED booking for ``listing``.

    :raises InvalidBookingRequest: bad dates, or the renter owns the listing.
    """
    if renter.id == listing.owner_id:
        raise InvalidBookingRequest("You can't rent your own listing.")
    if start_date is None or end_date is None:
        raise InvalidBookingRequest("Please choose start and end dates.")
    if start_date < date.today():
        raise InvalidBookingRequest("Start date can't be in the past.")
    if end_date < start_date:
        raise InvalidBookingRequest("End date must be on or after the start date.")

    booking = Booking(
        listing_id=listing.id,
        renter_id=renter.id,
        owner_id=listing.owner_id,
        status=STATUS_REQUESTED,
        rental_date_start=start_date,
        rental_date_end=end_date,
        deposit_amount=listing.deposit_amount,
        message_from_renter=(message or "").strip() or None,
    )
    booking.rental_amount = Decimal(listing.price_per_day) * booking.rental_days
    db.session.add(booking)
    db.session.commit()
    notifications.booking_requested(booking)
    return booking


def get_booking(booking_id: int) -> Booking | None:
    return db.session.get(Booking, booking_id)


def has_booking_on_listing(user_id: int, listing_id: int) -> bool:
    """True if ``user_id`` is a party (renter or owner) on any booking for this
    listing — used to let an archived/non-active listing stay viewable by
    direct link for someone with real history on it (not the public)."""
    return db.session.query(
        Booking.query.filter(
            Booking.listing_id == listing_id,
            or_(Booking.renter_id == user_id, Booking.owner_id == user_id),
        ).exists()
    ).scalar()


def listing_ids_with_bookings(listing_ids: list[int]) -> set[int]:
    """Which of these listing ids have at least one booking against them.

    Used by My Listings to decide whether to offer Delete (only safe with no
    booking history — see ``ListingHasBookings``) alongside Archive.
    """
    if not listing_ids:
        return set()
    rows = (
        db.session.query(Booking.listing_id)
        .filter(Booking.listing_id.in_(listing_ids))
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def requests_for_owner(owner: User) -> list[Booking]:
    """Pending rental requests (REQUESTED) for the owner's listings, oldest first."""
    return (
        Booking.query.filter_by(owner_id=owner.id, status=STATUS_REQUESTED)
        .order_by(Booking.created_at.asc())
        .all()
    )


def pending_count_for_owner(owner: User) -> int:
    """Count of REQUESTED bookings against the owner's listings — nav badge."""
    return Booking.query.filter_by(owner_id=owner.id, status=STATUS_REQUESTED).count()


def completed_count() -> int:
    """Platform-wide count of completed rentals — used in the homepage stats row."""
    return Booking.query.filter_by(status=STATUS_COMPLETED).count()


def active_for_owner(owner: User) -> list[Booking]:
    """Owner's in-flight bookings (accepted → returned), soonest return first."""
    return (
        Booking.query.filter(
            Booking.owner_id == owner.id,
            Booking.status.in_(BLOCKING_STATUSES),
        )
        .order_by(Booking.rental_date_end.asc())
        .all()
    )


def completed_for_owner(owner: User) -> list[Booking]:
    """Owner's finished/cancelled bookings, most recent first."""
    return (
        Booking.query.filter(
            Booking.owner_id == owner.id,
            Booking.status.in_((STATUS_COMPLETED, STATUS_CANCELLED)),
        )
        .order_by(Booking.created_at.desc())
        .all()
    )


def pending_for_renter(renter: User) -> list[Booking]:
    """Bookings the renter made that are still awaiting the owner's decision."""
    return (
        Booking.query.filter_by(renter_id=renter.id, status=STATUS_REQUESTED)
        .order_by(Booking.created_at.desc())
        .all()
    )


def active_for_renter(renter: User) -> list[Booking]:
    """Renter's in-flight bookings — owner-accepted through returned-awaiting."""
    return (
        Booking.query.filter(
            Booking.renter_id == renter.id,
            Booking.status.in_(BLOCKING_STATUSES),
        )
        .order_by(Booking.rental_date_start.asc())
        .all()
    )


def history_for_renter(renter: User) -> list[Booking]:
    """Finished bookings — completed rentals and cancelled/rejected requests."""
    return (
        Booking.query.filter(
            Booking.renter_id == renter.id,
            Booking.status.in_((STATUS_COMPLETED, STATUS_CANCELLED)),
        )
        .order_by(Booking.created_at.desc())
        .all()
    )


def accept(booking: Booking, *, owner: User) -> Booking:
    """Owner accepts a REQUESTED booking.

    :raises BookingPermissionError: ``owner`` isn't this booking's owner.
    :raises InvalidBookingTransition: the booking isn't REQUESTED.
    :raises BookingConflict: the dates overlap an already-ACCEPTED booking.
    """
    if booking.owner_id != owner.id:
        raise BookingPermissionError("You don't own this listing.")
    if booking.status != STATUS_REQUESTED:
        raise InvalidBookingTransition("Only pending requests can be accepted.")
    if has_overlapping_acceptance(
        booking.listing_id, booking.rental_date_start, booking.rental_date_end,
        exclude_booking_id=booking.id,
    ):
        raise BookingConflict("This item is already booked for overlapping dates.")

    booking.status = STATUS_ACCEPTED
    db.session.commit()
    notifications.booking_accepted(booking)
    return booking


def reject(booking: Booking, *, owner: User) -> Booking:
    """Owner rejects a REQUESTED booking.

    :raises BookingPermissionError: ``owner`` isn't this booking's owner.
    :raises InvalidBookingTransition: the booking isn't REQUESTED.
    """
    if booking.owner_id != owner.id:
        raise BookingPermissionError("You don't own this listing.")
    if booking.status != STATUS_REQUESTED:
        raise InvalidBookingTransition("Only pending requests can be rejected.")

    booking.status = STATUS_CANCELLED
    db.session.commit()
    notifications.booking_rejected(booking)
    return booking


def cancel(booking: Booking, *, user: User) -> Booking:
    """Either the renter or the owner cancels a REQUESTED/ACCEPTED booking.

    :raises BookingPermissionError: ``user`` is neither party on this booking.
    :raises InvalidBookingTransition: the booking is already CANCELLED.
    """
    if user.id not in (booking.renter_id, booking.owner_id):
        raise BookingPermissionError("You're not part of this booking.")
    # Cancellable only while no money has been confirmed as received.
    if booking.status not in (STATUS_REQUESTED, STATUS_ACCEPTED, STATUS_AWAITING_PAYMENT):
        raise InvalidBookingTransition("This booking can no longer be cancelled.")

    booking.status = STATUS_CANCELLED
    db.session.commit()
    return booking


def confirm_return(booking: Booking, *, owner: User) -> Booking:
    """Owner confirms the item came back in good condition: RETURNED -> COMPLETED.

    Queues the money side (blueprint §1, §7): a 20% commission on the rental fee,
    a payout of the rest to the owner, and a full deposit refund to the renter —
    all as *pending* ledger entries until an admin confirms the real payout via
    ``/admin/payments``.

    :raises BookingPermissionError: ``owner`` isn't this booking's owner.
    :raises InvalidBookingTransition: the booking isn't RETURNED.
    """
    from app.services import ledger as ledger_service

    if booking.owner_id != owner.id:
        raise BookingPermissionError("You don't own this listing.")
    if booking.status != STATUS_RETURNED:
        raise InvalidBookingTransition(
            "The item must be marked returned (after-photos uploaded) first."
        )

    booking.status = STATUS_COMPLETED
    ledger_service.record_completion_entries(booking)
    db.session.commit()
    notifications.booking_completed(booking)
    return booking
