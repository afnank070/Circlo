"""Flask extension singletons.

Instantiated here (unbound) and initialised against the app inside the
application factory. Import these anywhere without causing circular imports.
"""
from __future__ import annotations

from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# OAuth registry ("Sign in with Google"). Providers are registered in the app
# factory only when their credentials are configured — see app/__init__.py.
oauth = OAuth()

# Where to redirect anonymous users hitting a login-required view.
login_manager.login_view = "web.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    """Resolve a session user id to a User object (blueprint §5).

    Delegates to the auth service so the lookup logic lives in one place. Imported
    lazily to avoid a circular import at module load (models import ``db`` from
    here).
    """
    from app.services import auth

    return auth.get_user(user_id)
