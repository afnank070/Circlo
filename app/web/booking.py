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
from app.services import evidence as evidence_service
from app.services import ledger as ledger_service
from app.services import listings as listings_service
from app.services import payments as payments_service

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


@web_bp.route("/bookings/<int:booking_id>/mark-paid", methods=["POST"])
@login_required
def mark_booking_paid(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        payments_service.mark_awaiting_payment(booking, renter=current_user)
    except payments_service.PaymentPermissionError:
        abort(403)
    except payments_service.InvalidPaymentTransition as exc:
        flash(str(exc), "error")
    else:
        flash("Thanks — we'll confirm your payment shortly.", "success")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/bookings/<int:booking_id>/evidence", methods=["POST"])
@login_required
def upload_booking_evidence(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    phase = request.form.get("phase", "")
    try:
        evidence_service.upload_evidence(
            booking, current_user, phase=phase, file=request.files.get("photo"),
        )
    except evidence_service.EvidencePermissionError:
        abort(403)
    except evidence_service.InvalidEvidenceUpload as exc:
        flash(str(exc), "error")
    else:
        flash("Photo uploaded.", "success")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/bookings/<int:booking_id>/confirm-return", methods=["POST"])
@login_required
def confirm_booking_return(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        booking_service.confirm_return(booking, owner=current_user)
    except booking_service.BookingPermissionError:
        abort(403)
    except booking_service.InvalidBookingTransition as exc:
        flash(str(exc), "error")
    else:
        flash("Return confirmed. Payout and deposit refund are queued.", "success")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/my-rentals")
@login_required
def my_rentals():
    owner_active = booking_service.active_for_owner(current_user)
    renter_active = booking_service.active_for_renter(current_user)

    def _evidence(bookings):
        return {
            b.id: {
                "before_me": evidence_service.has_uploaded(b, current_user.id, "before"),
                "after_me": evidence_service.has_uploaded(b, current_user.id, "after"),
                "before_both": evidence_service.both_parties_uploaded(b, "before"),
                "after_both": evidence_service.both_parties_uploaded(b, "after"),
                "media": evidence_service.evidence_for_booking(b),
                "ledger": ledger_service.entries_for_booking(b),
            }
            for b in bookings
        }

    return render_template(
        "rentals/my_rentals.html",
        owner_requests=booking_service.requests_for_owner(current_user),
        owner_active=owner_active,
        owner_history=booking_service.completed_for_owner(current_user),
        owner_listings=listings_service.listings_for_owner(current_user),
        renter_pending=booking_service.pending_for_renter(current_user),
        renter_active=renter_active,
        renter_history=booking_service.history_for_renter(current_user),
        booking_detail=_evidence(owner_active + renter_active),
    )
