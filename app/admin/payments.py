"""Admin payments — the semi-manual money step (blueprint §7).

Two queues:

* **Awaiting payment** — the renter says they've transferred rental + deposit.
  The admin checks the bank / JazzCash statement by hand and clicks
  "Confirm payment received" → ledger entries created, booking moves to PAID.
* **Awaiting payout** — a completed rental whose owner payout + deposit refund
  are still pending. The admin sends the money by hand and clicks
  "Confirm payout sent" → ledger entries flip to confirmed.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, url_for
from flask_login import current_user

from app.services import booking as booking_service
from app.services import ledger as ledger_service
from app.services import payments as payments_service

from . import admin_bp, admin_required


@admin_bp.route("/payments")
@admin_required
def payments_queue():
    awaiting_payment = payments_service.bookings_awaiting_payment_confirmation()
    awaiting_payout = payments_service.bookings_awaiting_payout()
    return render_template(
        "payments_queue.html",
        awaiting_payment=awaiting_payment,
        awaiting_payout=awaiting_payout,
        rental_amount_for=booking_service.rental_amount_for,
        ledger_for=ledger_service.entries_for_booking,
    )


@admin_bp.route("/payments/<int:booking_id>/confirm-payment", methods=["POST"])
@admin_required
def confirm_payment(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("admin.payments_queue"))
    try:
        payments_service.confirm_payment_received(booking, admin=current_user)
    except payments_service.PaymentError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Payment confirmed for booking #{booking.id}.", "success")
    return redirect(url_for("admin.payments_queue"))


@admin_bp.route("/payments/<int:booking_id>/confirm-payout", methods=["POST"])
@admin_required
def confirm_payout(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("admin.payments_queue"))
    try:
        payments_service.confirm_payout(booking, admin=current_user)
    except payments_service.PaymentError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Payout + refund confirmed for booking #{booking.id}.", "success")
    return redirect(url_for("admin.payments_queue"))
