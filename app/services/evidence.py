"""Evidence service — before/after handover photos (blueprint §5, §6, §8).

Both parties upload photos *before* the item changes hands and *after* it comes
back. Files go to the **private** bucket (only the object key is stored). Once
*both* the renter and the owner have uploaded for a phase, the booking advances:

    PAID    --both "before" photos-->  HANDED_OVER -> ACTIVE
    ACTIVE  --both "after" photos -->  RETURNED

Evidence is write-once: there is no update/delete here so it holds up in a
dispute.
"""
from __future__ import annotations

import uuid

from app.extensions import db
from app.models import Booking, EvidenceMedia, User
from app.models.booking import (
    STATUS_ACTIVE,
    STATUS_HANDED_OVER,
    STATUS_PAID,
    STATUS_RETURNED,
)
from app.models.evidence_media import MEDIA_PHOTO, PHASE_AFTER, PHASE_BEFORE, PHASES
from app.services import storage

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_FOR_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# Which booking status each phase's upload is allowed from.
_PHASE_REQUIRES = {PHASE_BEFORE: STATUS_PAID, PHASE_AFTER: STATUS_ACTIVE}


class EvidenceError(Exception):
    """Base class for evidence-flow errors."""


class InvalidEvidenceUpload(EvidenceError):
    """Bad file, unknown phase, or wrong booking state for this phase."""


class EvidencePermissionError(EvidenceError):
    """The uploader is neither the renter nor the owner on this booking."""


def _validate_image(f) -> str:
    if f is None or not getattr(f, "filename", ""):
        raise InvalidEvidenceUpload("Please choose a photo to upload.")
    content_type = (f.mimetype or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise InvalidEvidenceUpload("Photo must be a JPG, PNG, or WEBP image.")
    return _EXT_FOR_TYPE[content_type]


def evidence_for_booking(booking: Booking) -> list[EvidenceMedia]:
    return (
        EvidenceMedia.query.filter_by(booking_id=booking.id)
        .order_by(EvidenceMedia.created_at.asc(), EvidenceMedia.id.asc())
        .all()
    )


def has_uploaded(booking: Booking, user_id: int, phase: str) -> bool:
    return (
        EvidenceMedia.query.filter_by(
            booking_id=booking.id, phase=phase, uploaded_by=user_id
        ).count()
        > 0
    )


def both_parties_uploaded(booking: Booking, phase: str) -> bool:
    return has_uploaded(booking, booking.renter_id, phase) and has_uploaded(
        booking, booking.owner_id, phase
    )


def upload_evidence(
    booking: Booking, user: User, *, phase: str, file, media_type: str = MEDIA_PHOTO
) -> EvidenceMedia:
    """Store one evidence photo and advance the booking if both sides are done.

    :raises EvidencePermissionError: ``user`` isn't a party to the booking.
    :raises InvalidEvidenceUpload: bad phase, bad file, or wrong booking state.
    """
    if user.id not in (booking.renter_id, booking.owner_id):
        raise EvidencePermissionError("You're not part of this booking.")
    if phase not in PHASES:
        raise InvalidEvidenceUpload("Unknown evidence phase.")

    required_status = _PHASE_REQUIRES[phase]
    if booking.status != required_status:
        if phase == PHASE_BEFORE:
            raise InvalidEvidenceUpload(
                "Handover (before) photos can only be uploaded once the booking is paid."
            )
        raise InvalidEvidenceUpload(
            "Return (after) photos can only be uploaded while the rental is active."
        )

    ext = _validate_image(file)
    key = f"evidence/{booking.id}/{phase}/{user.id}/{uuid.uuid4().hex}.{ext}"
    storage.upload_fileobj(file.stream, key, content_type=file.mimetype, private=True)

    media = EvidenceMedia(
        booking_id=booking.id,
        phase=phase,
        uploaded_by=user.id,
        object_key=key,
        media_type=media_type,
    )
    db.session.add(media)
    db.session.flush()

    _maybe_advance(booking, phase)
    db.session.commit()
    return media


def _maybe_advance(booking: Booking, phase: str) -> None:
    """Move the booking forward once both parties have uploaded for ``phase``."""
    if not both_parties_uploaded(booking, phase):
        return
    if phase == PHASE_BEFORE and booking.status == STATUS_PAID:
        # HANDED_OVER is instantaneous in the MVP — record it, then go ACTIVE.
        booking.status = STATUS_HANDED_OVER
        booking.status = STATUS_ACTIVE
    elif phase == PHASE_AFTER and booking.status == STATUS_ACTIVE:
        booking.status = STATUS_RETURNED
