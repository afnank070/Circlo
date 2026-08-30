"""SQLAlchemy models package.

M0 defines no domain tables yet — the models layer is scaffolded so that
Alembic autogenerate has a single import point. Real models (User,
IdentityDocument, Listing, Booking, ...) land from M1 onward per blueprint §5.

To add a model: create ``app/models/<name>.py`` and import it below so that
``flask db migrate`` can detect it.
"""
from __future__ import annotations

# M1 — Auth & Identity.
from .user import User  # noqa: F401
from .identity_document import IdentityDocument  # noqa: F401

# M2 — Listings & Search.
from .category import Category  # noqa: F401
from .listing import Listing  # noqa: F401
from .listing_image import ListingImage  # noqa: F401

# M3 — Booking core.
from .booking import Booking  # noqa: F401

# M4 — Money & Evidence.
from .ledger_entry import LedgerEntry  # noqa: F401
from .evidence_media import EvidenceMedia  # noqa: F401
from .app_setting import AppSetting  # noqa: F401

# M5 — Trust & Polish.
from .password_reset_token import PasswordResetToken  # noqa: F401
from .review import Review  # noqa: F401
from .dispute import Dispute  # noqa: F401

__all__ = [
    "User",
    "IdentityDocument",
    "Category",
    "Listing",
    "ListingImage",
    "Booking",
    "LedgerEntry",
    "EvidenceMedia",
    "AppSetting",
    "PasswordResetToken",
    "Review",
    "Dispute",
]
