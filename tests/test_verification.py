"""M1 part 2 smoke tests — CNIC/selfie upload, admin review, listing gating.

Uploads go through the real storage service (private MinIO bucket), same as the
existing listing-image tests hit the public bucket when running in the app
container against docker-compose's MinIO.
"""
import io

from app.extensions import db
from app.models import IdentityDocument
from app.models.user import ROLE_ADMIN, VERIFICATION_APPROVED
from app.services import auth as auth_service

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _signup(client, email="renter@example.com", name="Renter Person"):
    return client.post(
        "/signup",
        data={"name": name, "email": email, "password": "supersecret", "confirm": "supersecret"},
        follow_redirects=True,
    )


def _make_admin(app, email="admin@example.com"):
    with app.app_context():
        admin = auth_service.create_user("Admin Person", email, "supersecret")
        admin.role = ROLE_ADMIN
        admin.verification_status = VERIFICATION_APPROVED
        db.session.commit()
    return email


def _upload(client):
    return client.post(
        "/verify",
        data={
            "cnic_image": (io.BytesIO(PNG_BYTES), "cnic.png", "image/png"),
            "selfie_image": (io.BytesIO(PNG_BYTES), "selfie.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_verify_requires_login(client):
    resp = client.get("/verify")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_unverified_user_redirected_from_listing_form(client, app):
    _signup(client, email="unverified@example.com")
    resp = client.get("/listings/new", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Verify your identity to list items" in resp.data
    assert b"Identity verification" in resp.data  # landed on /verify


def test_upload_creates_pending_document(client, app):
    _signup(client, email="upload@example.com")
    resp = _upload(client)
    assert resp.status_code == 200
    assert b"Submitted for review" in resp.data or b"pending review" in resp.data

    with app.app_context():
        user = auth_service.get_user_by_email("upload@example.com")
        doc = IdentityDocument.query.filter_by(user_id=user.id).first()
        assert doc is not None
        assert doc.status == "pending"
        assert doc.cnic_image_key.startswith(f"identity/{user.id}/")
        assert doc.selfie_image_key.startswith(f"identity/{user.id}/")
        assert user.verification_status == "pending"


def test_admin_approve_updates_user_status(client, app):
    _signup(client, email="approveme@example.com")
    _upload(client)
    client.post("/logout")

    admin_email = _make_admin(app, "approver@example.com")
    client.post("/login", data={"email": admin_email, "password": "supersecret"})

    with app.app_context():
        user = auth_service.get_user_by_email("approveme@example.com")
        doc = IdentityDocument.query.filter_by(user_id=user.id).first()
        doc_id = doc.id

    resp = client.get("/admin/verify")
    assert resp.status_code == 200
    assert b"approveme@example.com" in resp.data

    resp = client.post(f"/admin/verify/{doc_id}/approve", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        user = auth_service.get_user_by_email("approveme@example.com")
        assert user.verification_status == "approved"
        doc = db.session.get(IdentityDocument, doc_id)
        assert doc.status == "approved"
        assert doc.reviewed_by == auth_service.get_user_by_email("approver@example.com").id
        assert doc.reviewed_at is not None


def test_admin_reject_sets_reason_and_allows_reupload(client, app):
    _signup(client, email="rejectme@example.com")
    _upload(client)
    client.post("/logout")

    admin_email = _make_admin(app, "rejector@example.com")
    client.post("/login", data={"email": admin_email, "password": "supersecret"})

    with app.app_context():
        user = auth_service.get_user_by_email("rejectme@example.com")
        doc_id = IdentityDocument.query.filter_by(user_id=user.id).first().id

    resp = client.post(
        f"/admin/verify/{doc_id}/reject",
        data={"reason": "CNIC photo is blurry."},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        user = auth_service.get_user_by_email("rejectme@example.com")
        assert user.verification_status == "rejected"

    client.post("/logout")
    client.post("/login", data={"email": "rejectme@example.com", "password": "supersecret"})
    resp = client.get("/verify")
    assert resp.status_code == 200
    assert b"blurry" in resp.data
    assert b"cnic_image" in resp.data  # re-upload form is shown again


def test_non_admin_forbidden_from_admin_queue(client, app):
    _signup(client, email="notadmin@example.com")
    resp = client.get("/admin/verify")
    assert resp.status_code == 403
