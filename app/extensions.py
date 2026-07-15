"""Flask extension singletons.

Instantiated here (unbound) and initialised against the app inside the
application factory. Import these anywhere without causing circular imports.
"""
from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# Where to redirect anonymous users hitting a login-required view (wired in M1).
login_manager.login_view = "web.index"


@login_manager.user_loader
def load_user(user_id):
    """Resolve a session user id to a User object.

    M0 has no User model yet, so no one is ever authenticated. Flask-Login still
    requires this callback to be registered (its template context processor calls
    it on every render). M1 (Auth) replaces the body with a real lookup.
    """
    return None
