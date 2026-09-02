"""Custom Flask CLI commands.

Thin adapters over the service layer, registered on the app in the factory. Like
the web and (future) API blueprints, commands hold no business logic themselves.
"""
from __future__ import annotations

import click
from flask import Flask


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed() -> None:
        """Populate the database with demo categories, listings and images."""
        from app.services.seed import seed_all

        summary = seed_all()
        click.echo(
            f"Seeded {summary['owners']} owners, "
            f"{summary['categories']} categories, "
            f"{summary['listings']} listings, "
            f"{summary['images']} images."
        )

    @app.cli.command("send-test-email")
    @click.argument("recipient")
    def send_test_email(recipient: str) -> None:
        """Send a one-off test email to RECIPIENT to confirm Brevo delivery works."""
        from app.services import email as email_service

        if not email_service.is_configured():
            click.echo(
                "Email not configured — set BREVO_API_KEY / MAIL_FROM_ADDRESS in "
                ".env. (The message would just be logged.)"
            )
        ok = email_service.send_email(
            recipient,
            "CIRCLO test email",
            "<p>This is a test from <strong>CIRCLO</strong>. "
            "If you can read this, Brevo API delivery works.</p>",
        )
        click.echo("Sent ✓" if ok else "Not sent — check the app log for the reason.")

    @app.cli.command("seed-test-accounts")
    def seed_test_accounts() -> None:
        """Create test users and listings for rapid testing (idempotent).

        Creates:
        - Regular verified user: user@circlo.test / testpass123
        - Admin verified user: admin@circlo.test / adminpass123
        - 1-2 seed listings (if none exist)
        """
        from app.extensions import db
        from app.models import Category, Listing
        from app.models.user import ROLE_ADMIN, VERIFICATION_APPROVED
        from app.services import auth, listings as listings_service

        # Ensure categories exist
        if not Category.query.first():
            db.session.add_all([
                Category(name="Cameras", slug="cameras"),
                Category(name="Tools", slug="tools"),
            ])
            db.session.commit()

        # Create regular user if not exists
        user = auth.get_user_by_email("user@circlo.test")
        if not user:
            user = auth.create_user("Test Renter", "user@circlo.test", "testpass123")
            user.verification_status = VERIFICATION_APPROVED
            db.session.commit()
            click.echo("[+] Created regular user: user@circlo.test / testpass123")
        else:
            click.echo("[+] Regular user already exists: user@circlo.test")

        # Create admin user if not exists
        admin = auth.get_user_by_email("admin@circlo.test")
        if not admin:
            admin = auth.create_user("Test Admin", "admin@circlo.test", "adminpass123")
            admin.role = ROLE_ADMIN
            admin.verification_status = VERIFICATION_APPROVED
            db.session.commit()
            click.echo("[+] Created admin user: admin@circlo.test / adminpass123")
        else:
            click.echo("[+] Admin user already exists: admin@circlo.test")

        # Create 1-2 seed listings owned by admin if none exist
        if Listing.query.count() == 0:
            listings_to_create = [
                {
                    "title": "Canon EOS R6",
                    "description": "Full-frame mirrorless camera, excellent for photography.",
                    "category_slug": "cameras",
                    "city": "Islamabad",
                    "area": "F-8",
                    "price_per_day": 1500,
                    "deposit_amount": 20000,
                },
                {
                    "title": "Bosch Hammer Drill",
                    "description": "Corded 750W professional hammer drill with case.",
                    "category_slug": "tools",
                    "city": "Islamabad",
                    "area": "G-9",
                    "price_per_day": 800,
                    "deposit_amount": 5000,
                },
            ]
            for item in listings_to_create:
                cat = Category.query.filter_by(slug=item.pop("category_slug")).first()
                if cat:
                    listings_service.create_listing(
                        owner=admin,
                        category_id=cat.id,
                        **item,
                    )
            click.echo(f"[+] Created {len(listings_to_create)} seed listings")
        else:
            click.echo(f"[+] Listings already exist ({Listing.query.count()} found)")

        click.echo("\n[OK] Test accounts ready. Log in with:")
        click.echo("  User:  user@circlo.test / testpass123")
        click.echo("  Admin: admin@circlo.test / adminpass123")
