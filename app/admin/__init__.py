"""Admin panel blueprint — verify identities, moderate listings, resolve disputes.

Only identity verification is wired for now (M1 part 2). Login required + role
must be ``admin`` — enforced by :func:`admin_required` in every view.
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort
from flask_login import current_user, login_required

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",
)


def admin_required(view):
    """Require an authenticated user with ``role == 'admin'``, else 403."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


from . import verify  # noqa: E402,F401  (identity review queue)
from . import payments  # noqa: E402,F401  (semi-manual payment confirmation)
from . import settings  # noqa: E402,F401  (admin-configurable operational settings)
from . import disputes  # noqa: E402,F401  (dispute review queue)
from . import trust_fund  # noqa: E402,F401  (trust & safety fund bookkeeping)
