# PROGRESS — CIRCLO

_Claude Code: read this at the START of each session to restore state, and UPDATE it
at the END (what got done, what's next, any blockers). Keep it short and current.
The real source of truth is the code + git history; this file just helps orient fast._

## Render deployment (in progress)
- **R2 storage compatibility**: `app/services/storage.py` now uses
  virtual-hosted addressing (`addressing_style="virtual"`) when
  `STORAGE_ENDPOINT_URL` contains `r2.cloudflarestorage.com`, path-style for
  local MinIO. `presigned_url()` returns a direct `STORAGE_PUBLIC_URL/<key>`
  URL (no signing) when that URL is an R2 `.r2.dev` public domain, since
  those hosts serve unauthenticated and don't accept a bucket-subdomain
  prefix or signature — real presigned requests otherwise. `render.yaml`
  added (web service + managed Postgres, storage vars marked `sync: false`
  for manual entry in the Render dashboard).
- **Buckets**: consolidated to exactly two — `circlo-public` (listing
  images) and `circlo-private` (CNIC/selfie documents); the old
  `circlo-images` bucket is retired. `.env.example` / `.env` updated.
  Verified via `flask shell`-style scripts: `head_bucket` + full
  put/get/delete round-trip passes on both buckets against real R2
  credentials.
- **Known blocker**: the public `.r2.dev` URL in `.env` still 403s —
  `circlo-public`'s "Public Development URL" needs to be enabled in the
  Cloudflare dashboard (R2 → circlo-public → Settings) and the resulting
  `pub-xxxx.r2.dev` domain copied into `STORAGE_PUBLIC_URL`. Not yet
  confirmed working end-to-end.
- **Entrypoint fix** (`docker/entrypoint.sh`): the "wait for Postgres" step
  used to hardcode `postgres:5432` (the Docker Compose service name), which
  fails on Render — there is no such host. Now parses host/port out of
  `DATABASE_URL` (what Render actually sets) via `urllib.parse`, falling
  back to `postgres:5432` if unset. `POSTGRES_HOST`/`POSTGRES_PORT_INTERNAL`
  (set explicitly in `docker-compose.yml`) still take precedence locally, so
  Compose behaviour is unchanged. Verified both paths: local `docker compose
  up --build` logs `resolved Postgres host: postgres:5432` and boots clean
  (`/health` → 200); a simulated Render-style `DATABASE_URL`
  (`...@dpg-xxx.oregon-postgres.render.com:5432/...`) with `POSTGRES_HOST`
  unset correctly resolves to that external host.
- **Next**: enable the R2 public dev URL (above), then a real Render deploy
  attempt to confirm the Postgres-wait fix resolves the original
  `[entrypoint] ERROR: Postgres did not become ready in time` failure.

## Current milestone: M3 — Booking core (rental state machine, DONE ✅)
_(Front half of the lifecycle only — request → owner accept/reject/cancel. No
payments (M4), no handover evidence (M4), no availability calendar UI yet.)_

## Done — M3 (booking core)
- **`Booking` model** (`app/models/booking.py`, blueprint §5): `listing_id`,
  `renter_id`, `owner_id` (denormalised from `listing.owner_id` for fast owner
  queries), `status` (`requested`/`accepted`/`cancelled` — PAID/HANDED_OVER/
  ACTIVE/RETURNED/COMPLETED/DISPUTED land with M4/M5), `rental_date_start`,
  `rental_date_end`, `deposit_amount` (snapshotted from the listing at request
  time so later listing edits don't rewrite existing bookings),
  `message_from_renter`, `created_at`. Migration `7c3f9a1b2e4d` (hand-written in
  the style of the existing migrations — Docker/Postgres wasn't available in
  this environment to autogenerate; **run `flask db upgrade` and sanity-check
  the generated DDL once you're back on Docker**).
- **Booking service** (`app/services/booking.py`, API-reusable):
  `request_to_rent` (rejects renting your own listing, past start dates, end <
  start), `accept`/`reject` (owner-only, only from `requested`, `accept` also
  rejects if another `accepted` booking on the same listing overlaps the
  dates), `cancel` (renter or owner, from `requested` or `accepted`), plus
  query helpers for the owner's pending/active requests and the renter's
  pending/active/history lists. Custom exceptions
  (`InvalidBookingRequest`/`BookingPermissionError`/`InvalidBookingTransition`/
  `BookingConflict`) mirror the pattern in `services/auth.py`/`verification.py`.
- **Routes** (`app/web/booking.py`): `POST /listings/<id>/request` (login +
  identity-verification gated, same pattern as listing creation — the
  `/verify` copy already promised "list items and rent from others"),
  `POST /bookings/<id>/accept|reject|cancel`, `GET /my-rentals`.
- **UI**: listing detail's "Request to Rent" button now opens a real `<dialog>`
  modal (start/end date + optional message) posting to the request route;
  shows a login link when logged out and "This is your own listing" for the
  owner. `/my-rentals` (`templates/rentals/my_rentals.html`) shows, as owner:
  pending requests (Accept/Reject), active rentals (return date), and a
  reference list of your listings; as renter: pending/active/history with a
  Cancel action. Nav (`base.html`) gained a "My Rentals" link next to "My
  Listings".
- **Tests**: `tests/test_booking.py` — request requires login/verification,
  can't rent your own listing, request creates a `requested` booking with the
  deposit snapshot, owner accept/reject, non-owner can't accept (403), renter
  can cancel, **accept rejects a second overlapping-dates request** (stays
  `requested`), `/my-rentals` requires login and renders both sections. 11 new
  tests, all passing locally (in-memory SQLite, no Docker needed for these).
- Verified via `pytest` locally (Docker/MinIO weren't available in this
  session) — **28 passing** overall; the only failures are the 3 pre-existing
  `test_verification.py` tests that upload to MinIO and need
  `docker-compose up` to reach the storage endpoint. Re-run the full suite in
  the container to confirm those still pass and to smoke-test the new flow
  live over HTTP (see commands below) before calling this fully verified.

### Known follow-ups
- No cancellation-policy enforcement (e.g. no late-cancellation fee) — that's
  a business decision + M4 money work.
- No availability calendar on the listing page yet — a renter only finds out
  about a date conflict when the owner tries to accept a second overlapping
  request.
- `/my-rentals` re-queries on every load; fine at this scale, revisit if it
  ever needs pagination.
- Booking migration was hand-written (no Docker/Postgres locally this
  session) — confirm `flask db upgrade` applies cleanly against real Postgres.

## Seed data — real photos (post-M1 part 2)
- `app/services/seed.py` now downloads a real, hand-picked cover photo per
  listing from Unsplash's public CDN (`images.unsplash.com`, no API key) and
  pushes it through the existing storage service — full pipeline: download →
  upload to MinIO → stored key → runtime presigned URL. Falls back to the old
  SVG placeholder per-listing if a fetch fails, so `flask seed` never hard-fails
  offline. No new dependency — stdlib `urllib` only.
- Re-run: `docker compose exec app flask seed`. Verified live: all 11
  `cover.jpg` requests return 200 `image/jpeg` from MinIO, and photos genuinely
  match their listing (DEWALT-style drill, Canon body, PS5, DJI quadcopter, red/gold
  bridal wear, etc.) — not generic per-category stock art.

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
- Confirm the hand-written `7c3f9a1b2e4d` migration applies cleanly against
  real Postgres once Docker is available again (it was written without a
  live DB to autogenerate against — see M3 follow-ups above).

## Next up
- Phone OTP + email verification (need an SMS/email provider — blocked, see below).
- Add CSRF protection to all forms (Flask-WTF) — see follow-ups above.
- CNIC/selfie retention policy (delete raw docs after approval?) — blueprint §8.
- M4 Money & evidence: ledger, semi-manual deposit/payment, before/after
  evidence upload, payout-minus-commission, refunds — moves accepted bookings
  through PAID/HANDED_OVER/ACTIVE/RETURNED/COMPLETED.

## Blockers / decisions needed
- SMS provider for OTP (recurring cost) — pick before phone verification lands.
- Payment approach for MVP: semi-manual vs gateway (Safepay / JazzCash / Easypaisa).
- Full open-decisions list: CIRCLO_Technical_Blueprint.md §13.

## Reference
- Architecture + milestones: CIRCLO_Technical_Blueprint.md
- Milestone task list: CIRCLO_Progress_Tracker.xlsx
- Run: `cp .env.example .env && docker compose up --build` → http://localhost:5000
- **Quick test setup** (pre-verified users + sample listings):
  `docker compose exec app flask seed-test-accounts`
  Then log in as:
  - Regular user: `user@circlo.test` / `testpass123`
  - Admin: `admin@circlo.test` / `adminpass123`
- **Full demo data** (many owners + listings):
  `docker compose exec app flask seed` (idempotent; re-runnable)
  Demo login (any seeded owner): e.g. `sara.malik@demo.circlo.pk` / `circlo123`
  (seeded owners are pre-approved, so they skip `/verify`)
- To test the verification flow: sign up a new account (starts unverified),
  try `/listings/new` → redirected to `/verify` → upload any CNIC/selfie
  images → then log in as an admin (`flask shell` and set `role='admin'`,
  `verification_status='approved'` on a user) → `/admin/verify` → Approve/Reject.
- To test the booking flow: as a verified owner, create a listing; log in as a
  second verified user and open that listing → "Request to Rent" → pick dates
  → submit → `/my-rentals` shows it pending for the renter. Log back in as the
  owner → `/my-rentals` shows it under "Pending requests" → Accept (or
  Reject). Try requesting overlapping dates on the same listing from a third
  user and accepting both — the second Accept is refused with "already booked
  for overlapping dates".
- Tests: `docker compose exec app python -m pytest -q` (31 total: 28 passing;
  the 3 `test_verification.py` failures without Docker are pre-existing —
  they upload to MinIO and need `docker-compose up`, not a booking regression)
