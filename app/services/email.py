"""Email service — a single ``send_email`` over Brevo's transactional REST API.

Transactional email only (password reset, event notifications). SMS/phone OTP is
deferred (per-message cost — blueprint §13).

**Why the API and not SMTP:** outbound SMTP submission ports (587/465) are
blocked on both the dev network and Render, so ``smtplib`` just times out.
Brevo's REST API (``POST https://api.brevo.com/v3/smtp/email``) runs on 443,
which is open. It authenticates with a ``BREVO_API_KEY`` header — a v3 API key
from the Brevo dashboard, distinct from the old SMTP key.

Everything comes from config/env (blueprint §9): ``BREVO_API_KEY``,
``BREVO_API_URL``, ``MAIL_FROM_ADDRESS``, ``MAIL_FROM_NAME``. If the key or the
from-address is unset, the service logs an error and returns ``False`` instead
of sending, so dev and tests never deliver real mail.

Uses ``urllib`` from the stdlib — no new dependency (blueprint: ask before
adding deps).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from flask import current_app

_REQUIRED_KEYS = ("BREVO_API_KEY", "MAIL_FROM_ADDRESS")


def missing_config() -> list[str]:
    """Names of the required email config vars that are unset/empty."""
    cfg = current_app.config
    return [k for k in _REQUIRED_KEYS if not cfg.get(k)]


def is_configured() -> bool:
    return not missing_config()


def _html_to_text(html: str) -> str:
    """Very small fallback plain-text body (strip tags, collapse whitespace)."""
    import re

    text = re.sub(r"<(br|/p|/div|/h[1-6])\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def send_email(to: str, subject: str, body_html: str, raise_on_error: bool = False) -> bool:
    """Send one HTML email via the Brevo API. Returns True if Brevo accepted it.

    Never raises for an unconfigured relay or a delivery error (unless
    ``raise_on_error`` is set — used by the debug route) — callers treat email as
    best-effort so a mail outage can't break signup/booking flows.
    """
    cfg = current_app.config

    if not to:
        current_app.logger.warning("send_email: no recipient, skipping (%s)", subject)
        if raise_on_error:
            raise ValueError("no recipient")
        return False

    missing = missing_config()
    if missing:
        current_app.logger.error(
            "send_email SKIPPED: Brevo API not configured — missing env vars: %s "
            "(-> %s | %s)",
            ", ".join(missing), to, subject,
        )
        if raise_on_error:
            raise RuntimeError(f"Brevo API not configured — missing: {', '.join(missing)}")
        return False

    api_url = cfg.get("BREVO_API_URL") or "https://api.brevo.com/v3/smtp/email"
    sender_email = cfg["MAIL_FROM_ADDRESS"]
    sender_name = cfg.get("MAIL_FROM_NAME") or "CIRCLO"

    current_app.logger.info(
        "send_email: attempting delivery -> %s | %s | via Brevo API (%s) as %s <%s>",
        to, subject, api_url, sender_name, sender_email,
    )

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": body_html,
        "textContent": _html_to_text(body_html),
    }
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "api-key": cfg["BREVO_API_KEY"],
            "content-type": "application/json",
            "accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            raw = resp.read().decode("utf-8", "replace")
        message_id = ""
        try:
            message_id = (json.loads(raw) or {}).get("messageId", "")
        except ValueError:
            pass
        current_app.logger.info(
            "send_email OK -> %s | %s | messageId=%s", to, subject, message_id or "(none)",
        )
        return True
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        current_app.logger.error(
            "send_email FAILED -> %s | %s | Brevo API HTTP %s %s: %s",
            to, subject, exc.code, exc.reason, detail or "(no body)",
        )
        if raise_on_error:
            raise RuntimeError(
                f"Brevo API HTTP {exc.code} {exc.reason}: {detail or '(no body)'}"
            ) from exc
        return False
    except Exception as exc:  # noqa: BLE001 - email is best-effort, log and move on
        current_app.logger.error(
            "send_email FAILED -> %s | %s | %s: %s",
            to, subject, type(exc).__name__, exc, exc_info=True,
        )
        if raise_on_error:
            raise
        return False
