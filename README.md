# CIRCLO

A peer-to-peer rental marketplace for Pakistan (Islamabad & Rawalpindi). Item
owners list under-used things; renters book them for short periods. CIRCLO holds
the payment + security deposit, verifies identity, keeps a before/after evidence
trail, and takes a 20% commission.

This repo is the **web app + backend API** (built API-first so a separate mobile
app can reuse the same backend). See [`CIRCLO_Technical_Blueprint.md`](CIRCLO_Technical_Blueprint.md)
for the full architecture and [`PROGRESS.md`](PROGRESS.md) for current status.

## Stack

Python 3.12 · Flask (app-factory + blueprints) · SQLAlchemy + Flask-Migrate ·
PostgreSQL · Jinja2 + HTMX + Tailwind (CDN) · boto3 → MinIO (local) / R2 (prod) ·
Docker Compose · Gunicorn.

## Repository layout

```
app/
  __init__.py     application factory
  config.py       Config / DevConfig / ProdConfig (all values from env vars)
  extensions.py   db, migrate, login_manager
  models/         SQLAlchemy models (User, Category, Listing, ListingImage)
  services/       business logic — reused by web + future /api/v1
    auth.py       signup / authenticate / user lookup
    listings.py   browse/search + owner create/edit/delete
    storage.py    S3-compatible storage (MinIO/R2) + presigned URLs
  web/            Jinja routes + templates (browse, auth, owner listings, /health)
  api/            /api/v1 JSON routes (M6)
  admin/          admin panel (later)
migrations/       Alembic
docker/           entrypoint (waits for DB, migrates, ensures buckets)
tests/            smoke tests
```

## Run it (Docker — recommended)

Requires Docker Desktop. From the repo root:

```bash
cp .env.example .env
docker-compose up --build
```

The entrypoint waits for Postgres, applies migrations, and creates the MinIO
buckets automatically — no manual steps. Then open:

- Home page: <http://localhost:5000/>
- Health check: <http://localhost:5000/health> → `{"status":"ok"}`
- MinIO console: <http://localhost:9001> (login with `STORAGE_ACCESS_KEY` /
  `STORAGE_SECRET_KEY` from your `.env`)

## Accounts & demo data

**For rapid testing** (creates pre-verified test users + sample listings):

```bash
docker-compose exec app flask seed-test-accounts
```

This creates (idempotent):
- Regular user: `user@circlo.test` / `testpass123` (already verified)
- Admin user: `admin@circlo.test` / `adminpass123` (already verified, can approve identity docs)
- 1–2 sample listings owned by the admin (Camera, Drill) if none exist

**For full demo data** (many owners + listings + categories):

```bash
docker-compose exec app flask seed
```

This creates one demo owner per listing, all sharing the password `circlo123`
with emails like `sara.malik@demo.circlo.pk`. Log in as any of them to edit their
listings, or sign up for a fresh account at <http://localhost:5000/signup> and
list your own items via **+ List an item**. (Identity verification — phone OTP,
email, CNIC/selfie review — is deferred; `verification_status` exists for it.)

### Ports already in use?

Every host port is overridable in `.env` — the app still works because the
containers talk to each other over the internal network regardless:

```env
APP_HOST_PORT=5001
POSTGRES_HOST_PORT=55432
MINIO_HOST_PORT=9002
MINIO_CONSOLE_HOST_PORT=9003
```

## Database migrations

Migrations run automatically on container start. To create a new one after
adding/altering a model (from M1 onward):

```bash
docker-compose exec app flask db migrate -m "describe change"
docker-compose exec app flask db upgrade
```

## Tests

Smoke tests need no database or Docker (in-memory SQLite):

```bash
pip install -r requirements.txt pytest
pytest
```

Or run them inside the app container:

```bash
docker-compose exec app python -m pytest -q
```

## Configuration

Nothing environment-specific is hard-coded. Every value (secret key, database
DSN, storage endpoint + keys, host ports) comes from environment variables loaded
via `python-dotenv` into a `Config` class. `APP_ENV=development|production`
selects `DevConfig`/`ProdConfig`. Only object **keys** are stored in the DB;
URLs are built at runtime with presigned-URL helpers in `app/services/storage.py`.
Copy `.env.example` → `.env`; the real `.env` is git-ignored.
