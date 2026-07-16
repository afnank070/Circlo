"""Admin identity-verification review queue — approve/reject CNIC + selfie submissions."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.services import storage
from app.services import verification as verification_service

from . import admin_bp, admin_required


@admin_bp.app_template_global()
def private_image_url(key: str | None) -> str | None:
    """Jinja helper: presigned URL for a private-bucket object key."""
    if not key:
        return None
    return storage.presigned_url(key, private=True)


@admin_bp.route("/verify")
@admin_required
def queue():
    documents = verification_service.pending_documents()
    return render_template("verify_queue.html", documents=documents)


@admin_bp.route("/verify/<int:document_id>/approve", methods=["POST"])
@admin_required
def approve(document_id: int):
    document = verification_service.get_document(document_id)
    if document is None:
        flash("Submission not found.", "error")
        return redirect(url_for("admin.queue"))

    verification_service.approve(document, reviewer=current_user)
    flash(f"Approved {document.user.name}.", "success")
    return redirect(url_for("admin.queue"))


@admin_bp.route("/verify/<int:document_id>/reject", methods=["POST"])
@admin_required
def reject(document_id: int):
    document = verification_service.get_document(document_id)
    if document is None:
        flash("Submission not found.", "error")
        return redirect(url_for("admin.queue"))

    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Please give a reason for rejecting.", "error")
        return redirect(url_for("admin.queue"))

    verification_service.reject(document, reviewer=current_user, reason=reason)
    flash(f"Rejected {document.user.name}.", "info")
    return redirect(url_for("admin.queue"))
