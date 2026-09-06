"""Application factory for CIRCLO.

Everything is wired here so that both the web UI and the future ``/api/v1``
share one configured app instance. Nothing environment-specific lives in this
file — configuration is loaded from a ``Config`` class that reads env vars.
"""
from __future__ import annotations

import logging
import os

from flask import Flask

from .config import get_config
from .extensions import db, migrate, login_manager, oauth


def create_app(config_object=None) -> Flask:
    """Build and configure a Flask app.

    :param config_object: optional Config class/instance (used by tests).
                          Defaults to the one selected by ``APP_ENV``.
    """
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_models()
    _register_cli(app)
    _register_context_processors(app)

    return app


def _configure_logging(app: Flask) -> None:
    """Make ``app.logger`` output actually reach the platform log stream.

    Without this, under Gunicorn the Flask logger's effective level is WARNING,
    so every ``app.logger.info(...)`` is silently dropped on Render — which hides
    best-effort email diagnostics. We bind the app logger to Gunicorn's handlers
    (Render captures those) when running under Gunicorn, otherwise add a plain
    stream handler, and set the level from ``LOG_LEVEL`` (default INFO).
    """
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    gunicorn_logger = logging.getLogger("gunicorn.error")
    if gunicorn_logger.handlers:  # running under Gunicorn (Render, prod)
        app.logger.handlers = gunicorn_logger.handlers
    elif not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        ))
        app.logger.addHandler(handler)

    app.logger.setLevel(level)
    app.logger.propagate = False


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    _init_oauth(app)


def _init_oauth(app: Flask) -> None:
    """Wire the OAuth registry and register Google only if it's configured.

    With no ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET`` the provider is not
    registered: ``oauth.create_client("google")`` returns ``None`` and the web
    routes flash a friendly "not available" message. Email/password auth is
    unaffected either way.
    """
    oauth.init_app(app)

    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url=app.config["GOOGLE_DISCOVERY_URL"],
            client_kwargs={"scope": "openid email profile"},
        )


def _register_blueprints(app: Flask) -> None:
    # Web UI (Jinja + HTMX). The API blueprint lands in a later milestone.
    from .web import web_bp
    from .admin import admin_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)


def _register_models() -> None:
    """Import models so Alembic autogenerate can see them.

    Kept as a single import point; M1+ models get added under app/models/.
    """
    from . import models  # noqa: F401


def _register_cli(app: Flask) -> None:
    """Register custom ``flask`` CLI commands (e.g. ``flask seed``)."""
    from .cli import register_cli

    register_cli(app)


def _register_context_processors(app: Flask) -> None:
    """Template globals shared by every blueprint (web + admin), e.g. base.html's nav."""
    from flask_login import current_user

    from .services import booking as booking_service

    @app.context_processor
    def inject_pending_request_count() -> dict:
        if current_user.is_authenticated:
            return {"pending_request_count": booking_service.pending_count_for_owner(current_user)}
        return {"pending_request_count": 0}

    @app.context_processor
    def inject_google_oauth_enabled() -> dict:
        """Templates show the "Sign in with Google" button only when configured."""
        return {
            "google_oauth_enabled": bool(
                app.config.get("GOOGLE_CLIENT_ID")
                and app.config.get("GOOGLE_CLIENT_SECRET")
            )
        }

    @app.context_processor
    def inject_areas() -> dict:
        """Standardized Islamabad/Rawalpindi areas for the listing form + browse
        filter dropdowns (never free text — see app/services/areas.py)."""
        from .services import areas as areas_service

        return {"areas_by_city": areas_service.areas_by_city()}

    @app.context_processor
    def inject_current_year() -> dict:
        """Footer copyright line — computed server-side, never hardcoded."""
        from datetime import date

        return {"current_year": date.today().year}
