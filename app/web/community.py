"""Community web routes — public profiles, reviews, and dispute reporting.

Thin adapters over the review / dispute services (blueprint §4, §6).
"""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import auth as auth_service
from app.services import booking as booking_service
from app.services import disputes as disputes_service
from app.services import reviews as reviews_service

from . import web_bp


@web_bp.route("/users/<int:user_id>")
def user_profile(user_id: int):
    user = auth_service.get_user(user_id)
    if user is None:
        abort(404)
    return render_template(
        "users/profile.html",
        profile_user=user,
        reviews=reviews_service.reviews_about(user),
    )


@web_bp.route("/account/phone", methods=["POST"])
@login_required
def update_phone():
    phone = (request.form.get("phone") or "").strip()
    if not phone:
        flash("Enter a phone number.", "error")
    else:
        auth_service.set_phone(current_user, phone)
        flash("Phone number saved.", "success")
    return redirect(url_for("web.user_profile", user_id=current_user.id))


@web_bp.route("/bookings/<int:booking_id>/review", methods=["POST"])
@login_required
def leave_review(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        reviews_service.leave_review(
            booking, current_user,
            rating=request.form.get("rating"),
            comment=request.form.get("comment", ""),
        )
    except reviews_service.ReviewNotAllowed as exc:
        if current_user.id not in (booking.renter_id, booking.owner_id):
            abort(403)
        flash(str(exc), "error")
    except reviews_service.AlreadyReviewed as exc:
        flash(str(exc), "info")
    else:
        flash("Thanks for your review.", "success")
    return redirect(url_for("web.my_rentals"))


@web_bp.route("/bookings/<int:booking_id>/dispute", methods=["POST"])
@login_required
def report_problem(booking_id: int):
    booking = booking_service.get_booking(booking_id)
    if booking is None:
        abort(404)
    try:
        disputes_service.open_dispute(
            booking, current_user, reason=request.form.get("reason", ""),
        )
    except disputes_service.DisputeNotAllowed as exc:
        if current_user.id not in (booking.renter_id, booking.owner_id):
            abort(403)
        flash(str(exc), "error")
    except disputes_service.DisputeAlreadyOpen as exc:
        flash(str(exc), "info")
    else:
        flash("Problem reported. Our team will review it and be in touch.", "success")
    return redirect(url_for("web.my_rentals"))
