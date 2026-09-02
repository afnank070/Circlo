"""Email service — a single ``send_email`` over Brevo's SMTP relay.

Transactional email only (password reset, event notifications). SMS/phone OTP is
deferred (per-message cost — blueprint §13).

Everything comes from config/env (blueprint §9): ``BREVO_SMTP_SERVER``,
``BREVO_SMTP_PORT``, ``BREVO_SMTP_LOGIN``, ``BREVO_SMTP_KEY``,
``MAIL_FROM_ADDRESS``, ``MAIL_FROM_NAME``. If login/key/from aren't configured
the service logs the message and returns ``False`` instead of sending, so dev
and tests never deliver real mail.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app


_REQUIRED_KEYS = ("BREVO_SMTP_LOGIN", "BREVO_SMTP_KEY", "MAIL_FROM_ADDRESS")


def missing_config() -> list[str]:
    """Names of the required SMTP config vars that are unset/empty."""
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
    """Send one HTML email. Returns True if handed to the relay, False otherwise.

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
            "send_email SKIPPED: SMTP relay not configured — missing env vars: %s "
            "(-> %s | %s)",
            ", ".join(missing), to, subject,
        )
        if raise_on_error:
            raise RuntimeError(f"SMTP relay not configured — missing: {', '.join(missing)}")
        return False

    server = cfg.get("BREVO_SMTP_SERVER", "smtp-relay.brevo.com")
    port = int(cfg.get("BREVO_SMTP_PORT", 587))
    current_app.logger.info(
        "send_email: attempting delivery -> %s | %s | via %s:%s as %s",
        to, subject, server, port, cfg.get("BREVO_SMTP_LOGIN"),
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.get("MAIL_FROM_NAME") or "CIRCLO", cfg["MAIL_FROM_ADDRESS"]))
    msg["To"] = to
    msg.set_content(_html_to_text(body_html))
    msg.add_alternative(body_html, subtype="html")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(server, port, timeout=15,
                                  context=ssl.create_default_context()) as s:
                s.login(cfg["BREVO_SMTP_LOGIN"], cfg["BREVO_SMTP_KEY"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(server, port, timeout=15) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
                s.login(cfg["BREVO_SMTP_LOGIN"], cfg["BREVO_SMTP_KEY"])
                s.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - email is best-effort, log and move on
        current_app.logger.error(
            "send_email FAILED -> %s | %s | %s: %s",
            to, subject, type(exc).__name__, exc, exc_info=True,
        )
        if raise_on_error:
            raise
        return False

    current_app.logger.info("send_email OK -> %s | %s", to, subject)
    return True
