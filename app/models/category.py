"""Category model — the top-level grouping for listings.

Categories are a fixed, small set for the MVP (Tools, Cameras, Camping, Gaming,
Events, Formal Wear) and are created by the seed script. Blueprint §5.
"""
from __future__ import annotations

from app.extensions import db


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    # URL-safe identifier used in filter chips / query strings (e.g. "formal-wear").
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)

    listings = db.relationship("Listing", back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Category {self.slug}>"
