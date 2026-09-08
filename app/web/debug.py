"""Temporary operational debug endpoint.

``GET /debug/reprice-listings?key=<DEBUG_REPRICE_KEY>`` — re-applies the seed
script's ``price_per_hour`` / ``deposit_amount`` values to any existing listing
rows with a matching title. It exists so a deploy with no shell access can
correct the listing prices left at ``0`` by the day→hour column swap, without
running ``flask seed``.

Gated behind the ``DEBUG_REPRICE_KEY`` env var — if that is unset, or the
``key`` query param doesn't match, the route 404s so it isn't discoverable or
abusable. All it can do is set prices/deposits to the values hard-coded in
``app/services/seed.py``; it never creates, deletes, or otherwise mutates rows.

Remove this module (and the ``from . import debug`` line in
``app/web/__init__.py``, the ``DEBUG_REPRICE_KEY`` config entry, and the
``.env.example`` / ``render.yaml`` lines) once production pricing is confirmed.
"""
from __future__ import annotations

import hmac

from flask import Response, abort, current_app, request

from app.services import seed as seed_service

from . import web_bp


@web_bp.route("/debug/reprice-listings")
def debug_reprice_listings() -> Response:
    expected = current_app.config.get("DEBUG_REPRICE_KEY")
    provided = request.args.get("key", "")
    if not expected or not hmac.compare_digest(str(expected), provided):
        abort(404)

    result = seed_service.seed_pricing()
    current_app.logger.warning(
        "/debug/reprice-listings ran: %d changed, %d unchanged, %d missing",
        len(result["changed"]), len(result["unchanged"]), len(result["missing_from_db"]),
    )

    lines = ["CIRCLO /debug/reprice-listings", ""]
    lines.append(f"CHANGED ({len(result['changed'])}):")
    lines += [f"  {c}" for c in result["changed"]] or ["  (none)"]
    lines.append("")
    lines.append(f"ALREADY CORRECT ({len(result['unchanged'])}):")
    lines += [f"  {u}" for u in result["unchanged"]] or ["  (none)"]
    lines.append("")
    lines.append(f"IN SEED BUT NOT IN DB ({len(result['missing_from_db'])}):")
    lines += [f"  {t}" for t in result["missing_from_db"]] or ["  (none)"]
    lines.append("")
    lines.append("Done. Remove this route once prices look right on the live site.")

    return Response("\n".join(lines), status=200, mimetype="text/plain")
