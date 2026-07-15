# CLAUDE.md — CIRCLO

## What this is
CIRCLO is a peer-to-peer rental marketplace for Pakistan (Islamabad & Rawalpindi).
Web MVP first; a SEPARATE mobile app (built by Abdullah) will reuse the backend API
later. Full architecture is in CIRCLO_Technical_Blueprint.md — treat it as the
source of truth and read it before major work. Current progress and next tasks live
in PROGRESS.md — read it at the START of a session and update it at the END.

## My role
I (Afnan) build the WEB app only. Do NOT build any mobile UI. Keep the backend
API-first so the mobile app can reuse it later.

## Stack
- Python 3.12 + Flask (application-factory + blueprints)
- SQLAlchemy + Flask-Migrate (Alembic) + PostgreSQL
- Jinja2 + HTMX + Tailwind (CDN) for the web UI
- boto3 S3-compatible storage: MinIO locally, Cloudflare R2 when deployed
- Flask-Login (web sessions); JWT later for /api/v1 (mobile)
- Docker Compose (app + postgres + minio); Gunicorn + Nginx in prod

## Non-negotiable rules
- NEVER hard-code URLs, paths, secrets, DB DSN, or storage endpoints. Everything
  comes from env vars via a Config class (DevConfig/ProdConfig) + python-dotenv.
- Store only object KEYS in the DB, never full URLs; build URLs at runtime.
- Use Flask url_for() for internal links.
- Business logic lives in services/ (separate from routes) so /api/v1 can reuse it.
- Commit .env.example with dummy values; never commit the real .env.

## How to run
- cp .env.example .env, then: docker-compose up
- Migrations: flask db migrate / flask db upgrade
- After `docker-compose up`, the home page and /health must work with no fiddling.

## Build order (milestones — see blueprint §12 + the progress tracker)
M0 Foundation → M1 Auth & Identity → M2 Listings & Search → M3 Booking →
M4 Money & Evidence → M5 Trust & Polish → M6 API & Mobile handoff.
Work ONE feature at a time; confirm it runs before moving on.

## Conventions
- Ask before adding new dependencies or making major architectural changes.
- After finishing a feature, give me the exact commands to test it.
- At the end of a work session, update PROGRESS.md (done / in-progress / next / blockers).
