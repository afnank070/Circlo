"""ListingImage model — a photo attached to a listing.

Only the storage **object key** is persisted (blueprint §9); the browser-facing
URL is built at runtime by the storage service. Never store full URLs here.
"""
from __future__ import annotations

from app.extensions import db


class ListingImage(db.Model):
    __tablename__ = "listing_images"

    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(
        db.Integer, db.ForeignKey("listings.id"), nullable=False, index=True
    )
    # e.g. "listings/canon-eos-r6/cover.svg" — a key, not a URL.
    object_key = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    listing = db.relationship("Listing", back_populates="images")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ListingImage {self.object_key}>"
