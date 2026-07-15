"""Application factory for CIRCLO.

Everything is wired here so that both the web UI and the future ``/api/v1``
share one configured app instance. Nothing environment-specific lives in this
file — configuration is loaded from a ``Config`` class that reads env vars.
"""
from __future__ import annotations

from flask import Flask

from .config import get_config
from .extensions import db, migrate, login_manager


def create_app(config_object=None) -> Flask:
    """Build and configure a Flask app.

    :param config_object: optional Config class/instance (used by tests).
                          Defaults to the one selected by ``APP_ENV``.
    """
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    _init_extensions(app)
    _register_blueprints(app)
    _register_models()
    _register_cli(app)

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)


def _register_blueprints(app: Flask) -> None:
    # Web UI (Jinja + HTMX). API and admin blueprints land in later milestones.
    from .web import web_bp

    app.register_blueprint(web_bp)


def _register_models() -> None:
    """Import models so Alembic autogenerate can see them.

    Kept as a single import point; M1+ models get added under app/models/.
    """
    from . import models  # noqa: F401


def _register_cli(app: Flask) -> None:
    """Register custom ``flask`` CLI commands (e.g. ``flask seed``)."""
    from .cli import register_cli

    register_cli(app)
