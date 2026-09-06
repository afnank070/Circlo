"""Areas service — the standardized Islamabad / Rawalpindi location vocabulary.

:data:`CANONICAL_AREAS` is the single source of truth for every valid listing
area. It is:

* upserted into the ``areas`` table by :func:`sync_areas` (called from
  ``flask seed`` and the schema migration),
* used to validate the area chosen on the listing form
  (:func:`is_valid_area`, called from ``app.services.listings``),
* rendered into the listing form's searchable dropdown and the browse page's
  "All areas" filter (:func:`areas_by_city`),
* used to map legacy free-text area values onto the closest canonical name
  (:func:`closest_area`) during the migration and as a defensive fallback.

All logic lives here so ``/api/v1`` reuses it.
"""
from __future__ import annotations

import re

from app.extensions import db
from app.models import Area

ISLAMABAD = "Islamabad"
RAWALPINDI = "Rawalpindi"
CITIES = (ISLAMABAD, RAWALPINDI)

# (name, city). Order within a city is preserved as the dropdown order:
# lettered sectors first, then well-known named neighbourhoods and schemes.
_ISLAMABAD_AREAS = [
    "E-7", "E-8", "E-9", "E-11", "E-12", "E-16", "E-17",
    "F-5", "F-6", "F-7", "F-8", "F-10", "F-11", "F-12", "F-15", "F-17",
    "G-5", "G-6", "G-7", "G-8", "G-9", "G-10", "G-11", "G-12", "G-13",
    "G-14", "G-15", "G-16",
    "H-8", "H-9", "H-11", "H-12", "H-13",
    "I-8", "I-9", "I-10", "I-11", "I-12", "I-14", "I-15", "I-16",
    "D-12", "D-13", "D-17", "B-17",
    "Blue Area", "Diplomatic Enclave", "Margalla Town", "Bani Gala",
    "Bhara Kahu", "Chak Shahzad", "Tarlai", "Rawat", "Saidpur Village",
    "Shah Allah Ditta", "Golra Sharif", "Ghauri Town", "Pakistan Town",
    "PWD Housing Society", "Media Town", "Soan Gardens", "Naval Anchorage",
    "CBR Town", "Korang Town", "Bahria Enclave", "Gulberg Greens",
    "Gulberg Residencia", "DHA Phase 1", "DHA Phase 2", "DHA Phase 3",
    "DHA Phase 5",
]
_RAWALPINDI_AREAS = [
    "Saddar", "Raja Bazaar", "Committee Chowk", "Murree Road",
    "Commercial Market", "Satellite Town", "Chaklala Scheme 1",
    "Chaklala Scheme 3", "Chaklala Cantt", "Rawalpindi Cantt", "Westridge",
    "Tench Bhatta", "Misrial Road", "Adiala Road", "Peshawar Road",
    "Airport Housing Society", "PAF Complex", "Askari 10", "Askari 11",
    "Askari 13", "Askari 14", "Gulraiz Housing Scheme", "Media Town (Rawalpindi)",
    "Dhoke Kala Khan", "Dhoke Hassu", "Dhoke Ratta", "Dhamial", "Morgah",
    "Gulzar-e-Quaid", "Chungi No. 22", "Lalazar", "Officers Colony",
    "Judicial Colony", "Gulistan Colony", "Iqbal Town", "Shakrial",
    "Khanna Pul", "Pirwadhai", "Kohati Bazaar", "National Police Foundation",
    "Bahria Town", "Bahria Town Phase 1", "Bahria Town Phase 2",
    "Bahria Town Phase 3", "Bahria Town Phase 4", "Bahria Town Phase 5",
    "Bahria Town Phase 6", "Bahria Town Phase 7", "Bahria Town Phase 8",
    "Bahria Town Civic Centre",
]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


CANONICAL_AREAS: list[dict] = []
for _i, _name in enumerate(_ISLAMABAD_AREAS):
    CANONICAL_AREAS.append(
        {"name": _name, "slug": _slugify(_name), "city": ISLAMABAD, "sort_order": _i}
    )
for _i, _name in enumerate(_RAWALPINDI_AREAS):
    CANONICAL_AREAS.append(
        {"name": _name, "slug": _slugify(_name), "city": RAWALPINDI, "sort_order": _i}
    )

