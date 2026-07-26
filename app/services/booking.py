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

from datetime import date

from app.extensions import db
from app.models import Booking, Listing, User
from app.models.booking import STATUS_ACCEPTED, STATUS_CANCELLED, STATUS_REQUESTED


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


def has_overlapping_acceptance(
    listing_id: int, start_date: date, end_date: date, *, exclude_booking_id: int | None = None
) -> bool:
    """True if listing already has an ACCEPTED booking overlapping this range."""
    q = Booking.query.filter(
        Booking.listing_id == listing_id,
        Booking.status == STATUS_ACCEPTED,
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
    db.session.add(booking)
    db.session.commit()
    return booking


def get_booking(booking_id: int) -> Booking | None:
    return db.session.get(Booking, booking_id)


def requests_for_owner(owner: User) -> list[Booking]:
    """Pending rental requests (REQUESTED) for the owner's listings, oldest first."""
    return (
        Booking.query.filter_by(owner_id=owner.id, status=STATUS_REQUESTED)
        .order_by(Booking.created_at.asc())
        .all()
    )


def active_for_owner(owner: User) -> list[Booking]:
    """Items currently rented out (ACCEPTED), soonest return date first."""
    return (
        Booking.query.filter_by(owner_id=owner.id, status=STATUS_ACCEPTED)
        .order_by(Booking.rental_date_end.asc())
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
    """Bookings the renter made that the owner accepted."""
    return (
        Booking.query.filter_by(renter_id=renter.id, status=STATUS_ACCEPTED)
        .order_by(Booking.rental_date_start.asc())
        .all()
    )


def history_for_renter(renter: User) -> list[Booking]:
    """Cancelled/rejected bookings. (COMPLETED history lands with M4.)"""
    return (
        Booking.query.filter_by(renter_id=renter.id, status=STATUS_CANCELLED)
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
    return booking


def cancel(booking: Booking, *, user: User) -> Booking:
    """Either the renter or the owner cancels a REQUESTED/ACCEPTED booking.

    :raises BookingPermissionError: ``user`` is neither party on this booking.
    :raises InvalidBookingTransition: the booking is already CANCELLED.
    """
    if user.id not in (booking.renter_id, booking.owner_id):
        raise BookingPermissionError("You're not part of this booking.")
    if booking.status not in (STATUS_REQUESTED, STATUS_ACCEPTED):
        raise InvalidBookingTransition("This booking can no longer be cancelled.")

    booking.status = STATUS_CANCELLED
    db.session.commit()
    return booking
