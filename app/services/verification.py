"""Identity verification service — CNIC + selfie upload, admin review, gating.

All logic lives here (not in routes) so the future ``/api/v1`` can reuse it
(blueprint §4). Documents are uploaded to the *private* storage bucket; only
object keys are persisted (blueprint §8, §9).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import IdentityDocument, User
from app.models.identity_document import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from app.models.user import VERIFICATION_APPROVED, VERIFICATION_PENDING, VERIFICATION_REJECTED
from app.services import storage

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_FOR_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class InvalidDocumentUpload(Exception):
    """Raised when the CNIC/selfie files fail basic validation."""


def latest_document_for(user: User) -> IdentityDocument | None:
    """Most recent submission for ``user``, or ``None`` if they've never applied."""
    return (
        IdentityDocument.query.filter_by(user_id=user.id)
        .order_by(IdentityDocument.submitted_at.desc())
        .first()
    )


def pending_documents() -> list[IdentityDocument]:
    """All pending submissions, oldest first — the admin review queue."""
    return (
        IdentityDocument.query.filter_by(status=STATUS_PENDING)
        .order_by(IdentityDocument.submitted_at.asc())
        .all()
    )


def _validate_image(f, label: str) -> str:
    if f is None or not f.filename:
        raise InvalidDocumentUpload(f"Please choose a {label} photo.")
    content_type = (f.mimetype or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise InvalidDocumentUpload(f"{label} must be a JPG, PNG, or WEBP image.")
    return _EXT_FOR_TYPE[content_type]


def submit_documents(user: User, *, cnic_file, selfie_file) -> IdentityDocument:
    """Upload CNIC + selfie to the private bucket and create a pending submission.

    :raises InvalidDocumentUpload: if either file is missing or not an image.
    """
    cnic_ext = _validate_image(cnic_file, "CNIC")
    selfie_ext = _validate_image(selfie_file, "selfie")

    folder = f"identity/{user.id}/{uuid.uuid4().hex}"
    cnic_key = f"{folder}/cnic.{cnic_ext}"
    selfie_key = f"{folder}/selfie.{selfie_ext}"

    storage.upload_fileobj(cnic_file.stream, cnic_key, content_type=cnic_file.mimetype, private=True)
    storage.upload_fileobj(selfie_file.stream, selfie_key, content_type=selfie_file.mimetype, private=True)

    doc = IdentityDocument(
        user_id=user.id,
        cnic_image_key=cnic_key,
        selfie_image_key=selfie_key,
        status=STATUS_PENDING,
    )
    user.verification_status = VERIFICATION_PENDING
    db.session.add(doc)
    db.session.commit()

    _notify_admin_pending(doc)
    return doc


def _notify_admin_pending(doc: IdentityDocument) -> None:
    """Notify admins a new verification is pending review.

    Just logs for now (blueprint: email/SMS providers land later).
    """
    current_app.logger.info(
        "New verification pending: document #%s for user #%s (%s)",
        doc.id, doc.user_id, doc.user.email,
    )


def approve(doc: IdentityDocument, *, reviewer: User) -> IdentityDocument:
    doc.status = STATUS_APPROVED
    doc.reviewed_by = reviewer.id
    doc.reviewed_at = datetime.utcnow()
    doc.rejection_reason = None
    doc.user.verification_status = VERIFICATION_APPROVED
    db.session.commit()
    return doc


def reject(doc: IdentityDocument, *, reviewer: User, reason: str) -> IdentityDocument:
    doc.status = STATUS_REJECTED
    doc.reviewed_by = reviewer.id
    doc.reviewed_at = datetime.utcnow()
    doc.rejection_reason = reason.strip()
    doc.user.verification_status = VERIFICATION_REJECTED
    db.session.commit()
    return doc


def get_document(document_id: int) -> IdentityDocument | None:
    return db.session.get(IdentityDocument, document_id)
