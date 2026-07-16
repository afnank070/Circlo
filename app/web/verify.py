"""Identity verification web routes — status page + CNIC/selfie upload.

Thin adapter over :mod:`app.services.verification`. Login required; no account
logic lives here so ``/api/v1`` can reuse the service later (blueprint §4).
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models.identity_document import STATUS_PENDING, STATUS_REJECTED
from app.services import verification as verification_service

from . import web_bp


@web_bp.route("/verify", methods=["GET", "POST"])
@login_required
def verify():
    document = verification_service.latest_document_for(current_user)

    if request.method == "POST":
        # Only allow (re)submitting when there's no document yet, or the last
        # one was rejected — an approved/pending user has nothing to upload.
        if document is not None and document.status != STATUS_REJECTED:
            flash("Your verification is already submitted.", "info")
            return redirect(url_for("web.verify"))

        try:
            verification_service.submit_documents(
                current_user,
                cnic_file=request.files.get("cnic_image"),
                selfie_file=request.files.get("selfie_image"),
            )
        except verification_service.InvalidDocumentUpload as exc:
            flash(str(exc), "error")
            return redirect(url_for("web.verify"))

        flash("Submitted for review. We'll update your status here once an admin reviews it.", "success")
        return redirect(url_for("web.verify"))

    return render_template(
        "verify/status.html",
        document=document,
        show_upload=(document is None or document.status == STATUS_REJECTED),
    )
