"""Owner listing routes — create / edit / delete your own listings.

Login-required, ownership-guarded adapters over :mod:`app.services.listings`.
Browse and detail stay public (in ``routes.py``); only mutation is gated here.
Form parsing/validation lives here; the actual persistence + image upload lives in
the service so ``/api/v1`` can reuse it.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.services import listings as listings_service

from . import web_bp


def _owned_or_404(listing_id: int):
    """Fetch a listing the current user owns, else 404 (don't leak existence)."""
    listing = listings_service.get_listing(listing_id)
    if listing is None:
        abort(404)
    if listing.owner_id != current_user.id:
        abort(403)
    return listing


def _parse_form(form):
    """Pull + validate the shared listing fields. Returns (data, errors)."""
    data = {
        "title": (form.get("title") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "city": (form.get("city") or "").strip(),
        "area": (form.get("area") or "").strip(),
        "category_id": form.get("category_id") or "",
        "price_per_day": (form.get("price_per_day") or "").strip(),
        "deposit_amount": (form.get("deposit_amount") or "").strip(),
    }
    errors = []

    if not data["title"]:
        errors.append("Title is required.")
    if not data["city"]:
        errors.append("City is required.")
    if not data["area"]:
        errors.append("Area is required.")

    try:
        data["category_id"] = int(data["category_id"])
        if listings_service.get_category(data["category_id"]) is None:
            errors.append("Please choose a valid category.")
    except (TypeError, ValueError):
        errors.append("Please choose a category.")

    for field, label in (("price_per_day", "Price"), ("deposit_amount", "Deposit")):
        try:
            value = Decimal(data[field])
            if value < 0:
                raise InvalidOperation
            data[field] = value
        except (InvalidOperation, TypeError):
            errors.append(f"{label} must be a number (0 or more).")

    return data, errors


@web_bp.route("/listings/new", methods=["GET", "POST"])
@login_required
def create_listing():
    # Verification gating (blueprint §5, §8): only verified users may list items.
    # Same pattern applies to renting once M3 lands.
    if not current_user.is_verified:
        flash("Verify your identity to list items.", "info")
        return redirect(url_for("web.verify"))

    categories = listings_service.all_categories()

    if request.method == "POST":
        data, errors = _parse_form(request.form)
        images = request.files.getlist("images")

        if errors:
            for msg in errors:
                flash(msg, "error")
            return render_template(
                "listings/form.html",
                mode="create",
                categories=categories,
                form=request.form,
                listing=None,
            )

        listing = listings_service.create_listing(
            owner=current_user,
            title=data["title"],
            description=data["description"],
            category_id=data["category_id"],
            city=data["city"],
            area=data["area"],
            price_per_day=data["price_per_day"],
            deposit_amount=data["deposit_amount"],
            images=images,
        )
        flash("Listing published.", "success")
        return redirect(url_for("web.listing_detail", listing_id=listing.id))

    return render_template(
        "listings/form.html",
        mode="create",
        categories=categories,
        form={},
        listing=None,
    )


@web_bp.route("/listings/<int:listing_id>/edit", methods=["GET", "POST"])
@login_required
def edit_listing(listing_id: int):
    listing = _owned_or_404(listing_id)
    categories = listings_service.all_categories()

    if request.method == "POST":
        data, errors = _parse_form(request.form)
        new_images = request.files.getlist("images")
        remove_ids = [int(x) for x in request.form.getlist("remove_images") if x.isdigit()]

        if errors:
            for msg in errors:
                flash(msg, "error")
            return render_template(
                "listings/form.html",
                mode="edit",
                categories=categories,
                form=request.form,
                listing=listing,
            )

        listings_service.update_listing(
            listing,
            title=data["title"],
            description=data["description"],
            category_id=data["category_id"],
            city=data["city"],
            area=data["area"],
            price_per_day=data["price_per_day"],
            deposit_amount=data["deposit_amount"],
            new_images=new_images,
            remove_image_ids=remove_ids,
        )
        flash("Listing updated.", "success")
        return redirect(url_for("web.listing_detail", listing_id=listing.id))

    return render_template(
        "listings/form.html",
        mode="edit",
        categories=categories,
        form={},
        listing=listing,
    )


@web_bp.route("/listings/<int:listing_id>/delete", methods=["POST"])
@login_required
def delete_listing(listing_id: int):
    listing = _owned_or_404(listing_id)
    listings_service.delete_listing(listing)
    flash("Listing deleted.", "info")
    return redirect(url_for("web.my_listings"))


@web_bp.route("/my/listings")
@login_required
def my_listings():
    owned = listings_service.listings_for_owner(current_user)
    return render_template("listings/my_listings.html", listings=owned)
