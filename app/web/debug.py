"""Temporary operational debug endpoints.

Only ``GET /debug/test-email`` for now: a direct email smoke test for deploy
targets with no shell access (Render free tier), so we can't run
``flask send-test-email`` there. It is gated behind the ``DEBUG_EMAIL_KEY`` env
var — if that is unset, or the ``key`` query param doesn't match, the route 404s
so it isn't discoverable or abusable. Remove this module (and the blueprint
import in ``app/web/__init__.py``) once the mail path is confirmed working.
"""
from __future__ import annotations

import hmac
import traceback

from flask import Response, abort, current_app, request

from app.services import email as email_service

from . import web_bp


@web_bp.route("/debug/test-email")
def debug_test_email() -> Response:
    expected = current_app.config.get("DEBUG_EMAIL_KEY")
    provided = request.args.get("key", "")
    if not expected or not hmac.compare_digest(str(expected), provided):
        abort(404)

    recipient = (
        request.args.get("to")
        or current_app.config.get("DEBUG_EMAIL_RECIPIENT")
        or current_app.config.get("MAIL_FROM_ADDRESS")
        or ""
    )

    missing = email_service.missing_config()
    api_key = current_app.config.get("BREVO_API_KEY") or ""
    lines = [
        "CIRCLO /debug/test-email",
        f"recipient      : {recipient or '(none resolved)'}",
        f"brevo api url  : {current_app.config.get('BREVO_API_URL')}",
        f"brevo api key  : {'set (' + str(len(api_key)) + ' chars)' if api_key else '(unset)'}",
        f"from name      : {current_app.config.get('MAIL_FROM_NAME') or '(unset)'}",
        f"from address   : {current_app.config.get('MAIL_FROM_ADDRESS') or '(unset)'}",
        f"missing config : {', '.join(missing) if missing else '(none)'}",
        "",
    ]

    if not recipient:
        lines.append("RESULT: ERROR — no recipient (set DEBUG_EMAIL_RECIPIENT or pass ?to=)")
        return Response("\n".join(lines), status=400, mimetype="text/plain")

    try:
        ok = email_service.send_email(
            recipient,
            "CIRCLO email debug test",
            "<p>This is a direct <strong>/debug/test-email</strong> call. "
            "If you received it, Brevo API delivery works.</p>",
            raise_on_error=True,
        )
        lines.append(f"RESULT: {'SUCCESS — accepted by Brevo' if ok else 'FALSE — see logs'}")
        status = 200 if ok else 500
    except Exception as exc:  # noqa: BLE001 - surface the full reason in the response
        current_app.logger.exception("/debug/test-email send failed")
        lines.append(f"RESULT: EXCEPTION — {type(exc).__name__}: {exc}")
        lines.append("")
        lines.append(traceback.format_exc())
        status = 500

    return Response("\n".join(lines), status=status, mimetype="text/plain")
