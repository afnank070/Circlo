#!/usr/bin/env bash
# Container entrypoint: wait for Postgres, apply migrations, ensure storage
# buckets, then exec the given command (gunicorn by default). This is what lets
# `docker-compose up` work with no manual fiddling.
set -euo pipefail

echo "[entrypoint] waiting for Postgres at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT_INTERNAL:-5432} ..."
python - <<'PY'
import os, time, socket, sys

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT_INTERNAL", "5432"))
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
