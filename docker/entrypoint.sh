#!/usr/bin/env bash
# Container entrypoint: wait for Postgres, apply migrations, ensure storage
# buckets, then exec the given command (gunicorn by default). This is what lets
# `docker-compose up` work with no manual fiddling.
set -euo pipefail

echo "[entrypoint] waiting for Postgres ..."
python - <<'PY'
import os, time, socket, sys
from urllib.parse import urlparse

# On Render (and any real deployment) DATABASE_URL already points at the real
# DB host/port; parse it from there. Locally with Docker Compose, DATABASE_URL
# uses the "postgres" service name too, but POSTGRES_HOST/PORT_INTERNAL can
# override it -- fall back to the compose default if nothing is set.
host, port = "postgres", 5432
database_url = os.environ.get("DATABASE_URL")
if database_url:
    parsed = urlparse(database_url)
    if parsed.hostname:
        host = parsed.hostname
        port = parsed.port or 5432

host = os.environ.get("POSTGRES_HOST", host)
port = int(os.environ.get("POSTGRES_PORT_INTERNAL", port))

print(f"[entrypoint] resolved Postgres host: {host}:{port}")
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("[entrypoint] Postgres is up.")
            sys.exit(0)
    except OSError:
        time.sleep(1)
print("[entrypoint] ERROR: Postgres did not become ready in time.", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] applying database migrations ..."
flask db upgrade

if [[ "${STORAGE_ENDPOINT_URL:-}" == *"r2"* ]]; then
    echo "[entrypoint] R2 endpoint detected; skipping ensure_buckets (create buckets manually in the Cloudflare dashboard)."
else
    echo "[entrypoint] ensuring object-storage buckets exist ..."
    python - <<'PY'
from app import create_app
from app.services import storage

app = create_app()
with app.app_context():
    try:
        storage.ensure_buckets()
        print("[entrypoint] buckets ready.")
    except Exception as exc:  # storage is non-fatal for boot; log and continue
        print(f"[entrypoint] WARNING: could not ensure buckets: {exc}")
PY
fi

echo "[entrypoint] starting: $*"
exec "$@"
