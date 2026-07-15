"""Listing model — an item someone offers for rent.

Blueprint §5 defines Listing with an ``owner_id`` FK to User, but the User model
only arrives in M1 (Auth). For this read-only marketplace milestone the owner is
captured as denormalised ``owner_name`` / ``owner_rating`` fields populated by the
seed script; M1 will introduce the FK and migrate these onto the User relationship.

Prices are stored in PKR as fixed-point Numerics. Money never moves here — this
milestone is browse-only.
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

    # Denormalised owner info until the User model lands in M1.
    owner_name = db.Column(db.String(120), nullable=False)
    owner_rating = db.Column(db.Numeric(2, 1), nullable=False, default=0)

    # Green "Verified" badge on cards; becomes derived from User.verification_status in M1.
    is_verified = db.Column(db.Boolean, nullable=False, default=False)

    # draft / active / paused / removed (blueprint §5). Only "active" is browsable.
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

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

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Listing {self.id} {self.title!r}>"
