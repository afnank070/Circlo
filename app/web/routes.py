"""Web routes — read-only marketplace (M2).

Thin adapters: they call the listings service for data and render Jinja. All
query logic lives in ``app/services/listings.py`` so the future ``/api/v1`` reuses
it. Internal links use ``url_for`` and image URLs are built at runtime from the
stored object key (blueprint §9).
"""
from __future__ import annotations

from flask import abort, jsonify, render_template, request
from flask_login import current_user

from app.services import booking as booking_service
from app.services import listings as listings_service
from app.services import reviews as reviews_service
from app.services import storage

from . import web_bp


@web_bp.app_template_global()
def image_url(key: str | None) -> str | None:
    """Jinja helper: turn a stored object key into a browser-usable URL."""
    if not key:
        return None
    return storage.presigned_url(key)


@web_bp.route("/")
def index():
    """Browse page: card grid with category-chip and text search filters."""
    category = request.args.get("category") or None
    query = request.args.get("q") or None

    results = listings_service.browse_listings(category_slug=category, query=query)
    categories = listings_service.all_categories()

    # Real marketplace stats for the homepage stats row — never hardcoded.
    stats = {
        "listings": listings_service.total_listings_count(),
        "completed_rentals": booking_service.completed_count(),
        "avg_rating": reviews_service.platform_average_rating(),
    }

    return render_template(
        "index.html",
        listings=results,
        categories=categories,
        active_category=category,
        query=query or "",
        stats=stats,
    )


@web_bp.route("/listings/<int:listing_id>")
def listing_detail(listing_id: int):
    """Listing detail: image + price/deposit/owner + trust strip + CTA.

    Only "active" listings are publicly visible. An archived (or otherwise
    non-active) listing stays reachable by direct link for its owner, and for
    anyone with a booking on it — so rental history/evidence stays viewable —
    but 404s for everyone else, same as a nonexistent listing.
    """
    listing = listings_service.get_listing(listing_id)
    if listing is None:
        abort(404)
    if listing.status != listings_service.BROWSABLE_STATUS:
        may_view = current_user.is_authenticated and (
            current_user.id == listing.owner_id
            or booking_service.has_booking_on_listing(current_user.id, listing.id)
        )
        if not may_view:
            abort(404)

    # "Also nearby" — reuses the same browse query the home page uses, just
    # filtered to this listing's category and capped at 4.
    related = [
        l for l in listings_service.browse_listings(category_slug=listing.category.slug)
        if l.id != listing.id
    ][:4]

    return render_template("listing_detail.html", listing=listing, related=related)


@web_bp.route("/how-it-works")
def how_it_works():
    """Explainer — how renting/listing works end to end. Static page."""
    return render_template("how_it_works.html")


@web_bp.route("/trust-deposits")
def trust_deposits():
    """Explainer — deposits, evidence, and the Trust & Safety Fund. Static page."""
    return render_template("trust_deposits.html")


@web_bp.route("/privacy")
def privacy():
    """Privacy policy — static page (required for Google OAuth verification)."""
    return render_template("legal/privacy.html")


@web_bp.route("/terms")
def terms():
    """Terms of service — static page (required for Google OAuth verification)."""
    return render_template("legal/terms.html")


@web_bp.route("/health")
def health():
    """Liveness probe consumed by Docker/monitoring. Returns JSON."""
    return jsonify(status="ok")
