# PROGRESS — CIRCLO

_Claude Code: read this at the START of each session to restore state, and UPDATE it
at the END (what got done, what's next, any blockers). Keep it short and current.
The real source of truth is the code + git history; this file just helps orient fast._

## Current milestone: M0 — Foundation (DONE ✅)

## Done
- Repo created; CLAUDE.md, CIRCLO_Technical_Blueprint.md, and this file added.
- **M0 Foundation complete and verified end-to-end via Docker:**
  - Flask 3 application-factory (`app/__init__.py`) + blueprints (web/api/admin).
  - Config layer (`app/config.py`): `Config`/`DevConfig`/`ProdConfig`, everything
    from env vars via python-dotenv; `ProdConfig` fails fast on missing secrets.
  - Extensions (`app/extensions.py`): SQLAlchemy `db`, Flask-Migrate, Flask-Login
    (stub `user_loader` returning None until M1).
  - PostgreSQL + Flask-Migrate/Alembic scaffold wired (`migrations/`); `flask db
    upgrade` runs automatically on container start. No tables yet (M0 has no models).
  - S3-compatible storage service (`app/services/storage.py`): boto3 client from
    env, presigned GET/PUT helpers, `ensure_buckets()`; stores only object keys.
  - Web blueprint: home page (Tailwind + HTMX via CDN, base + index templates) and
    `/health` → `{"status":"ok"}`.
  - Docker: `Dockerfile` (Gunicorn, non-root), `docker-compose.yml` (app + postgres
    + minio) with **env-overridable host ports**, `docker/entrypoint.sh` (waits for
    DB → migrates → ensures buckets → gunicorn), `.dockerignore`, `.gitattributes`.
  - `.env.example` (dummy values), `.gitignore` (ignores real `.env`),
    `requirements.txt`, updated `README.md`.
  - Smoke tests (`tests/`) pass; `docker compose up --build` serves `/` (200) and
    `/health` (`{"status":"ok"}`) with no manual fiddling.

## In progress
- (nothing — M0 shipped)

## Next up
- M1 Auth & Identity: `User` model + first real migration, signup/login
  (Flask-Login), email + phone OTP, manual CNIC/selfie upload (private bucket) →
  admin approval gating list/rent. Replace the stub `user_loader` in
  `app/extensions.py` with a real lookup.

## Blockers / decisions needed
- SMS provider for OTP (recurring cost) — pick one before M1.
- Payment approach for MVP: semi-manual vs gateway (Safepay / JazzCash / Easypaisa).
- Full open-decisions list: CIRCLO_Technical_Blueprint.md §13.

## Reference
- Architecture + milestones: CIRCLO_Technical_Blueprint.md
- Milestone task list: CIRCLO_Progress_Tracker.xlsx
- Run: `cp .env.example .env && docker compose up --build` → http://localhost:5000
