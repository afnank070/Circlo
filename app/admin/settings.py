"""Admin settings — edit admin-configurable operational values.

Currently just the CIRCLO payment-collection details (EasyPaisa / bank account)
shown to renters on the payment step. Backed by ``services.settings`` so the
values are DB-stored and editable without a redeploy.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

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

    return render_template(
        "settings.html",
        payment_fields=settings_service.PAYMENT_SETTINGS,
        values=settings_service.get_many(settings_service.PAYMENT_SETTINGS.keys()),
    )
