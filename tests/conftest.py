"""Pytest fixtures.

The M0 smoke tests exercise routing only (home + /health) and don't touch the
database, so they run with a throwaway in-memory SQLite URI — no Postgres or
Docker required just to verify the app boots.
"""
import pytest

from app import create_app
from app.config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def app():
    return create_app(TestConfig)


@pytest.fixture()
def client(app):
    return app.test_client()
