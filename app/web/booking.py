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
from app.services import cancellation as cancellation_service
from app.services import disputes as disputes_service
from app.services import evidence as evidence_service
from app.services import ledger as ledger_service
from app.services import listings as listings_service
from app.services import payments as payments_service
from app.services import reviews as reviews_service
from app.services import settings as settings_service

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


@web_bp.route("/bookings/<int:booking_id>/request-cancellation", methods=["POST"])
@login_required
def request_booking_cancellation(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        cancellation_service.request_cancellation(
            booking, current_user, reason=request.form.get("reason", ""),
        )
    except cancellation_service.CancellationNotAllowed as exc:
        if current_user.id not in (booking.renter_id, booking.owner_id):
            abort(403)
        flash(str(exc), "error")
    except cancellation_service.CancellationAlreadyRequested as exc:
        flash(str(exc), "info")
    else:
        flash(
            "Cancellation requested. A CIRCLO admin will arrange the refund and "
            "confirm the cancellation.",
            "success",
        )
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
    from datetime import datetime, timedelta
    from decimal import Decimal

    from app.models.booking import (
        STATUS_ACTIVE, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_HANDED_OVER,
        STATUS_PAID, STATUS_RETURNED,
    )

    owner_requests = booking_service.requests_for_owner(current_user)
    owner_active = booking_service.active_for_owner(current_user)
    owner_history = booking_service.completed_for_owner(current_user)
    renter_pending = booking_service.pending_for_renter(current_user)
    renter_active = booking_service.active_for_renter(current_user)
    renter_history = booking_service.history_for_renter(current_user)
    owner_listings = listings_service.listings_for_owner(current_user)

    commission_rate = ledger_service.COMMISSION_RATE

    def _amount(b):
        """(amount, label) for this booking's money cell, from the viewer's side."""
        is_owner = b.owner_id == current_user.id
        if b.status == STATUS_CANCELLED:
            return Decimal("0"), ("No charge" if is_owner else "Refunded")
        rental = booking_service.rental_amount_for(b)
        if is_owner:
            payout = (rental * (Decimal("1") - commission_rate)).quantize(Decimal("1"))
            label = "Paid out" if b.status == STATUS_COMPLETED else "Payout"
            return payout, label
        total = rental + Decimal(b.deposit_amount)
        paid = b.status in (
            STATUS_PAID, STATUS_HANDED_OVER, STATUS_ACTIVE, STATUS_RETURNED,
            STATUS_COMPLETED,
        )
        return total, ("Paid" if paid else "To pay")

    def _detail(bookings):
        out = {}
        for b in bookings:
            open_dispute = next((d for d in b.disputes if d.status == "open"), None)
            amount, amount_label = _amount(b)
            out[b.id] = {
                "before_me": evidence_service.has_uploaded(b, current_user.id, "before"),
                "after_me": evidence_service.has_uploaded(b, current_user.id, "after"),
                "before_both": evidence_service.both_parties_uploaded(b, "before"),
                "after_both": evidence_service.both_parties_uploaded(b, "after"),
                "media": evidence_service.evidence_for_booking(b),
                "ledger": ledger_service.entries_for_booking(b),
                "can_review": reviews_service.can_review(b, current_user),
                "my_review": reviews_service.review_by(b, current_user),
                "open_dispute": open_dispute,
                "can_dispute": (
                    open_dispute is None
                    and b.status in disputes_service.DISPUTABLE_STATUSES
                ),
                "can_reveal_contact": booking_service.can_reveal_contact(b),
                "cancel_action": cancellation_service.available_action(b, current_user),
                "pending_cancellation": cancellation_service.open_request_for(b),
                "amount": amount,
                "amount_label": amount_label,
                "is_owner": b.owner_id == current_user.id,
            }
        return out

    all_shown = (
        owner_requests + owner_active + owner_history
        + renter_pending + renter_active + renter_history
    )

    return render_template(
        "rentals/my_rentals.html",
        owner_requests=owner_requests,
        owner_active=owner_active,
        owner_history=owner_history,
        owner_listings=owner_listings,
        renter_pending=renter_pending,
        renter_active=renter_active,
        renter_history=renter_history,
        booking_detail=_detail(all_shown),
        payment_details=settings_service.payment_details(),
        payment_configured=settings_service.has_payment_details(),
        active_listings_count=sum(
            1 for l in owner_listings if l.status == listings_service.BROWSABLE_STATUS
        ),
        owner_rating=current_user.rating,
        earnings_30d=ledger_service.owner_earnings_since(
            current_user.id, datetime.utcnow() - timedelta(days=30)
        ),
    )
