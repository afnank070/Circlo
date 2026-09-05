"""Listing model — an item someone offers for rent.

Blueprint §5: a Listing belongs to a User via ``owner_id``. M2 shipped this as
denormalised ``owner_name`` / ``owner_rating`` / ``is_verified`` fields because the
User model didn't exist yet; M1 introduces the real FK and exposes owner name,
rating and verified-status as thin properties off the ``owner`` relationship so
templates read the same as before.

Prices are stored in PKR as fixed-point Numerics. Money never moves here.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class Listing(db.Model):
    __tablename__ = "listings"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")

    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True
    )

    # Twin cities only for the MVP (blueprint §1).
    city = db.Column(db.String(80), nullable=False)
    area = db.Column(db.String(80), nullable=False)

    # PKR, whole rupees in practice but kept as Numeric for safety.
    price_per_day = db.Column(db.Numeric(10, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Handover details, revealed to the renter once a booking is accepted
    # (see app/services/booking.py CONTACT_REVEAL_STATUSES). Both optional —
    # an owner may not have a fixed pickup spot yet or may skip the map link.
    pickup_location = db.Column(db.String(160), nullable=True)
    map_link = db.Column(db.String(500), nullable=True)

    # The member who owns this item (blueprint §5). Replaces the M2 denormalised
    # owner_name/owner_rating/is_verified columns.
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )

    # draft / active / paused / removed (blueprint §5). Only "active" is browsable.
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    owner = db.relationship("User", back_populates="listings")
    category = db.relationship("Category", back_populates="listings")
    images = db.relationship(
        "ListingImage",
        back_populates="listing",
        order_by="ListingImage.sort_order",
        cascade="all, delete-orphan",
    )

    @property
    def cover_image(self):
        """First image (by sort order), or None if the listing has no images."""
        return self.images[0] if self.images else None

    # --- Owner passthroughs (keep templates/API reading listing-level fields) --
    @property
    def owner_name(self) -> str:
        return self.owner.name if self.owner else ""

    @property
    def owner_rating(self):
        """Owner's cached rating, or None if they have no ratings yet."""
        return self.owner.rating if self.owner else None

    @property
    def is_verified(self) -> bool:
        """Green 'Verified' badge — derived from the owner's identity status."""
        return bool(self.owner and self.owner.is_verified)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Listing {self.id} {self.title!r}>"
