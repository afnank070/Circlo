"""Admin disputes queue — review and resolve reported problems (blueprint §6)."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.services import disputes as disputes_service

from . import admin_bp, admin_required


@admin_bp.route("/disputes")
@admin_required
def disputes_queue():
    return render_template(
        "disputes_queue.html",
        open_disputes=disputes_service.open_disputes(),
        resolved_disputes=disputes_service.resolved_disputes(),
    )


@admin_bp.route("/disputes/<int:dispute_id>/resolve", methods=["POST"])
@admin_required
def resolve_dispute(dispute_id: int):
    dispute = disputes_service.get_dispute(dispute_id)
    if dispute is None:
        flash("Dispute not found.", "error")
        return redirect(url_for("admin.disputes_queue"))
    try:
        disputes_service.resolve_dispute(
            dispute,
            admin=current_user,
            resolution=request.form.get("resolution", ""),
            deposit_decision=request.form.get("deposit_decision", "pending"),
            amount_from_fund=request.form.get("amount_from_fund", "0"),
        )
    except disputes_service.DisputeError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Dispute #{dispute.id} resolved.", "success")
    return redirect(url_for("admin.disputes_queue"))
