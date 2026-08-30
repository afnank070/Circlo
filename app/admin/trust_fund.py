"""Admin Trust & Safety Fund view — bookkeeping only (blueprint §6, §7)."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.services import trust_fund as trust_fund_service

from . import admin_bp, admin_required


@admin_bp.route("/trust-fund", methods=["GET", "POST"])
@admin_required
def trust_fund_page():
    if request.method == "POST":
        try:
            trust_fund_service.set_starting_balance(
                request.form.get("starting_balance", "0"), admin=current_user
            )
        except Exception:  # noqa: BLE001
            flash("Enter a valid number.", "error")
        else:
            flash("Starting balance saved.", "success")
        return redirect(url_for("admin.trust_fund_page"))

    return render_template(
        "trust_fund.html",
        starting_balance=trust_fund_service.starting_balance(),
        total_disbursed=trust_fund_service.total_disbursed(),
        current_balance=trust_fund_service.current_balance(),
        disbursements=trust_fund_service.disbursements(),
    )
