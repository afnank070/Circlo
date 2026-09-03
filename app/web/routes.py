"""Web routes — read-only marketplace (M2).

Thin adapters: they call the listings service for data and render Jinja. All
query logic lives in ``app/services/listings.py`` so the future ``/api/v1`` reuses
it. Internal links use ``url_for`` and image URLs are built at runtime from the
stored object key (blueprint §9).
"""
from __future__ import annotations

from flask import abort, jsonify, render_template, request

from app.services import listings as listings_service
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

    return render_template(
        "index.html",
        listings=results,
        categories=categories,
        active_category=category,
        query=query or "",
    )


@web_bp.route("/listings/<int:listing_id>")
def listing_detail(listing_id: int):
    """Listing detail: image + price/deposit/owner + trust strip + CTA."""
    listing = listings_service.get_listing(listing_id)
    if listing is None or listing.status != listings_service.BROWSABLE_STATUS:
        abort(404)
    return render_template("listing_detail.html", listing=listing)


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
