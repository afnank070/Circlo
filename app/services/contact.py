"""Contact-form service — route a visitor's message to CIRCLO's human inbox.

The message is emailed to ``CONTACT_EMAIL`` (``contact@circlo.pk`` by default),
which is deliberately **not** ``MAIL_FROM_ADDRESS`` — that address
(``help@circlo.pk``) is only the *sender* of automated system mail (password
resets, booking notifications). Reuses the Brevo transactional email service.

All validation / spam handling lives here so ``/api/v1`` could reuse it.
"""
from __future__ import annotations

from html import escape

from flask import current_app

from app.services import email as email_service

# (value, label) — drives the form dropdown; value is what's stored/sent.
CATEGORIES: list[tuple[str, str]] = [
    ("general", "General question"),
    ("bug", "Report a bug"),
    ("booking", "Booking issue"),
    ("verification", "Verification issue"),
    ("other", "Other"),
]
_CATEGORY_LABELS = dict(CATEGORIES)
DEFAULT_CATEGORY = "general"


class ContactError(Exception):
    """Raised when the submitted contact form fails validation."""


def category_label(value: str | None) -> str:
    return _CATEGORY_LABELS.get(value or "", _CATEGORY_LABELS[DEFAULT_CATEGORY])


def normalize_category(value: str | None) -> str:
    return value if value in _CATEGORY_LABELS else DEFAULT_CATEGORY


def contact_inbox() -> str:
    return current_app.config.get("CONTACT_EMAIL") or "contact@circlo.pk"


def submit_contact_message(
    *, name: str, email: str, category: str, message: str, honeypot: str = ""
) -> bool:
    """Validate a contact-form submission and email it to :func:`contact_inbox`.

    :param honeypot: value of the hidden anti-bot field — if a bot filled it,
        the message is silently dropped and ``True`` is returned (so the bot
        can't tell it was rejected).
    :raises ContactError: on invalid name / email / message.
    :returns: whatever ``email_service.send_email`` returns (bots aside).
    """
    if (honeypot or "").strip():
        current_app.logger.info(
            "contact form: honeypot tripped — dropping message from %r", email
        )
        return True

    name = (name or "").strip()
    email = (email or "").strip()
    message = (message or "").strip()
    category = normalize_category(category)

    if not name:
        raise ContactError("Please enter your name.")
    if not email or "@" not in email:
        raise ContactError("Please enter a valid email address.")
    if len(message) < 10:
        raise ContactError("Please add a bit more detail to your message.")
    if len(message) > 5000:
        raise ContactError("That message is too long — please keep it under 5000 characters.")

    label = _CATEGORY_LABELS[category]
    subject = f"[Contact · {label}] {name}"
    body_html = (
        f"<p>New message from the CIRCLO contact form.</p>"
        f"<p><strong>Name:</strong> {escape(name)}<br>"
        f"<strong>Email:</strong> {escape(email)}<br>"
        f"<strong>Category:</strong> {escape(label)}</p>"
        f"<p><strong>Message:</strong></p>"
        f"<p style=\"white-space:pre-wrap\">{escape(message)}</p>"
        f"<hr><p style=\"color:#6d7973;font-size:12px\">"
        f"Reply directly to {escape(email)} to respond to this person.</p>"
    )
    return email_service.send_email(contact_inbox(), subject, body_html)
