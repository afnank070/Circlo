"""Web UI blueprint (Jinja2 + HTMX + Tailwind)."""
from __future__ import annotations

from flask import Blueprint

web_bp = Blueprint(
    "web",
    __name__,
    template_folder="templates",
    static_folder="static",
)

# Import route modules so their views register on the blueprint. Order doesn't
# matter — each just decorates web_bp.
from . import routes  # noqa: E402,F401  (browse/detail/health)
from . import auth  # noqa: E402,F401  (signup/login/logout)
from . import owner  # noqa: E402,F401  (owner listing CRUD)
from . import verify  # noqa: E402,F401  (identity verification)
from . import booking  # noqa: E402,F401  (rental request/accept/reject/cancel)
from . import community  # noqa: E402,F401  (profiles, reviews, dispute reporting)
