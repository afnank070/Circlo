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
