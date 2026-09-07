"""Smoke tests — the /contact form.

Submitting a valid message triggers exactly one email send, addressed to
CONTACT_EMAIL (contact@circlo.pk), NOT the automated-mail sender. The honeypot
drops bot submissions without emailing. Logged-in users get their details
pre-filled. The actual Brevo call is mocked.
"""
import pytest

from app.extensions import db
from app.models.user import VERIFICATION_APPROVED
from app.services import auth as auth_service


@pytest.fixture()
def sent_emails(monkeypatch):
    """Record every send_email(to, subject, body_html) call; nothing goes out."""
    box = []
    monkeypatch.setattr(
        "app.services.email.send_email",
        lambda to, subject, body_html, **kw: box.append(
            {"to": to, "subject": subject, "body": body_html}
        )
        or True,
        raising=True,
    )
    return box


def _form(**over):
    data = {
        "name": "Sana Khan",
        "email": "sana@example.com",
        "category": "bug",
        "message": "The upload button does nothing on the listing form.",
        "website": "",
    }
    data.update(over)
    return data


def test_contact_page_renders(client):
    resp = client.get("/contact")
    assert resp.status_code == 200
    assert b'name="name"' in resp.data
    assert b'name="email"' in resp.data
    assert b'name="category"' in resp.data
    assert b'name="message"' in resp.data
    assert b'name="website"' in resp.data  # honeypot present
    assert b"Report a bug" in resp.data


def test_submit_sends_one_email_to_contact_inbox(client, app, sent_emails):
    resp = client.post("/contact", data=_form(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"we'll get back to you" in resp.data.lower() or b"we'll be in touch" in resp.data.lower()

    assert len(sent_emails) == 1
    msg = sent_emails[0]
    assert msg["to"] == "contact@circlo.pk"
    assert msg["to"] != app.config.get("MAIL_FROM_ADDRESS")
    assert "Report a bug" in msg["subject"]
    assert "Sana Khan" in msg["body"]
    assert "sana@example.com" in msg["body"]
    assert "upload button does nothing" in msg["body"]


def test_honeypot_drops_message_without_sending(client, sent_emails):
    resp = client.post("/contact", data=_form(website="http://spam.example"),
                       follow_redirects=True)
    assert resp.status_code == 200
    # Bot sees a normal success page; no email actually sent.
    assert sent_emails == []


def test_short_message_is_rejected(client, sent_emails):
    resp = client.post("/contact", data=_form(message="hi"))
    assert resp.status_code == 200
    assert b"bit more detail" in resp.data
    assert sent_emails == []


def test_missing_name_is_rejected(client, sent_emails):
    resp = client.post("/contact", data=_form(name=""))
    assert b"enter your name" in resp.data
    assert sent_emails == []


def test_unknown_category_falls_back_to_general(client, sent_emails):
    client.post("/contact", data=_form(category="pwn"), follow_redirects=True)
    assert len(sent_emails) == 1
    assert "General question" in sent_emails[0]["subject"]


def test_logged_in_user_details_are_prefilled(client, app, sent_emails):
    with app.app_context():
        u = auth_service.create_user("Bilal Owner", "bilal@example.com",
                                     "supersecret", phone="03001234567")
        u.verification_status = VERIFICATION_APPROVED
        db.session.commit()
    client.post("/login", data={"email": "bilal@example.com", "password": "supersecret"})

    page = client.get("/contact").data
    assert b'value="Bilal Owner"' in page
    assert b'value="bilal@example.com"' in page

    # A logged-in user who leaves the fields as-is still submits with their info.
    client.post("/contact", data={"category": "general",
                                  "message": "Just checking the contact form works.",
                                  "website": ""}, follow_redirects=True)
    assert len(sent_emails) == 1
    assert "bilal@example.com" in sent_emails[0]["body"]


def test_footer_links_to_contact_page(client):
    body = client.get("/").data
    assert b'href="/contact"' in body
    assert b">Contact us</a>" in body
    assert b"mailto:help@circlo.pk" not in body
