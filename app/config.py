"""Configuration layer for CIRCLO.

Every environment-specific value (secret key, database DSN, S3/MinIO endpoint
and keys) is read from environment variables. Nothing is hard-coded. A real
``.env`` is loaded in development via python-dotenv; in production the platform
injects the same variables.

Select the active config with the ``APP_ENV`` env var: ``development`` (default)
or ``production``.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env once, at import time. In production the file may be absent and the
# platform provides the vars directly — load_dotenv() is a no-op then.
load_dotenv()


def _env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def _bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Base config — shared defaults, all values sourced from env vars."""

    # --- Core Flask ---
    SECRET_KEY = _env("SECRET_KEY", "dev-insecure-change-me")

    # --- Database (SQLAlchemy) ---
    SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Object storage (S3-compatible: MinIO local, R2/S3 deployed) ---
    STORAGE_ENDPOINT_URL = _env("STORAGE_ENDPOINT_URL")      # e.g. http://minio:9000
    STORAGE_PUBLIC_URL = _env("STORAGE_PUBLIC_URL")          # browser-facing base, optional
    STORAGE_REGION = _env("STORAGE_REGION", "us-east-1")
    STORAGE_ACCESS_KEY = _env("STORAGE_ACCESS_KEY")
    STORAGE_SECRET_KEY = _env("STORAGE_SECRET_KEY")
    STORAGE_BUCKET = _env("STORAGE_BUCKET", "circlo")
    STORAGE_BUCKET_PRIVATE = _env("STORAGE_BUCKET_PRIVATE", "circlo-private")
    STORAGE_PRESIGN_EXPIRY = int(_env("STORAGE_PRESIGN_EXPIRY", "3600"))
    # MinIO needs path-style addressing; real S3 accepts it too.
    STORAGE_USE_PATH_STYLE = _bool("STORAGE_USE_PATH_STYLE", True)

    # --- Email (Brevo transactional API, over HTTPS) ---
    # Transactional email only (password reset, notifications). No SMS/OTP — that
    # has a per-message cost and is deferred (blueprint §13).
    # We use Brevo's REST API on port 443, NOT SMTP: outbound SMTP (587/465) is
    # blocked on both the dev network and Render. BREVO_API_KEY is a v3 API key
    # from the Brevo dashboard (SMTP & API -> API Keys) — a different credential
    # from the old SMTP key. If the key or from-address is unset the email
    # service logs an error and returns False, so dev/tests never deliver.
    BREVO_API_KEY = _env("BREVO_API_KEY")
    BREVO_API_URL = _env("BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")
    MAIL_FROM_ADDRESS = _env("MAIL_FROM_ADDRESS")
    MAIL_FROM_NAME = _env("MAIL_FROM_NAME", "CIRCLO")
    # Base URL for links inside emails (password reset, etc.). No trailing slash.
    PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "http://localhost:5000")

    # Logging verbosity for app.logger (INFO surfaces best-effort email diagnostics).
    LOG_LEVEL = _env("LOG_LEVEL", "INFO")

    # --- Google OAuth2 / OpenID Connect ("Sign in with Google") ---
    # Client ID + secret come from a Google Cloud OAuth 2.0 "Web application"
    # credential. Leave both blank to hide the Google button and disable the
    # routes — email/password auth is unaffected. The discovery URL is Google's
    # well-known OIDC metadata endpoint; only override it for testing.
    GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = _env("GOOGLE_CLIENT_SECRET")
    GOOGLE_DISCOVERY_URL = _env(
        "GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )

    # --- Admin-configurable operational settings: env-var *fallbacks* only ---
    # The live values are edited from /admin/settings and stored in the DB
    # (app_settings). These provide sensible defaults for a fresh deploy before
    # anyone opens that page. See app/services/settings.py.
    PAYMENT_EASYPAISA_NUMBER = _env("PAYMENT_EASYPAISA_NUMBER")
    PAYMENT_EASYPAISA_NAME = _env("PAYMENT_EASYPAISA_NAME")
    PAYMENT_BANK_NAME = _env("PAYMENT_BANK_NAME")
    PAYMENT_BANK_TITLE = _env("PAYMENT_BANK_TITLE")
    PAYMENT_BANK_ACCOUNT = _env("PAYMENT_BANK_ACCOUNT")
    PAYMENT_BANK_IBAN = _env("PAYMENT_BANK_IBAN")
    PAYMENT_INSTRUCTIONS_NOTE = _env("PAYMENT_INSTRUCTIONS_NOTE")

    DEBUG = False
    TESTING = False


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False

    def __init__(self) -> None:
        # Fail fast in production if critical secrets were not provided.
        missing = [
            name
            for name in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI")
            if not getattr(self, name)
            or getattr(self, name) == "dev-insecure-change-me"
        ]
        if missing:
            raise RuntimeError(
                f"Missing required production config: {', '.join(missing)}"
            )


_CONFIGS = {
    "development": DevConfig,
    "production": ProdConfig,
}


def get_config():
    """Return the Config class/instance selected by APP_ENV."""
    env = _env("APP_ENV", "development").strip().lower()
    config_cls = _CONFIGS.get(env, DevConfig)
    # ProdConfig validates in __init__, so instantiate it; Dev can stay a class.
    return config_cls() if config_cls is ProdConfig else config_cls
