"""Admin settings — edit admin-configurable operational values + manage admins.

- CIRCLO payment-collection details (EasyPaisa / bank account) shown to renters
  on the payment step. Backed by ``services.settings`` so the values are
  DB-stored and editable without a redeploy.
- User management: list members and grant/revoke the admin role. Backed by
  ``services.admin_users``.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.services import admin_users as admin_users_service
from app.services import settings as settings_service

from . import admin_bp, admin_required


@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings_page():
    if request.method == "POST":
        settings_service.set_many(
            {k: request.form.get(k, "") for k in settings_service.PAYMENT_SETTINGS},
            admin=current_user,
        )
        flash("Payment details saved.", "success")
        return redirect(url_for("admin.settings_page"))

    user_query = (request.args.get("q") or "").strip()
    return render_template(
        "settings.html",
        payment_fields=settings_service.PAYMENT_SETTINGS,
        values=settings_service.get_many(settings_service.PAYMENT_SETTINGS.keys()),
        users=admin_users_service.list_users(user_query),
        user_query=user_query,
        admin_count=admin_users_service.admin_count(),
    )


def _back_to_settings():
    """Redirect back to the settings page, preserving the user search box."""
    q = (request.form.get("q") or "").strip()
    return redirect(url_for("admin.settings_page", q=q or None) + "#users")


@admin_bp.route("/users/<int:user_id>/promote", methods=["POST"])
@admin_required
def promote_user(user_id: int):
    try:
        target = admin_users_service.promote_to_admin(current_user, user_id)
    except admin_users_service.RoleUnchanged as exc:
        flash(str(exc), "info")
    except admin_users_service.AdminUserError:
        flash("That user could not be updated.", "error")
    else:
        flash(f"{target.name} is now an admin.", "success")
    return _back_to_settings()


@admin_bp.route("/users/<int:user_id>/revoke", methods=["POST"])
@admin_required
def revoke_user(user_id: int):
    try:
        target = admin_users_service.revoke_admin(current_user, user_id)
    except admin_users_service.CannotChangeOwnRole as exc:
        flash(str(exc), "error")
    except admin_users_service.RoleUnchanged as exc:
        flash(str(exc), "info")
    except admin_users_service.AdminUserError:
        flash("That user could not be updated.", "error")
    else:
        flash(f"{target.name} is no longer an admin.", "success")
    return _back_to_settings()
