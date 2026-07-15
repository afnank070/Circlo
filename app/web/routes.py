"""Web routes for M0 — home page + health check.

Product features (auth, listings, booking) arrive in later milestones. Internal
links must use ``url_for`` (blueprint §9).
"""
from __future__ import annotations

from flask import jsonify, render_template

from . import web_bp


@web_bp.route("/")
def index():
    return render_template("index.html")


@web_bp.route("/health")
def health():
    """Liveness probe consumed by Docker/monitoring. Returns JSON."""
    return jsonify(status="ok")
