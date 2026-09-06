"""Seed service — populate the marketplace with realistic demo data.

Inserts a demo user per owner, the fixed category set, and ~10 Islamabad/Rawalpindi
listings, and pushes a real cover photo for each through the existing storage
service so the whole image pipeline (download → upload → stored key → runtime
presigned URL) is exercised end-to-end with no extra dependencies (stdlib
``urllib`` only — no Pillow, no ``requests``).

Photos are fetched from Unsplash's public CDN (``images.unsplash.com``, no API
key needed for direct photo fetches) — one hand-picked photo id per listing that
matches the item (see :data:`UNSPLASH_PHOTO_IDS`), not a generic category stock
image. If a fetch fails (offline dev box, Unsplash hiccup), the seed falls back
to the old SVG placeholder for that listing so ``flask seed`` still completes.

Every seed owner shares the same demo password (:data:`SEED_PASSWORD`) so the
listings can be logged into and edited while testing M1 — see PROGRESS.md.

Idempotent: object keys are derived from a slug, and the DB rows are wiped and
re-inserted on every run, so ``flask seed`` can be run repeatedly.
"""
from __future__ import annotations

import io
import re
import urllib.error
import urllib.request

from app.extensions import db
from app.models import Category, Listing, ListingImage, User
from app.services import areas as areas_service
from app.services import storage

# Shared password for every seeded demo owner (dev only — see PROGRESS.md).
SEED_PASSWORD = "circlo123"
# Emails are derived as "<name-slug>@demo.circlo.pk"; this is the domain.
SEED_EMAIL_DOMAIN = "demo.circlo.pk"

# --- Category set (blueprint / prompt) --------------------------------------
CATEGORIES = [
    ("Tools", "tools", "#f59e0b", "#b45309"),
    ("Cameras", "cameras", "#0ea5e9", "#0369a1"),
    ("Camping", "camping", "#10b981", "#047857"),
    ("Gaming", "gaming", "#8b5cf6", "#6d28d9"),
    ("Events", "events", "#f43f5e", "#be123c"),
    ("Formal Wear", "formal-wear", "#db2777", "#9d174d"),
]

# --- Seed listings ----------------------------------------------------------
# (title, category_slug, city, area, price_per_day, deposit, owner, rating, verified, description)
LISTINGS = [
    ("Bosch Hammer Drill (Corded)", "tools", "Islamabad", "F-8", 800, 5000,
     "Ahmed Raza", 4.8, True,
     "Powerful 750W corded hammer drill, great for concrete and masonry. Comes with a full bit set and carry case."),
    ("Makita Angle Grinder 4\"", "tools", "Rawalpindi", "Satellite Town", 600, 4000,
     "Bilal Khan", 4.5, True,
     "Reliable Makita angle grinder for cutting and polishing. Two spare discs included."),
    ("Canon EOS R6 Mirrorless Kit", "cameras", "Islamabad", "F-7", 3500, 40000,
     "Sara Malik", 4.9, True,
     "Full-frame Canon EOS R6 with 24-105mm lens, two batteries and a 64GB card. Perfect for weddings and shoots."),
    ("DJI Mavic Air 2 Drone", "cameras", "Rawalpindi", "Bahria Town", 4000, 50000,
     "Hamza Sheikh", 4.7, True,
     "4K camera drone with three batteries and ND filters. Ideal for aerial video around the twin cities."),
    ("4-Person Camping Tent", "camping", "Islamabad", "E-11", 1200, 6000,
     "Usman Tariq", 4.6, True,
     "Waterproof dome tent that sleeps four. Easy 10-minute setup — tested on trips to Nathia Gali."),
    ("Coleman Sleeping Bag Set (x2)", "camping", "Islamabad", "DHA Phase 2", 500, 2000,
     "Ayesha Noor", 4.4, False,
     "Pair of warm 3-season sleeping bags, freshly cleaned. Rated comfortable down to 5°C."),
    ("PlayStation 5 + 2 Controllers", "gaming", "Islamabad", "Gulberg Greens", 1500, 25000,
     "Fahad Iqbal", 4.9, True,
     "PS5 disc edition with two DualSense controllers and FIFA + Spider-Man. Great for weekend tournaments."),
    ("Xbox Series X Console", "gaming", "Rawalpindi", "Chaklala Scheme 3", 1400, 24000,
     "Zain Ali", 4.6, True,
     "Xbox Series X with wireless controller and Game Pass installed. 1TB storage, like new."),
    ("Party Sound System + Speakers", "events", "Islamabad", "G-11", 5000, 15000,
     "Imran Yousaf", 4.5, True,
     "1000W PA system with two speakers, a mixer and two wireless mics. Covers birthdays and small events."),
    ("Wedding Sherwani (Maroon)", "formal-wear", "Rawalpindi", "Saddar", 2500, 10000,
     "Danish Aziz", 4.7, False,
     "Elegant maroon sherwani, size L, with matching khussa and turban. Dry-cleaned after every rental."),
    ("Designer Bridal Lehenga", "formal-wear", "Islamabad", "F-10", 6000, 30000,
     "Mahnoor Sattar", 4.8, True,
     "Hand-embroidered bridal lehenga in deep red, size M. A fraction of the price of buying one."),
]

