# PROGRESS — CIRCLO

_Claude Code: read this at the START of each session to restore state, and UPDATE it
at the END (what got done, what's next, any blockers). Keep it short and current.
The real source of truth is the code + git history; this file just helps orient fast._

## Current milestone: M1 — Auth & Identity (part 2, DONE ✅)
_(Manual CNIC + selfie identity verification, admin review, and listing-gating.
Phone OTP and email verification are still deferred — they need an SMS/email
provider.)_

## Done — M1 part 2 (identity verification — the trust core)
- **`IdentityDocument` model** (`app/models/identity_document.py`, blueprint §5,
  §8): `user_id`, `cnic_image_key`, `selfie_image_key`, `status`
  (pending/approved/rejected), `reviewed_by`, `reviewed_at`, `rejection_reason`,
  `submitted_at`. Each submission is its own row (resubmission after rejection
  keeps history). Migration `48271134b900`, applied clean on top of `5dfccc05bad8`.
- **Verification service** (`app/services/verification.py`, API-reusable):
  `submit_documents` (validates + uploads CNIC/selfie to the **private** MinIO
  bucket via the existing storage service, only object keys stored),
  `latest_document_for`, `pending_documents` (admin queue), `approve`, `reject`
  (sets `reviewed_by`/`reviewed_at`, mirrors onto `User.verification_status`).
  `_notify_admin_pending` logs a "new verification pending" line for now (real
  email/SMS lands with those providers).
- **`/verify` page** (`app/web/verify.py` + `templates/verify/status.html`,
  login-required): pending → "submitted, awaiting review"; approved → green
  "Verified since <date>" badge; rejected → reason + re-upload form. Upload is a
  two-file form (`cnic_image`, `selfie_image`) validated to JPG/PNG/WEBP.
- **Admin panel** (`app/admin/` — blueprint now actually wired, was a stub):
  `admin_required` decorator (login + `role == 'admin'`, else 403).
  `/admin/verify` lists pending submissions (name, email, submitted-at, CNIC +
  selfie thumbnails via short-lived presigned URLs against the private bucket).
  Approve is one click; Reject prompts for a reason inline. Both redirect back
  to the queue with a flash.
- **Verification gating**: `web.create_listing` now redirects unverified users
  to `/verify` with "Verify your identity to list items." before rendering the
  form. Same pattern noted in code for renting once M3 lands (not enforced yet
  — renting doesn't exist).
- **Tests**: `tests/test_verification.py` (upload flow, admin approve/reject,
  gating redirect, non-admin 403) — 6 new tests, all against the real private
  MinIO bucket. Updated `tests/test_listings_crud.py` to verify the test owner
  first (gating is now enforced) — **20 passing** total.
- Verified live over HTTP (dev overlay): signup → gated at `/listings/new` →
  upload CNIC+selfie (stored under `identity/<user_id>/<uuid>/...` in the
  private bucket) → `/verify` shows pending → admin logs in, sees thumbnails
  render from presigned private URLs, approves → renter's `/verify` flips to
  "Verified since ..." → `/listings/new` now accessible.

### Known follow-ups
- **No CSRF protection yet** — still open from M1 part 1 (Flask-WTF, ask before
  adding). Do before any public deploy.
- CNIC/selfie retention policy not implemented (blueprint §8 suggests deleting
  raw documents once approved, keeping only `verification_status`) — flagged,
  not built.
- Admin notification is a log line only; real email/push lands with a provider.
- Renting isn't gated yet because renting doesn't exist yet (M3).

## Previous milestone: M1 — Auth & Identity (part 1, DONE ✅)
_(Accounts + owner-created listings. Phone OTP, email verification, and CNIC/selfie
review are deferred — they need external services; `verification_status` is in place
for when they land.)_

## Done — M1 part 1 (accounts + owner listings)
- **`User` model** (`app/models/user.py`, blueprint §5): name, email (unique),
  `password_hash`, `role` (default `user`), `verification_status` (default
  `pending`), `rating` (nullable cache, filled by Reviews in M5), `created_at`.
  `UserMixin` + Werkzeug password hashing (`set_password`/`check_password`);
  `is_verified`/`initials` helpers. **No plaintext passwords** (blueprint §8).
- **Auth service** (`app/services/auth.py`, API-reusable): `create_user`
  (raises `EmailAlreadyRegistered`), `authenticate`, `get_user`,
  `get_user_by_email`, `normalize_email`. Real Flask-Login `user_loader` now wired
  in `extensions.py` (was the M0 stub); `login_view = web.login`.
- **Auth routes** (`app/web/auth.py`): `/signup`, `/login` (with safe `?next=`
  redirect guard), `/logout` (POST). Server-side validation + flash messages.
- **Listing → User FK**: dropped the denormalised `owner_name`/`owner_rating`/
  `is_verified` columns; added `owner_id` FK + `owner` relationship. Listing keeps
  `owner_name`/`owner_rating`/`is_verified` as **read-only passthroughs** to the
  owner so templates/API are unchanged. New owners (no rating) render as "New".
- **Owner listing CRUD** (`app/services/listings.py` + `app/web/owner.py`):
  `create_listing`, `update_listing` (add/remove images), `delete_listing`,
  `listings_for_owner`. Multi-image upload goes through the existing storage
  service → MinIO; **only object keys stored** (`listings/<id>/<uuid>.<ext>`),
  image types/count validated. Ownership guard: only the owner can edit/delete
  (403 otherwise); browse/detail stay public.
- **UI** (matches the navy/teal marketplace theme): `auth/signup.html`,
  `auth/login.html`, `listings/form.html` (shared create/edit), `listings/
  my_listings.html`, flash-message region + auth-aware header (account menu w/
  logout, or Log in/Sign up) in `base.html`. Header "+ List an item" → create form
  (or login if logged out). Owner-only Edit/Delete strip on the detail page.
- **Migration** `5dfccc05bad8`: creates `users`, adds `listings.owner_id`, and
  **backfills** existing M2 listings — each distinct legacy owner becomes a real
  user (rating preserved, `is_verified`→`verification_status`) before `owner_id`
  goes NOT NULL. Verified: 11 legacy listings migrated with owners intact.
- **Seed** now creates a demo user per owner (all share password `circlo123`,
  emails `<name>@demo.circlo.pk`, e.g. `sara.malik@demo.circlo.pk`), verified
  owners → `approved`. `flask seed` → 11 owners, 6 categories, 11 listings, 11 imgs.
- **Tests**: `tests/test_auth.py` (signup/login/logout, dupe email, bad password)
  + `tests/test_listings_crud.py` (create, validation, ownership 403). **14 passing.**
- Verified live over HTTP (dev overlay): signup→create→edit→delete, image upload
  to MinIO (key-only, presigned GET 200 `image/png`), "New" owner badge, owner
  guard. Reseeded to a clean 11/11/11/6 state.

### Known follow-ups (M1 part 2 / later)
- **No CSRF protection yet** — forms POST without tokens. Needs Flask-WTF (a new
  dependency → ask before adding). Do before any public deploy.
- Deferred by design: phone OTP, email verification, CNIC/selfie upload + admin
  approval gating (the `verification_status` field is ready for it).
- `owner_rating` is a per-user cache; real ratings arrive with Reviews (M5).

## Previous milestone: M2 — Listings & Search (read-only marketplace, DONE ✅)

## Done — M2 (read-only marketplace)
- **Models** (`app/models/`): `Category`, `Listing`, `ListingImage` (blueprint §5).
  Owner is denormalised (`owner_name`/`owner_rating`) until the `User` model lands
  in M1; `Listing.status` gates visibility (only `active` is browsable). Images
  store only the object **key**, never a URL.
- **First real Alembic migration** `d65ddfbbd8e7` (categories, listings,
  listing_images) — autogenerated in-container and committed.
- **Services** (business logic, API-reusable): `services/listings.py`
  (`browse_listings` with category + text filter, `get_listing`, `all_categories`)
  and `services/seed.py` (`seed_all`). CLI adapter `flask seed` (`app/cli.py`).
- **Seed data**: 6 categories + 11 realistic Islamabad/Rawalpindi listings (PKR
  price + deposit, area, owner, star rating, verified flag). Each gets an SVG
  placeholder uploaded to MinIO **through the storage service** — real
  upload→key→presigned-URL pipeline, no extra deps.
- **Storage fix**: presigned GET/PUT now sign against `STORAGE_PUBLIC_URL`
  (`http://localhost:9000` in dev, R2 domain in prod) so browser-facing image URLs
  carry a reachable host. Added `STORAGE_PUBLIC_URL` to `.env.example` + `.env`.
- **UI** (Jinja + Tailwind, emerald/slate): browse `/` (responsive 1→4 col card
  grid, category chips + search box) and `/listings/<id>` (two-column: image left;
  price/deposit/owner+verified badge, trust strip, placeholder "Request to Rent").
- Verified end-to-end: pages 200, images render in-browser, category/text filters
  work, missing listing → 404, no console errors. Smoke tests updated → 4 passing.

### M2 visual redesign (mockup match — styling only, no backend change)
- Re-skinned browse + detail to the CIRCLO mockup: deep-navy primary + teal accent
  on a warm sand background; Sora (headings) + Manrope (body) via Google Fonts CDN.
  Theme tokens (navy/teal/sand palettes, fonts, styled range slider) live in a
  `tailwind.config` block in `base.html`.
- **Header** (`base.html`): "circlo" logo w/ circular mark, city selector pill,
  centered search bar, right nav (+ List an item, My Rentals, Messages w/ dot,
  avatar). Search still posts `q` to `web.index` (real). Footer restyled.
- **Browse** (`index.html`): full-bleed navy hero w/ concentric-circle motif +
  new copy; category chips (functional); left filter sidebar (price slider, Area
  dropdown, Verified-owners checkbox — **visual placeholders**); "N items available
  near you" + "Sorted by · Recommended"; redesigned cards (Verified pill, category
  label, star rating, price, deposit, area). Area options derived in-template from
  `listings` (no route change).
- **Detail** (`listing_detail.html`): photo carousel + thumbnail strip (tiny vanilla
  JS; inert with the single seed image), price/deposit card w/ Availability line +
  Request-to-Rent / Message-owner placeholders + "won't be charged yet" note,
  verified-owner card (avatar initials, Verified identity, rating), and a navy
  "Protected by CIRCLO" trust panel (deposit / before-after evidence / Trust Fund).
- No models/routes/services/seed/storage/URLs changed. Verified live via the dev
  overlay (`docker-compose.dev.yml`): both pages 200, all sections render, no
  console errors.
- **Flagged for later (need backend fields, kept as honest placeholders, NOT
  fabricated):** per-listing review counts `(34)`; owner "N rentals · joined YEAR";
  multiple/labeled photos per listing; and actually *wiring* the price/area/verified
  filters (service currently supports only category + text). Land these with the
  M1 User model + a listing/owner-stats extension.

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
- (nothing — M1 part 2 shipped)

## Next up
- Phone OTP + email verification (need an SMS/email provider — blocked, see below).
- Add CSRF protection to all forms (Flask-WTF) — see follow-ups above.
- CNIC/selfie retention policy (delete raw docs after approval?) — blueprint §8.
- M3 Booking: rental request → owner accept/reject, availability, the state machine.
  Gate renting on `verification_status` the same way listing is now gated.

## Blockers / decisions needed
- SMS provider for OTP (recurring cost) — pick before phone verification lands.
- Payment approach for MVP: semi-manual vs gateway (Safepay / JazzCash / Easypaisa).
- Full open-decisions list: CIRCLO_Technical_Blueprint.md §13.

## Reference
- Architecture + milestones: CIRCLO_Technical_Blueprint.md
- Milestone task list: CIRCLO_Progress_Tracker.xlsx
- Run: `cp .env.example .env && docker compose up --build` → http://localhost:5000
- Seed demo data: `docker compose exec app flask seed` (idempotent; re-runnable)
- Demo login (any seeded owner): e.g. `sara.malik@demo.circlo.pk` / `circlo123`
  (seeded owners are pre-approved, so they skip `/verify`)
- To test the verification flow: sign up a new account (starts unverified),
  try `/listings/new` → redirected to `/verify` → upload any CNIC/selfie
  images → then log in as an admin (`flask shell` and set `role='admin'`,
  `verification_status='approved'` on a user) → `/admin/verify` → Approve/Reject.
- Tests: `docker compose exec app python -m pytest -q` (20 passing)
