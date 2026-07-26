"""Booking web routes — request to rent, owner/renter rentals queue.

Thin adapters over :mod:`app.services.booking`; date parsing/validation-message
mapping lives here, the state machine lives in the service so ``/api/v1`` can
reuse it later (blueprint §4).
"""
from __future__ import annotations

from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import booking as booking_service
from app.services import listings as listings_service

from . import web_bp


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@web_bp.route("/listings/<int:listing_id>/request", methods=["POST"])
@login_required
def request_booking(listing_id: int):
    listing = listings_service.get_listing(listing_id)
    if listing is None or listing.status != listings_service.BROWSABLE_STATUS:
        abort(404)

    if not current_user.is_verified:
        flash("Verify your identity to rent items.", "info")
        return redirect(url_for("web.verify"))

    start_date = _parse_date(request.form.get("start_date"))
    end_date = _parse_date(request.form.get("end_date"))
    message = request.form.get("message")

    try:
        booking_service.request_to_rent(
            listing, current_user,
            start_date=start_date, end_date=end_date, message=message,
        )
    except booking_service.InvalidBookingRequest as exc:
        flash(str(exc), "error")
        return redirect(url_for("web.listing_detail", listing_id=listing.id, open_request=1))

    flash("Rental request sent to the owner.", "success")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/bookings/<int:booking_id>/accept", methods=["POST"])
@login_required
def accept_booking(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        booking_service.accept(booking, owner=current_user)
    except booking_service.BookingPermissionError:
        abort(403)
    except (booking_service.InvalidBookingTransition, booking_service.BookingConflict) as exc:
        flash(str(exc), "error")
    else:
        flash("Rental request accepted.", "success")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/bookings/<int:booking_id>/reject", methods=["POST"])
@login_required
def reject_booking(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        booking_service.reject(booking, owner=current_user)
    except booking_service.BookingPermissionError:
        abort(403)
    except booking_service.InvalidBookingTransition as exc:
        flash(str(exc), "error")
    else:
        flash("Rental request rejected.", "info")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        booking_service.cancel(booking, user=current_user)
    except booking_service.BookingPermissionError:
        abort(403)
    except booking_service.InvalidBookingTransition as exc:
        flash(str(exc), "error")
    else:
        flash("Booking cancelled.", "info")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/my-rentals")
@login_required
def my_rentals():
    return render_template(
        "rentals/my_rentals.html",
        owner_requests=booking_service.requests_for_owner(current_user),
        owner_active=booking_service.active_for_owner(current_user),
        owner_listings=listings_service.listings_for_owner(current_user),
        renter_pending=booking_service.pending_for_renter(current_user),
        renter_active=booking_service.active_for_renter(current_user),
        renter_history=booking_service.history_for_renter(current_user),
    )
