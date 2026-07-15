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
