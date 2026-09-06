"""Area model — a standardized Islamabad / Rawalpindi sector or neighbourhood.

Blueprint §1 (twin cities only). "Area" used to be free text an owner typed at
listing time, so "F-7", "F7" and "F-7 Islamabad" never matched in the browse
filter. This reference table fixes the vocabulary: every listing's ``area``
string must equal one of these ``name`` values (enforced in
``app.services.listings``), and the browse filter's dropdown is populated from
this table so a chosen area always matches stored data exactly.

The canonical rows live in :data:`app.services.areas.CANONICAL_AREAS` and are
upserted into this table by ``areas.sync_areas`` (run from ``flask seed`` and
the schema migration).
"""
from __future__ import annotations

from app.extensions import db


class Area(db.Model):
    __tablename__ = "areas"

    id = db.Column(db.Integer, primary_key=True)
    # The canonical display + stored value, e.g. "F-7", "Bahria Town Phase 4".
    name = db.Column(db.String(80), nullable=False, unique=True)
    # URL-safe identifier for query strings, e.g. "f-7".
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    # "Islamabad" or "Rawalpindi" — keeps the city distinction alongside area.
    city = db.Column(db.String(80), nullable=False, index=True)
    # Ordering hint so the dropdown lists sectors before named neighbourhoods.
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Area {self.slug} ({self.city})>"
