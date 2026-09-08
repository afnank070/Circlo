"""Admin user management — list members, grant/revoke the admin role.

All logic here (not in the route) so ``/api/v1`` could reuse it. Role changes
are deliberately simple: no invite flow, no audit table — just a role flip plus
a log line naming who did what to whom and when (blueprint: full audit trail is
a later concern).
"""
from __future__ import annotations

from datetime import datetime

from flask import current_app
from sqlalchemy import or_

from app.extensions import db
from app.models import User
from app.models.user import ROLE_ADMIN, ROLE_USER


class AdminUserError(Exception):
    """Base class for admin-user-management errors."""


class UserNotFound(AdminUserError):
    """The target user id doesn't exist."""


class CannotChangeOwnRole(AdminUserError):
    """An admin tried to revoke their own admin access (accidental-lockout guard)."""


class RoleUnchanged(AdminUserError):
    """The target is already in the requested role — nothing to do."""


def list_users(query: str | None = None) -> list[User]:
    """All users, optionally filtered by a name/email substring.

    Admins first, then by name — so the people with elevated access are always
    visible at the top of the list.
    """
    q = User.query
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    return q.order_by(
        (User.role == ROLE_ADMIN).desc(), User.name.asc(), User.id.asc()
    ).all()


def admin_count() -> int:
    return User.query.filter_by(role=ROLE_ADMIN).count()


def _log_role_change(actor: User, target: User, action: str) -> None:
    current_app.logger.info(
        "ADMIN ROLE CHANGE: %s (id=%s) %s %s (id=%s) at %s",
        actor.email, actor.id, action, target.email, target.id,
        datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )


def _get_target(user_id) -> User:
    target = db.session.get(User, _coerce_id(user_id))
    if target is None:
        raise UserNotFound(str(user_id))
    return target


def _coerce_id(user_id) -> int:
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise UserNotFound(str(user_id))


def promote_to_admin(actor: User, user_id) -> User:
    """Grant the admin role to ``user_id``.

    :raises UserNotFound: no such user.
    :raises RoleUnchanged: the user is already an admin.
    """
    target = _get_target(user_id)
    if target.role == ROLE_ADMIN:
        raise RoleUnchanged(f"{target.email} is already an admin.")
    target.role = ROLE_ADMIN
    db.session.commit()
    _log_role_change(actor, target, "promoted to admin")
    return target


def revoke_admin(actor: User, user_id) -> User:
    """Remove the admin role from ``user_id``.

    :raises UserNotFound: no such user.
    :raises CannotChangeOwnRole: ``actor`` is trying to demote themselves.
    :raises RoleUnchanged: the user isn't an admin.
    """
    target = _get_target(user_id)
    if target.id == actor.id:
        raise CannotChangeOwnRole(
            "You can't revoke your own admin access — ask another admin to do it."
        )
    if target.role != ROLE_ADMIN:
        raise RoleUnchanged(f"{target.email} isn't an admin.")
    target.role = ROLE_USER
    db.session.commit()
    _log_role_change(actor, target, "revoked admin from")
    return target
