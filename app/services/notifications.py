"""Notification service — transactional emails for key CIRCLO events.

Each function builds a small HTML email and hands it to
:func:`app.services.email.send_email`. Every call is best-effort and never
raises (email service swallows errors), so a mail outage can't break the
verification / booking / payment flows that trigger these.

Wired from the service layer (verification, booking, payments) so ``/api/v1``
gets the same notifications for free.
"""
from __future__ import annotations

import functools

from flask import current_app, url_for

from app.services import email as email_service


def _base_url() -> str:
    return (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")


def _abs_url(endpoint: str, **values) -> str:
    """Absolute URL for an email link.

    Falls back to ``PUBLIC_BASE_URL`` if ``url_for`` can't build (e.g. called
    outside a request context) so a notification is never blocked by it.
    """
    try:
        path = url_for(endpoint, **values)
    except Exception:  # noqa: BLE001
        return _base_url() or "/"
    base = _base_url()
    return f"{base}{path}" if base else path


def _safe(fn):
    """Notifications are best-effort — never let one break the calling flow."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("notification %s failed", fn.__name__)
            return None
    return wrapped


def _send(to: str, subject: str, body_html: str) -> bool:
    return email_service.send_email(to, subject, body_html)


def _first_name(user) -> str:
    return user.name.split()[0] if user and user.name else "there"


# --- Identity verification -------------------------------------------------
@_safe
def verification_submitted(user) -> None:
    _send(
        user.email, "We've received your CIRCLO verification",
        f"<p>Hi {_first_name(user)},</p><p>Thanks — your CNIC and selfie are in "
        f"the review queue. We'll email you once an admin has checked them "
        f"(usually within a day).</p>",
    )


@_safe
def verification_approved(user) -> None:
    _send(
        user.email, "You're verified on CIRCLO ✅",
        f"<p>Hi {_first_name(user)},</p><p>Your identity is verified. You can now "
        f"list items and rent from others.</p>"
        f'<p><a href="{_abs_url("web.index")}">Start browsing</a></p>',
    )


@_safe
def verification_rejected(user, reason: str) -> None:
    _send(
        user.email, "Your CIRCLO verification needs another look",
        f"<p>Hi {_first_name(user)},</p><p>We couldn't verify your identity from "
        f"what was submitted:</p><blockquote>{reason}</blockquote>"
        f'<p>You can re-upload here: <a href="{_abs_url("web.verify")}">'
        f"{_abs_url('web.verify')}</a></p>",
    )


# --- Booking lifecycle ----------------------------------------------------
@_safe
def booking_requested(booking) -> None:
    """To the owner: a renter wants to book their item."""
    _send(
        booking.owner.email, f"New rental request: {booking.listing.title}",
        f"<p>Hi {_first_name(booking.owner)},</p><p><strong>{booking.renter.name}"
        f"</strong> requested to rent <strong>{booking.listing.title}</strong> "
        f"for {booking.rental_date_start:%d %b} – {booking.rental_date_end:%d %b %Y}.</p>"
        f'<p><a href="{_abs_url("web.my_rentals")}">Review the request</a></p>',
    )


@_safe
def booking_accepted(booking) -> None:
    _send(
        booking.renter.email, f"Your rental request was accepted: {booking.listing.title}",
        f"<p>Hi {_first_name(booking.renter)},</p><p><strong>{booking.owner.name}"
        f"</strong> accepted your request for <strong>{booking.listing.title}"
        f"</strong>. Next step: pay the rental + deposit so CIRCLO can hold it.</p>"
        f'<p><a href="{_abs_url("web.my_rentals")}">Go to My Rentals</a></p>',
    )


@_safe
def booking_rejected(booking) -> None:
    _send(
        booking.renter.email, f"Update on your rental request: {booking.listing.title}",
        f"<p>Hi {_first_name(booking.renter)},</p><p>Unfortunately "
        f"<strong>{booking.owner.name}</strong> couldn't accept your request for "
        f"<strong>{booking.listing.title}</strong> this time. Plenty more to "
        f"rent though —</p>"
        f'<p><a href="{_abs_url("web.index")}">keep browsing</a>.</p>',
    )


@_safe
def payment_confirmed(booking) -> None:
    _send(
        booking.renter.email, f"Payment confirmed: {booking.listing.title}",
        f"<p>Hi {_first_name(booking.renter)},</p><p>We've confirmed your rental "
        f"payment and deposit for <strong>{booking.listing.title}</strong>. "
        f"Upload your handover photos when you collect the item.</p>"
        f'<p><a href="{_abs_url("web.my_rentals")}">Open My Rentals</a></p>',
    )


@_safe
def booking_completed(booking) -> None:
    """To both parties, with a review prompt."""
    link = _abs_url("web.my_rentals")
    for user, other in (
        (booking.renter, booking.owner),
        (booking.owner, booking.renter),
    ):
        _send(
            user.email, f"Rental complete: {booking.listing.title}",
            f"<p>Hi {_first_name(user)},</p><p>Your rental of "
            f"<strong>{booking.listing.title}</strong> is complete"
            + (
                " and the deposit refund + payout are queued" if user is booking.owner
                else " and your deposit refund is queued"
            )
            + f".</p><p>Please leave <strong>{other.name}</strong> a review — it "
            f"keeps CIRCLO trustworthy for everyone.</p>"
            f'<p><a href="{link}">Leave a review</a></p>',
        )
