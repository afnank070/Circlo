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
        ratings=reviews_service.rating_breakdown(user),
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


@web_bp.route("/account", methods=["POST"])
@login_required
def update_account():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    errors = []
    if not name:
        errors.append("Please enter your name.")
    if not email or "@" not in email:
        errors.append("Please enter a valid email address.")

    if not errors:
        try:
            auth_service.update_account(current_user, name=name, email=email, phone=phone)
        except auth_service.EmailAlreadyRegistered:
            errors.append("That email is already registered to another account.")
        else:
            flash("Profile updated.", "success")

    for msg in errors:
        flash(msg, "error")
    return redirect(url_for("web.user_profile", user_id=current_user.id))


@web_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    # OAuth-only accounts have no password to change — nothing to show here.
    if not current_user.has_password:
        abort(404)

    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm") or ""

        errors = []
        if len(new_password) < 8:
            errors.append("New password must be at least 8 characters.")
        if new_password != confirm:
            errors.append("New passwords do not match.")

        if not errors:
            try:
                auth_service.change_password(current_user, current_password, new_password)
            except auth_service.IncorrectPassword:
                errors.append("Your current password is incorrect.")
            else:
                flash("Password changed.", "success")
                return redirect(url_for("web.user_profile", user_id=current_user.id))

        for msg in errors:
            flash(msg, "error")

    return render_template("users/change_password.html")


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
