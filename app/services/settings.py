"""Settings service — read/write admin-configurable operational settings.

Values live in the ``app_settings`` table so an admin can change them from the
panel with no redeploy. Each known key has an env-var fallback (so a fresh
deploy has sensible values before anyone opens the settings page) and a
human label for the form. All logic here so ``/api/v1`` / templates never touch
the model directly.
"""
from __future__ import annotations

from flask import current_app

from app.extensions import db
from app.models import AppSetting

# key -> (label, Config-key fallback, form input type). The Config key is sourced
# from an env var (see app/config.py) so the anti-hard-code rule (blueprint §9)
# still holds; the DB value, edited from /admin/settings, overrides it.
PAYMENT_SETTINGS: dict[str, tuple[str, str, str]] = {
    "payment_easypaisa_number": ("EasyPaisa number", "PAYMENT_EASYPAISA_NUMBER", "text"),
    "payment_easypaisa_name": ("EasyPaisa account name", "PAYMENT_EASYPAISA_NAME", "text"),
    "payment_bank_name": ("Bank name", "PAYMENT_BANK_NAME", "text"),
    "payment_bank_title": ("Bank account title", "PAYMENT_BANK_TITLE", "text"),
    "payment_bank_account": ("Bank account number", "PAYMENT_BANK_ACCOUNT", "text"),
    "payment_bank_iban": ("Bank IBAN", "PAYMENT_BANK_IBAN", "text"),
    "payment_instructions_note": (
        "Extra note shown to renters", "PAYMENT_INSTRUCTIONS_NOTE", "textarea"
    ),
}

KNOWN_SETTINGS = PAYMENT_SETTINGS


def get(key: str, default: str = "") -> str:
    """Value for ``key``: DB override if set, else the env-var fallback, else ``default``."""
    row = db.session.get(AppSetting, key)
    if row is not None and (row.value or "").strip():
        return row.value.strip()
    config_key = KNOWN_SETTINGS.get(key, (None, None, None))[1]
    if config_key:
        fallback = current_app.config.get(config_key)
        if fallback and str(fallback).strip():
            return str(fallback).strip()
    return default


def get_many(keys) -> dict[str, str]:
    return {k: get(k) for k in keys}


def set_value(key: str, value: str, *, admin) -> AppSetting:
    row = db.session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key)
        db.session.add(row)
    row.value = (value or "").strip()
    row.updated_by = admin.id
    db.session.commit()
    return row


def set_many(values: dict[str, str], *, admin) -> None:
    for key in KNOWN_SETTINGS:
        if key in values:
            set_value(key, values[key], admin=admin)


def payment_details() -> dict[str, str]:
    """The CIRCLO payment-collection details shown on a booking's payment card."""
    return get_many(PAYMENT_SETTINGS.keys())


def has_payment_details() -> bool:
    d = payment_details()
    return bool(
        d.get("payment_easypaisa_number")
        or d.get("payment_bank_account")
        or d.get("payment_bank_iban")
    )
