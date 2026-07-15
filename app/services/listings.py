"""Listings service — read-only browse/search/detail logic.

All query logic lives here (not in routes) so the future ``/api/v1`` can reuse it
verbatim (blueprint §4). Routes are thin adapters that call these functions and
render HTML; the API will call the same functions and return JSON.
"""
from __future__ import annotations

from sqlalchemy import or_

from app.extensions import db
from app.models import Category, Listing

# Only listings in this status are shown to renters.
BROWSABLE_STATUS = "active"


def all_categories() -> list[Category]:
    """Every category, alphabetically — used to render the filter chips."""
    return Category.query.order_by(Category.name).all()


def browse_listings(*, category_slug: str | None = None,
                    query: str | None = None) -> list[Listing]:
    """Active listings, optionally filtered by category and/or a text query.

    The text query matches title, description or area (case-insensitive) so a
    renter can search "drill", "camera" or "F-7" and get sensible results.
    """
    q = Listing.query.filter(Listing.status == BROWSABLE_STATUS)

    if category_slug:
        q = q.join(Category).filter(Category.slug == category_slug)

    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(
                Listing.title.ilike(like),
                Listing.description.ilike(like),
                Listing.area.ilike(like),
            )
        )

    return q.order_by(Listing.created_at.desc()).all()


def get_listing(listing_id: int) -> Listing | None:
    """Return a listing by id, or ``None`` if it doesn't exist.

    Routes decide how to handle a miss (the web route aborts with 404).
    """
    return db.session.get(Listing, listing_id)
