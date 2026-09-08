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
from datetime import datetime

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
    """Raised when accepting would double-book an item's hours."""


# The rental unit is hours. A booking must be at least this many hours long.
MIN_RENTAL_HOURS = 1


# Contact details (phone numbers) and the listing's pickup location/map link are
# revealed once a booking has been accepted — i.e. any status at or past ACCEPTED,
# including a finished rental. Not revealed for a still-pending request or a
# cancelled one. This is a plain data reveal, not messaging (blueprint: no chat).
CONTACT_REVEAL_STATUSES = BLOCKING_STATUSES + (STATUS_COMPLETED,)


def can_reveal_contact(booking: Booking) -> bool:
    """True once both parties should see each other's phone + pickup details."""
    return booking.status in CONTACT_REVEAL_STATUSES


def _ranges_overlap(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    """True if two half-open time windows [start, end) intersect.

    Half-open on purpose: a booking that ends exactly when another starts
    (2pm–4pm and 4pm–6pm) does **not** conflict, but any real hour of overlap
    (2pm–4pm vs 3pm–5pm) does.
    """
    return start_a < end_b and start_b < end_a


def rental_amount_for(booking: Booking) -> Decimal:
    """The booking's total rental fee.

    Uses the snapshot taken at request time; falls back to
    ``listing.price_per_hour * duration_hours`` for rows that never got one.
    """
    if booking.rental_amount is not None:
        return Decimal(booking.rental_amount)
    return Decimal(booking.listing.price_per_hour) * booking.duration_hours


def has_overlapping_acceptance(
    listing_id: int, start_dt: datetime, end_dt: datetime, *,
    exclude_booking_id: int | None = None,
) -> bool:
    """True if the listing already has a committed booking whose hour range
    overlaps ``[start_dt, end_dt)``.

    "Committed" = any status past REQUESTED that hasn't been cancelled/completed
    (see :data:`BLOCKING_STATUSES`), so a second request can't be accepted onto
    hours an in-flight rental already holds.
    """
    q = Booking.query.filter(
        Booking.listing_id == listing_id,
        Booking.status.in_(BLOCKING_STATUSES),
    )
    if exclude_booking_id is not None:
        q = q.filter(Booking.id != exclude_booking_id)
    return any(
        _ranges_overlap(start_dt, end_dt, b.start_datetime, b.end_datetime)
        for b in q.all()
    )


def request_to_rent(
    listing: Listing, renter: User, *, start_datetime: datetime, duration_hours,
    message: str | None = None,
) -> Booking:
    """Create a REQUESTED booking for ``listing``.

    ``start_datetime`` is when the rental begins (hour precision) and
    ``duration_hours`` is how long it runs for (minimum :data:`MIN_RENTAL_HOURS`).

    :raises InvalidBookingRequest: bad start/duration, or the renter owns the
        listing.
    """
    if renter.id == listing.owner_id:
        raise InvalidBookingRequest("You can't rent your own listing.")
    if start_datetime is None:
        raise InvalidBookingRequest("Please choose a start date and time.")
    try:
        duration_hours = int(duration_hours)
    except (TypeError, ValueError):
        raise InvalidBookingRequest("Enter how many hours you need the item for.")
    if duration_hours < MIN_RENTAL_HOURS:
        raise InvalidBookingRequest(
            f"Rentals are a minimum of {MIN_RENTAL_HOURS} hour."
        )
    if start_datetime < datetime.now():
        raise InvalidBookingRequest("Start time can't be in the past.")

    booking = Booking(
        listing_id=listing.id,
        renter_id=renter.id,
        owner_id=listing.owner_id,
        status=STATUS_REQUESTED,
        start_datetime=start_datetime,
        duration_hours=duration_hours,
        deposit_amount=listing.deposit_amount,
        message_from_renter=(message or "").strip() or None,
    )
    booking.rental_amount = Decimal(listing.price_per_hour) * duration_hours
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


def completed_counts(user: User) -> dict:
    """How many rentals ``user`` has completed on each side — profile stats.

    Returns ``{"as_owner": n, "as_renter": m}`` (COMPLETED bookings only).
    """
    return {
        "as_owner": Booking.query.filter_by(
            status=STATUS_COMPLETED, owner_id=user.id
        ).count(),
        "as_renter": Booking.query.filter_by(
            status=STATUS_COMPLETED, renter_id=user.id
        ).count(),
    }


def active_for_owner(owner: User) -> list[Booking]:
    """Owner's in-flight bookings (accepted → returned), soonest return first."""
    return (
        Booking.query.filter(
            Booking.owner_id == owner.id,
            Booking.status.in_(BLOCKING_STATUSES),
        )
        .order_by(Booking.start_datetime.asc())
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
        .order_by(Booking.start_datetime.asc())
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
        booking.listing_id, booking.start_datetime, booking.end_datetime,
        exclude_booking_id=booking.id,
    ):
        raise BookingConflict("This item is already booked for overlapping hours.")

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


# Free (instant) cancellation — no money has moved yet, either party can just
# pull out. Past this the money side needs an admin (see services.cancellation).
FREE_CANCEL_STATUSES = (STATUS_REQUESTED, STATUS_ACCEPTED)


def cancel(booking: Booking, *, user: User) -> Booking:
    """Either the renter or the owner instantly cancels a pre-payment booking.

    Only valid while the booking is REQUESTED or ACCEPTED (no money involved).
    Once payment is in play (AWAITING_PAYMENT / PAID) cancellation must go
    through :func:`app.services.cancellation.request_cancellation` so an admin
    can confirm the refund; from HANDED_OVER on it's gone entirely (dispute
    flow instead).

    :raises BookingPermissionError: ``user`` is neither party on this booking.
    :raises InvalidBookingTransition: the booking is past free cancellation.
    """
    if user.id not in (booking.renter_id, booking.owner_id):
        raise BookingPermissionError("You're not part of this booking.")
    if booking.status not in FREE_CANCEL_STATUSES:
        raise InvalidBookingTransition("This booking can no longer be cancelled.")

    booking.status = STATUS_CANCELLED
    db.session.commit()
    notifications.booking_cancelled(booking, by_user=user)
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
