"""WSGI entry point.

Gunicorn runs ``wsgi:app`` in the container; ``flask`` CLI uses ``FLASK_APP=wsgi.py``
so that ``flask db migrate`` / ``flask db upgrade`` work.
"""
from app import create_app

app = create_app()
