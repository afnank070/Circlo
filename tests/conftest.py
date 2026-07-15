"""Pytest fixtures.

The smoke tests run against a throwaway in-memory SQLite DB — no Postgres or
Docker required just to verify the app boots. From M2 the browse route touches
the database, so the fixture creates the schema (``db.create_all()``) before the
test client hits it. No seed data is inserted: an empty marketplace renders the
empty state, which is enough to prove routing + templates work.
"""
import pytest

from app import create_app
from app.config import Config
from app.extensions import db


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