# Fast lookups off the frozen list (independent of the DB).
_BY_NAME = {a["name"]: a for a in CANONICAL_AREAS}
_BY_SLUG = {a["slug"]: a for a in CANONICAL_AREAS}
_NAMES_LOWER = {a["name"].lower(): a["name"] for a in CANONICAL_AREAS}


# --- Validation / lookup -----------------------------------------------------
def area_names() -> list[str]:
    """Every canonical area name, in dropdown order."""
    return [a["name"] for a in CANONICAL_AREAS]


def is_valid_area(name: str | None) -> bool:
    """True if ``name`` is exactly a canonical area (case-sensitive match)."""
    return bool(name) and name in _BY_NAME


def city_for_area(name: str | None) -> str | None:
    entry = _BY_NAME.get(name or "")
    return entry["city"] if entry else None


def area_by_slug(slug: str | None) -> dict | None:
    return _BY_SLUG.get(slug or "")


# --- Rendering helpers ------------------------------------------------------
def all_areas() -> list[Area]:
    """Every area row from the DB, city then sort_order (dropdown source)."""
    return Area.query.order_by(Area.city.asc(), Area.sort_order.asc()).all()


def areas_by_city() -> dict[str, list[Area]]:
    """DB area rows grouped ``{city: [Area, ...]}`` for optgroup rendering.

    Falls back to the frozen canonical list if the table hasn't been populated
    yet (fresh DB, migration not run) so the dropdown is never empty.
    """
    rows = all_areas()
    if not rows:
        grouped: dict[str, list] = {c: [] for c in CITIES}
        for a in CANONICAL_AREAS:
            grouped[a["city"]].append(
                Area(name=a["name"], slug=a["slug"], city=a["city"],
                     sort_order=a["sort_order"])
            )
        return grouped

    grouped = {c: [] for c in CITIES}
    for row in rows:
        grouped.setdefault(row.city, []).append(row)
    return grouped


# --- Legacy free-text mapping ---------------------------------------------
_CITY_WORDS = re.compile(
    r"\b(islamabad|rawalpindi|isb|rwp|pindi|pakistan|sector)\b", re.I
)


def _normalize_sector(text: str) -> str:
    """"f7", "F 7", "F-7 Markaz" -> "F-7" when it looks like a lettered sector."""
    m = re.match(r"\s*([a-iA-I])\s*-?\s*(\d{1,2})\b", text)
    if m:
        return f"{m.group(1).upper()}-{int(m.group(2))}"
    return text.strip()


def closest_area(raw: str | None, *, city: str | None = None) -> str:
    """Best-effort map a legacy free-text area onto a canonical name.

    Tries, in order: exact match, case-insensitive match, lettered-sector
    normalization ("F7" -> "F-7"), substring match against canonical names.
    Falls back to the first canonical area of ``city`` (or the very first
    canonical area) so a listing is never left with a non-standard value.
    """
    raw = (raw or "").strip()
    if raw in _BY_NAME:
        return raw
    if raw.lower() in _NAMES_LOWER:
        return _NAMES_LOWER[raw.lower()]

    stripped = _CITY_WORDS.sub("", raw).strip(" ,-")
    sector = _normalize_sector(stripped)
    if sector in _BY_NAME:
        return sector

    cleaned = stripped.lower()
    if cleaned:
        for entry in CANONICAL_AREAS:
            n = entry["name"].lower()
            if cleaned == n or cleaned in n or n in cleaned:
                return entry["name"]

    if city in CITIES:
        for entry in CANONICAL_AREAS:
            if entry["city"] == city:
                return entry["name"]
    return CANONICAL_AREAS[0]["name"]


# --- Sync into the DB ------------------------------------------------------
def sync_areas() -> int:
    """Upsert :data:`CANONICAL_AREAS` into the ``areas`` table. Returns the count.

    Idempotent: matches on ``slug``, updates name/city/sort_order, inserts what's
    missing. Does not delete extras (there shouldn't be any).
    """
    existing = {a.slug: a for a in Area.query.all()}
    for entry in CANONICAL_AREAS:
        row = existing.get(entry["slug"])
        if row is None:
            db.session.add(Area(**entry))
        else:
            row.name = entry["name"]
            row.city = entry["city"]
            row.sort_order = entry["sort_order"]
    db.session.commit()
    return len(CANONICAL_AREAS)
