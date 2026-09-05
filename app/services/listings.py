"""Listings service — browse/search/detail plus owner create/edit/delete logic.

All query and mutation logic lives here (not in routes) so the future ``/api/v1``
can reuse it verbatim (blueprint §4). Routes are thin adapters that call these
functions and render HTML; the API will call the same functions and return JSON.

Images go to S3-compatible storage through the storage service; only the object
**key** is persisted (blueprint §9).
"""
from __future__ import annotations

import uuid

from sqlalchemy import or_
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Booking, Category, Listing, ListingImage
from app.services import storage


class ListingHasBookings(Exception):
    """Raised when deleting a listing that has rental history.

    ``bookings.listing_id`` is a required (non-nullable) FK with no delete
    cascade — hard-deleting a listing with bookings would otherwise hit an
    ``IntegrityError`` at commit time. Rental history (and the ledger/evidence
    tied to it) must be preserved, so deletion is refused instead.
    """

# Only listings in this status are shown to renters.
BROWSABLE_STATUS = "active"

# Off the marketplace but not deleted — reversible via reactivate_listing().
# Reuses the "paused" value from the blueprint §5 status vocabulary
# (draft/active/paused/removed) rather than adding a new column value.
ARCHIVED_STATUS = "paused"

# Guardrails for owner uploads.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_EXT_FOR_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_IMAGES_PER_LISTING = 8


def all_categories() -> list[Category]:
    """Every category, alphabetically — used to render the filter chips."""
    return Category.query.order_by(Category.name).all()


def total_listings_count() -> int:
    """All listings ever created, any status — a "items listed" trust stat."""
    return Listing.query.count()


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


def get_category(category_id: int) -> Category | None:
    return db.session.get(Category, category_id)


def listings_for_owner(owner) -> list[Listing]:
    """Every listing owned by ``owner`` (any status), newest first."""
    return (
        Listing.query.filter(Listing.owner_id == owner.id)
        .order_by(Listing.created_at.desc())
        .all()
    )


# --- Owner mutations --------------------------------------------------------
def _store_images(listing: Listing, files, *, start_order: int = 0) -> int:
    """Upload valid image files for ``listing`` and attach ListingImage rows.

    Silently skips empty file inputs and non-image types (the route validates and
    surfaces user-facing messages). Returns the number of images stored. Enforces
    :data:`MAX_IMAGES_PER_LISTING` across the listing's existing + new images.
    """
    stored = 0
    order = start_order
    existing = len(listing.images)
    for f in files:
        if not isinstance(f, FileStorage) or not f.filename:
            continue
        if existing + stored >= MAX_IMAGES_PER_LISTING:
            break
        content_type = (f.mimetype or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            continue
        ext = _EXT_FOR_TYPE[content_type]
        key = f"listings/{listing.id}/{uuid.uuid4().hex}.{ext}"
        storage.upload_fileobj(f.stream, key, content_type=content_type)
        listing.images.append(ListingImage(object_key=key, sort_order=order))
        order += 1
        stored += 1
    return stored


def create_listing(*, owner, title: str, description: str, category_id: int,
                   city: str, area: str, price_per_day, deposit_amount,
                   images=None) -> Listing:
    """Create an ``active`` listing owned by ``owner`` and store any images.

    The listing is flushed first so it has an id to key images under, then images
    are uploaded and the whole thing is committed atomically.
    """
    listing = Listing(
        owner_id=owner.id,
        title=title.strip(),
        description=(description or "").strip(),
        category_id=category_id,
        city=city.strip(),
        area=area.strip(),
        price_per_day=price_per_day,
        deposit_amount=deposit_amount,
        status=BROWSABLE_STATUS,
    )
    db.session.add(listing)
    db.session.flush()  # assign listing.id for image keys

    if images:
        _store_images(listing, images)

    db.session.commit()
    return listing


def update_listing(listing: Listing, *, title: str, description: str,
                   category_id: int, city: str, area: str, price_per_day,
                   deposit_amount, new_images=None,
                   remove_image_ids=None) -> Listing:
    """Update a listing's fields, optionally removing and/or adding images."""
    listing.title = title.strip()
    listing.description = (description or "").strip()
    listing.category_id = category_id
    listing.city = city.strip()
    listing.area = area.strip()
    listing.price_per_day = price_per_day
    listing.deposit_amount = deposit_amount

    if remove_image_ids:
        remove = set(remove_image_ids)
        for img in list(listing.images):
            if img.id in remove:
                storage.delete_object(img.object_key)
                listing.images.remove(img)  # delete-orphan removes the row

    if new_images:
        next_order = (max((i.sort_order for i in listing.images), default=-1)) + 1
        _store_images(listing, new_images, start_order=next_order)

    db.session.commit()
    return listing


def delete_listing(listing: Listing) -> None:
    """Delete a listing and its stored images (storage objects first).

    Raises :class:`ListingHasBookings` if any booking (pending, active, or
    historical) references this listing — see that class's docstring.
    """
    has_bookings = db.session.query(
        Booking.query.filter(Booking.listing_id == listing.id).exists()
    ).scalar()
    if has_bookings:
        raise ListingHasBookings(
            "This listing has rental history and can't be deleted."
        )

    for img in listing.images:
        storage.delete_object(img.object_key)
    db.session.delete(listing)
    db.session.commit()


def archive_listing(listing: Listing) -> Listing:
    """Take a listing off the public marketplace without deleting it.

    Unlike :func:`delete_listing`, this works regardless of booking history —
    it's the reversible alternative for a listing that has rental history (or
    that the owner just wants off the marketplace for now). The listing stops
    appearing in browse/search (``browse_listings`` only returns
    :data:`BROWSABLE_STATUS`), but stays reachable by direct link for the
    owner and anyone with a booking on it (see ``web.listing_detail``).
    """
    listing.status = ARCHIVED_STATUS
    db.session.commit()
    return listing


def reactivate_listing(listing: Listing) -> Listing:
    """Put an archived listing back on the public marketplace."""
    listing.status = BROWSABLE_STATUS
    db.session.commit()
    return listing