# --- Real cover photos (Unsplash CDN, no API key needed) --------------------
# One hand-picked photo id per listing title — matched to the specific item, not
# just its category, so e.g. the Canon kit gets a Canon body, not a random camera.
UNSPLASH_PHOTO_IDS = {
    "Bosch Hammer Drill (Corded)": "1572981779307-38b8cabb2407",
    "Makita Angle Grinder 4\"": "1522322512347-a0e57fd1744c",
    "Canon EOS R6 Mirrorless Kit": "1495707902641-75cac588d2e9",
    "DJI Mavic Air 2 Drone": "1521405924368-64c5b84bec60",
    "4-Person Camping Tent": "1504280390367-361c6d9f38f4",
    "Coleman Sleeping Bag Set (x2)": "1558477280-1bfed08ea5db",
    "PlayStation 5 + 2 Controllers": "1622297845775-5ff3fef71d13",
    "Xbox Series X Console": "1621259182978-fbf93132d53d",
    "Party Sound System + Speakers": "1724858103797-6d388eb1006a",
    "Wedding Sherwani (Maroon)": "1618886614638-80e3c103d31a",
    "Designer Bridal Lehenga": "1610047614301-13c63f00c032",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


def _placeholder_svg(title: str, category: str, c1: str, c2: str) -> bytes:
    """Build a simple category-coloured SVG placeholder with the item's title."""
    # Escape the few characters that matter inside SVG text.
    safe_title = (title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    safe_cat = category.upper()
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='800' height='600' viewBox='0 0 800 600'>
  <defs>
    <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0' stop-color='{c1}'/>
      <stop offset='1' stop-color='{c2}'/>
    </linearGradient>
  </defs>
  <rect width='800' height='600' fill='url(#g)'/>
  <text x='400' y='300' font-family='Segoe UI, Arial, sans-serif' font-size='42'
        fill='#ffffff' text-anchor='middle' font-weight='700'>{safe_title}</text>
  <text x='400' y='350' font-family='Segoe UI, Arial, sans-serif' font-size='22'
        fill='#ffffff' fill-opacity='0.75' text-anchor='middle'
        letter-spacing='3'>{safe_cat}</text>
</svg>"""
    return svg.encode("utf-8")


def _fetch_unsplash_photo(photo_id: str) -> bytes | None:
    """Download an Unsplash CDN photo. Returns ``None`` on any failure.

    ``images.unsplash.com`` serves direct photo fetches with no API key; a
    ``User-Agent`` is set because the CDN 403s the default urllib one.
    """
    url = f"https://images.unsplash.com/photo-{photo_id}?w=800&q=80&fit=crop&auto=format"
    req = urllib.request.Request(url, headers={"User-Agent": "circlo-seed/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _owner_email(name: str) -> str:
    """Derive a stable demo email from an owner's display name."""
    return f"{_slugify(name).replace('-', '.')}@{SEED_EMAIL_DOMAIN}"


def _wipe() -> None:
    """Remove existing rows so the seed is repeatable (children first).

    Only the demo owners (``@demo.circlo.pk``) are removed, so wiping never touches
    real accounts created through signup. Their listings cascade-delete with them.
    """
    ListingImage.query.delete()
    Listing.query.delete()
    Category.query.delete()
    User.query.filter(User.email.like(f"%@{SEED_EMAIL_DOMAIN}")).delete(
        synchronize_session=False
    )
    db.session.commit()


def seed_all() -> dict[str, int]:
    """(Re)create demo owners + categories + listings and upload a placeholder each.

    Each distinct owner in :data:`LISTINGS` becomes a real ``User`` (so the M1 FK
    is exercised), carrying the M2 rating and verified flag. Returns a small summary
    dict for the CLI to print.
    """
    storage.ensure_buckets()
    _wipe()

    # Standardized Islamabad/Rawalpindi areas — the fixed location vocabulary
    # every listing's area must belong to (see app/services/areas.py).
    areas_service.sync_areas()

    cats: dict[str, Category] = {}
    colors: dict[str, tuple[str, str]] = {}
    for name, slug, c1, c2 in CATEGORIES:
        cat = Category(name=name, slug=slug)
        db.session.add(cat)
        cats[slug] = cat
        colors[slug] = (c1, c2)

    # One demo user per distinct owner name; verified owners are "approved" so the
    # Verified badge (now derived from User.verification_status) still shows.
    owners: dict[str, User] = {}
    for (_t, _c, _city, _a, _p, _d, owner_name, rating, verified, _desc) in LISTINGS:
        if owner_name in owners:
            continue
        user = User(
            name=owner_name,
            email=_owner_email(owner_name),
            rating=rating,
            verification_status="approved" if verified else "pending",
        )
        user.set_password(SEED_PASSWORD)
        db.session.add(user)
        owners[owner_name] = user

    db.session.flush()  # assign category + user ids

    image_count = 0
    for (title, cat_slug, _seed_city, area, price, deposit,
         owner_name, _rating, _verified, description) in LISTINGS:
        # Area must be a standardized value; city is derived from it so the two
        # never drift (matches the listing-form / service behaviour).
        area = areas_service.closest_area(area)
        listing = Listing(
            title=title,
            description=description,
            category_id=cats[cat_slug].id,
            city=areas_service.city_for_area(area),
            area=area,
            price_per_day=price,
            deposit_amount=deposit,
            owner_id=owners[owner_name].id,
            status="active",
        )
        db.session.add(listing)

        # Real photo → download from Unsplash → upload through the storage
        # service, storing only the key. Falls back to the SVG placeholder if
        # the fetch fails (offline dev box, Unsplash hiccup) so seeding never
        # hard-fails on a network blip.
        photo_id = UNSPLASH_PHOTO_IDS.get(title)
        photo_bytes = _fetch_unsplash_photo(photo_id) if photo_id else None

        if photo_bytes:
            key = f"listings/{_slugify(title)}/cover.jpg"
            storage.upload_fileobj(
                io.BytesIO(photo_bytes), key, content_type="image/jpeg"
            )
        else:
            c1, c2 = colors[cat_slug]
            key = f"listings/{_slugify(title)}/cover.svg"
            svg_bytes = _placeholder_svg(title, cats[cat_slug].name, c1, c2)
            storage.upload_fileobj(
                io.BytesIO(svg_bytes), key, content_type="image/svg+xml"
            )
        listing.images.append(ListingImage(object_key=key, sort_order=0))
        image_count += 1

    db.session.commit()

    return {
        "owners": len(owners),
        "categories": len(cats),
        "listings": len(LISTINGS),
        "images": image_count,
    }
