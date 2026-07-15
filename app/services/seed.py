"""Seed service — populate the marketplace with realistic demo data.

Inserts the fixed category set and ~10 Islamabad/Rawalpindi listings, and pushes a
placeholder image for each through the existing storage service so the whole image
pipeline (upload → stored key → runtime presigned URL) is exercised end-to-end.

Placeholders are generated as SVGs so the seed needs no image files on disk and no
extra dependencies (Pillow etc.). The point is to prove the pipeline, not the art.

Idempotent: object keys are derived from a slug, and the DB rows are wiped and
re-inserted on every run, so ``flask seed`` can be run repeatedly.
"""
from __future__ import annotations

import io
import re

from app.extensions import db
from app.models import Category, Listing, ListingImage
from app.services import storage

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


def _wipe() -> None:
    """Remove existing rows so the seed is repeatable (children first)."""
    ListingImage.query.delete()
    Listing.query.delete()
    Category.query.delete()
    db.session.commit()


def seed_all() -> dict[str, int]:
    """(Re)create categories + listings and upload a placeholder image each.

    Returns a small summary dict for the CLI to print.
    """
    storage.ensure_buckets()
    _wipe()

    cats: dict[str, Category] = {}
    colors: dict[str, tuple[str, str]] = {}
    for name, slug, c1, c2 in CATEGORIES:
        cat = Category(name=name, slug=slug)
        db.session.add(cat)
        cats[slug] = cat
        colors[slug] = (c1, c2)
    db.session.flush()  # assign category ids

    image_count = 0
    for (title, cat_slug, city, area, price, deposit,
         owner, rating, verified, description) in LISTINGS:
        listing = Listing(
            title=title,
            description=description,
            category_id=cats[cat_slug].id,
            city=city,
            area=area,
            price_per_day=price,
            deposit_amount=deposit,
            owner_name=owner,
            owner_rating=rating,
            is_verified=verified,
            status="active",
        )
        db.session.add(listing)

        # Upload the placeholder through the storage service and store only the key.
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
        "categories": len(cats),
        "listings": len(LISTINGS),
        "images": image_count,
    }
