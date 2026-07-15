"""Web UI blueprint (Jinja2 + HTMX + Tailwind)."""
from __future__ import annotations

from flask import Blueprint

web_bp = Blueprint(
    "web",
    __name__,
    template_folder="templates",
    static_folder="static",
)

from . import routes  # noqa: E402,F401  (register routes on import)
