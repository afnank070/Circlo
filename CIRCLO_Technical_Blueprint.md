# CIRCLO — Technical Blueprint (MVP)

**Version 0.1 — Engineering draft**
**Owner: Afnan (Web)  ·  Companion: Abdullah (Mobile)**

> This is the technical counterpart to the founding business docs. It exists to
> turn the idea into something buildable: it fixes the stack, defines the MVP
> boundary, models the core domain, and lays down rules that prevent the two
> problems from the last project (hard-coded URLs and messy deployment). Treat it
> as a living document — it will change as we learn.

---

## 1. What CIRCLO is (one paragraph)

A peer-to-peer rental marketplace for Pakistan (launching in Islamabad +
Rawalpindi). Item owners list under-used things (power tools, cameras, camping
gear, consoles, formal wear, etc.); renters book them for short periods. CIRCLO
holds the rental payment and a security deposit, provides identity verification
and a before/after evidence trail, takes a **20% commission** on each rental, and
backs the whole thing with a trust & safety fund so users feel their property is
protected.

---

## 2. MVP scope — the single most important decision

The goal is **the smallest system where one real, safe rental can happen end-to-end
in the twin cities.** Everything else waits. Traction (completed rentals) is what
NIC / investors will look at, so the MVP must be able to *complete rentals*, not
just collect signups.

### In scope (MVP)
- Sign up / log in (email + phone OTP).
- **Manual identity verification**: user uploads CNIC photo + selfie; an admin
  approves. Verification gates the ability to list or rent. (Automated CNIC /
  liveness checks are expensive and hard — do them by hand at first.)
- Create a listing: photos, description, category, price/day, deposit amount,
  city + area, availability dates.
- Browse / search: by category, city/area, price, availability.
- Rental request → owner accepts or rejects.
- Collect rental payment + deposit (see §7 — this is the hard part).
- Handover evidence: photos/short video *before*, uploaded by both parties.
- Return evidence: photos/short video *after*, uploaded by both parties.
- Owner confirms return → deposit released to renter, payout to owner minus 20%.
- Mutual reviews / ratings after completion.
- **Admin panel**: verify identities, moderate listings, resolve disputes, trigger
  payouts/refunds from the trust fund.
- Notifications: email for events, SMS for OTP.

### Explicitly OUT of MVP (deferred, but not forgotten)
- Native mobile apps — but the backend is built API-first so Abdullah can consume it.
- Automated CNIC / face-liveness verification.
- Real-time in-app chat (MVP: reveal contact number after acceptance, or a simple
  message thread).
- Courier / delivery — handled manually and off-platform, per the instructions doc.
- Featured listings, subscriptions, rental-protection plans (future revenue).
- Multi-city beyond Islamabad/Rawalpindi.

**Rule of thumb:** if a feature isn't required for one rental to complete safely,
it is not MVP.

---

## 3. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | Your preference; one language across web + services. |
| Web framework | **Flask** (application-factory + blueprints) | Lightweight, you know it, avoids the Node integration pain. |
| API | **Flask REST blueprint (`/api/v1`)** returning JSON | The mobile app reuses this. See §5. |
| Web UI | **Jinja2 templates + HTMX + Tailwind (CDN for MVP)** | Dynamic feel without a heavy JS SPA. Fast for a solo dev, no build tooling headache. |
| ORM | **SQLAlchemy + Flask-Migrate (Alembic)** | DB-agnostic code, versioned schema migrations. |
| Database | **PostgreSQL** (same in dev via Docker and in prod) | Handles concurrent bookings/deposits properly; avoids SQLite-vs-Postgres surprises. |
| Object storage | **S3 API** via `boto3` — **MinIO** locally, **Cloudflare R2** when deployed | One codebase, swap by env var. See "Storage strategy" below. |
| Auth | **Flask-Login (sessions)** for web now; **JWT** added for the API when mobile starts | Simple now, extensible later. |
| Config | **python-dotenv + a `Config` class**, all values from env vars | Kills hard-coded URLs. See §9. |
| Containers | **Docker + docker-compose** (app + postgres + minio) | Dev environment == prod environment. Solves the deployment mess. |
| Web server (prod) | **Gunicorn behind Nginx**, TLS via Let's Encrypt | Standard, cheap, runs on a Contabo VPS. |
| Hosting | **Contabo VPS** with Docker Compose | Not Vercel — Vercel is a poor fit for a stateful Flask + Postgres + MinIO app. |
| Version control | **GitHub from commit zero** | Collaboration with Abdullah + clean deploys. |

**On SQLite vs PostgreSQL:** use Postgres everywhere. Because the code goes
through SQLAlchemy, you never write raw SQL that ties you to one DB, but running
SQLite locally and Postgres in prod hides bugs until deploy. Docker gives you a
real Postgres locally with zero manual install. (Free managed Postgres options if
you ever don't want to self-host: Neon or Supabase.)

**Storage strategy (MinIO vs cloud):** MinIO is *self-hosted* S3-compatible storage
— it needs a machine with a persistent disk, so it works on your own machine and on
the Contabo VPS, but **not** on Render's free tier (ephemeral disk wipes it on every
restart). Because MinIO, Cloudflare R2, Backblaze B2 and AWS S3 all speak the *same
S3 API*, the app uses one `boto3`-based storage service and picks the backend purely
from environment variables (endpoint + keys). Recommended setup:

- **Local development:** MinIO in Docker Compose — free, offline, no account needed.
- **Anything deployed (Render demo + Contabo prod):** **Cloudflare R2** free tier —
  10 GB storage, 1M writes + 10M reads/month, and **zero egress fees** (important for
  an image-heavy app; serving listing photos never incurs bandwidth charges). Needs a
  card on file to enable, but isn't charged under the free limits.
- Alternatives if avoiding a card: **Backblaze B2** (~10 GB free) or **Supabase
  Storage** (~1 GB free, bundles Postgres too).
- **Simplest option:** because R2 is S3-compatible and ~\$0.015/GB beyond the free
  tier, you may skip self-hosting MinIO entirely and use R2 everywhere — one less
  service to run. Store only the **object key** in the DB (never a full URL) so the
  backend is swappable without touching data (§9).

**Key points to avoid confusion:**
- **MinIO is the zero-setup development stand-in for S3.** It needs no account and no
  cloud setup — it already runs in Docker Compose. Use it for the entire dev phase; no
  need to set up AWS S3 to start building.
- **AWS S3 is a valid deployed target too** (the founders' eventual goal). Because it's
  the same S3 API, moving dev-MinIO → AWS S3 (or R2) later is an env-var change, not a
  code rewrite. Trade-off vs R2: S3 charges for egress (bandwidth out), which adds up
  for an image-heavy app — R2 does not. Either works; the code doesn't change.
- **Never store image bytes in the database.** Postgres *can* hold binary blobs, but
  for an image-heavy app it bloats the DB, slows queries, and makes backups huge. Files
  go to object storage; the DB holds only the small text **object key** that points to
  them.
- **Neither Docker nor MinIO causes slowness.** Any "slowness" discussed elsewhere
  refers only to Render's *free tier* sleeping after inactivity — a hosting-tier trait,
  not a Docker or MinIO trait. Both run at full speed locally and on a VPS.

---

## 4. Why API-first matters for you specifically

You said this becomes a mobile app and Abdullah is starting app development. That
one fact drives the architecture. If the web app and its logic are tangled
together, the mobile app has nothing clean to talk to and you rebuild everything.

The fix is a **service layer**: all business rules (create booking, hold deposit,
release funds, verify user) live in plain Python modules. Two thin layers sit on
top and both call those services:

```
                 ┌──────────────────────┐
   Web browser → │  Web routes (Jinja)  │ ─┐
                 └──────────────────────┘  │
                                           ├─→  Services (business logic)  →  DB / MinIO
                 ┌──────────────────────┐  │
   Mobile app  → │  API routes (/api/v1)│ ─┘
                 └──────────────────────┘
```

Write the logic once. The web renders HTML; the API returns JSON; both are just
adapters. This is the single most valuable structural decision in the whole
project.

---

## 5. Core data model (starting point)

Entities (SQLAlchemy models):

- **User** — name, email, phone, password hash, role (user/admin),
  `verification_status` (pending/approved/rejected), created_at.
- **IdentityDocument** — user_id, cnic_image_key, selfie_image_key, status,
  reviewed_by, reviewed_at. *(Sensitive — see §8.)*
- **Category** — name, slug.
- **Listing** — owner_id, title, description, category_id, city, area,
  price_per_day, deposit_amount, status (draft/active/paused/removed), created_at.
- **ListingImage** — listing_id, object_key, sort_order.
- **Availability** — listing_id, date ranges the item is free / already booked.
- **Booking / Rental** — the heart of the system (state machine below).
- **EvidenceMedia** — booking_id, phase (before/after), uploaded_by, object_key,
  media_type (photo/video).
- **Payment / LedgerEntry** — booking_id, type (rental/deposit/commission/payout/
  refund), amount, status, provider_reference.
- **Review** — booking_id, author_id, subject_id, rating, comment.
- **Dispute** — booking_id, opened_by, reason, status, resolution, amount_from_fund.

### The rental lifecycle (state machine)

This is the domain's spine. Define it explicitly so nothing is ambiguous:

```
REQUESTED
   → (owner accepts)        ACCEPTED
   → (renter pays)          PAID          (rental + deposit held by CIRCLO)
   → (before-evidence)      HANDED_OVER
   →                        ACTIVE
   → (item returned)        RETURNED      (after-evidence uploaded)
   → (owner confirms)       COMPLETED     (deposit released, owner paid minus 20%)

   Side paths:
   REQUESTED/ACCEPTED  → CANCELLED   (by either party, per cancellation policy)
   any active state    → DISPUTED    (→ admin resolves → COMPLETED / refund from fund)
```

Every transition should be a service function with clear pre-conditions.

---

## 6. Trust & safety framework (the four layers — reconciled)

⚠️ **Your two documents disagree on what the four layers are.** The overview lists
(Identity, Secure Payments, Reviews, Deposits). The instructions list (Identity,
Security Deposit, Evidence System, Trust Fund). These need to be one canonical
list. Proposed reconciliation — treat trust as **five mechanisms**, four of them
the headline "layers":

1. **Identity verification** — phone OTP + email + manual CNIC/selfie review. (Bank/
   wallet link comes with payments.)
2. **Security deposit** — a % of item value, scaled by value; held by CIRCLO,
   returned on clean return.
3. **Evidence system** — before/after photos & video from *both* parties, stored
   immutably in MinIO, timestamped. This is your best defence in disputes.
4. **Trust & Safety Fund** — 700k–1,000,000 PKR reserve to compensate theft/damage/
   fraud and keep user confidence. Tracked as a ledger, drawn down via the admin
   panel during dispute resolution.
5. **Reviews & ratings** — reputation that compounds over time.

Decide the canonical wording and update both business docs so the story is
consistent for investors.

---

## 7. Payments, deposits, commission — the hardest part (read carefully)

This is the biggest unknown and the thing most likely to block launch, so treat it
as its own workstream, not a checkbox.

**What CIRCLO needs to do:** collect rental + deposit up front, *hold* both,
release the deposit to the renter and pay the owner (minus 20%) on a clean return,
or draw on funds/the trust fund on a dispute. That "hold money for others" behavior
is **escrow**, and in Pakistan holding third-party funds touches SBP regulation —
worth being aware of even for a small pilot.

**Options, cheapest-first:**
- **Semi-manual (recommended to *start*):** renter pays into CIRCLO's account
  (bank transfer / JazzCash / Easypaisa); admin confirms receipt in the panel;
  releases/refunds are triggered manually. Ugly but lets you validate real demand
  with near-zero integration.
- **Payment gateway:** Safepay (developer-friendly, cards + wallets) or a direct
  JazzCash/Easypaisa merchant integration. Cleaner UX, needs merchant onboarding
  and likely a registered business + bank account.

**MVP recommendation:** build the ledger model now so every rupee is *tracked* in
the DB from day one, but keep the *movement* of money semi-manual behind an admin
action until traction justifies a real gateway. Design the payment service with a
`PaymentProvider` interface so a gateway can be dropped in without touching booking
logic.

**Open questions to resolve with your co-founders:** Is there a registered business
+ business bank account? Deposit %s per item-value band? Cancellation/refund policy?
Payout timing to owners? These are business decisions the code must encode.

---

## 8. Privacy & security (don't skip — CNIC is sensitive)

- **CNIC and selfie images are highly sensitive PII.** Store them in a *private*
  MinIO bucket, access only via short-lived presigned URLs, restrict to admins,
  and set a retention policy. Consider keeping only `verification_status` long-term
  and deleting raw documents once approved. This is legal exposure, not just good
  practice.
- Passwords hashed (Werkzeug / bcrypt), never stored plain.
- All secrets in env vars, never in the repo (see §9).
- HTTPS everywhere in prod (Let's Encrypt).
- Rate-limit auth and OTP endpoints.
- Evidence media should be write-once (don't allow overwrite/delete by users) so it
  holds up in disputes.

---

## 9. Configuration rules — killing the hard-coded-URL problem

The last project broke on deploy because of hard-coded paths/URLs. These rules
prevent it:

1. **Nothing environment-specific is written in code.** Base URLs, DB DSN, MinIO
   endpoint + keys, secret keys, SMS/email creds → all read from environment
   variables through a single `Config` class (`DevConfig`, `ProdConfig`).
2. **Never store full URLs in the database.** For any file, store only the MinIO
   **object key** (e.g. `listings/8f2/photo1.jpg`). Build the URL at runtime with a
   presigned-URL helper that reads the endpoint from config. Move servers → nothing
   in the DB breaks.
3. **Internal links use Flask's `url_for()`**, never string-built paths.
4. **Commit a `.env.example`** with dummy keys; the real `.env` is git-ignored.
5. **The frontend never hard-codes the API host** — it uses a relative `/api/v1`
   path (web) or a single configurable base URL (mobile).

Get these right on day one and deployment stops being a rewrite.

---

## 10. Suggested repository structure

```
circlo/
├─ app/
│  ├─ __init__.py          # application factory
│  ├─ config.py            # Config / DevConfig / ProdConfig (reads env)
│  ├─ extensions.py        # db, migrate, login_manager, etc.
│  ├─ models/              # SQLAlchemy models
│  ├─ services/            # business logic (booking, payments, storage, verify)
│  ├─ web/                 # Jinja routes (blueprints) + templates
│  ├─ api/                 # /api/v1 JSON routes (blueprints)
│  └─ admin/               # admin panel
├─ migrations/             # Alembic
├─ tests/
├─ docker-compose.yml      # app + postgres + minio
├─ Dockerfile
├─ .env.example
├─ requirements.txt
└─ README.md
```

---

## 11. Local dev & deployment

- **Local:** `docker-compose up` starts Flask + Postgres + MinIO together. Same
  images run in production, so "works on my machine" stops being a category of bug.
- **Migrations:** `flask db migrate` / `flask db upgrade` (Alembic) — never edit the
  DB by hand.
- **Prod (Contabo):** same compose file, Gunicorn behind Nginx, Let's Encrypt TLS,
  a managed or containerized Postgres volume with backups.
- **CI later:** GitHub Actions to run tests on push.

### Hosting choice — dev vs production

| | Render (free) | Vercel (free) | Contabo VPS (~$5–8/mo) |
|---|---|---|---|
| Fit for Flask + Postgres + MinIO | partial | poor | **good** |
| Cold starts | 15-min sleep → 30–60s wake | n/a (serverless) | none (always on) |
| Data persistence | free Postgres **auto-deleted ~30 days**; filesystem wiped on redeploy | no persistent DB/storage | full persistent disk |
| Can host MinIO | no (ephemeral disk) | no | yes |
| Cost to be production-safe | ~$13/mo (Starter web $7 + Postgres $6) | n/a for this stack | ~$5–8/mo, one box runs everything |

**Decision:** use **Render's free tier for early dev + demos only** — it's genuinely
handy for pushing a live, shareable URL (e.g. to show co-founders or NIC) at zero
cost, *as long as you treat its database as throwaway* (it's deleted ~monthly and
the filesystem is ephemeral). **Do the real soft launch on a Contabo VPS.** A single
~$5–8/mo box runs Flask + Postgres + MinIO together via the same Docker Compose file,
has no cold starts, and keeps data and images persistent. Skip Vercel for the backend
— it's built for static/serverless frontends, not a stateful Flask app.

Reality check: there is **no truly-free option that persists real data and serves
images reliably.** The ~$5–8/mo VPS is the practical floor for a real marketplace —
cheap enough to fit the no-investment constraint.

---

## 12. Build roadmap (rough milestones)

1. **Foundation** — repo, Docker compose, app factory, config, DB connection, MinIO
   connection, user auth (signup/login/OTP). *Prove the plumbing works and deploys.*
2. **Identity + Listings** — manual verification flow + admin approval; create/browse
   listings with image upload to MinIO; search by category/city/price.
3. **Booking core** — the rental state machine, availability, requests, accept/reject.
4. **Money + evidence** — ledger, deposit/payment (semi-manual), before/after
   evidence, payout-minus-commission, refunds.
5. **Trust polish** — reviews/ratings, disputes + trust-fund drawdown, notifications.
6. **API hardening + mobile handoff** — stabilise `/api/v1`, add JWT, give Abdullah
   the API contract.

Run the **demand survey in parallel** with milestone 1 — don't wait for the build to
validate whether people will rent to strangers. And start gathering the **75–100
seed listings** early; an empty marketplace kills launch.

---

## 13. Open decisions to resolve (bring these to your co-founders)

- Canonical definition of the four trust layers (docs currently conflict).
- Payment approach for MVP (semi-manual vs gateway) + is there a registered business/bank account?
- Deposit percentage bands by item value.
- Cancellation & refund policy.
- Where the initial trust-fund capital comes from and how it's accounted.
- Handling of CNIC data retention (store vs delete-after-approval).
- Handover model for MVP: in-app chat vs reveal-contact-after-acceptance.

---

## 14. Immediate next step

Set up the **GitHub repo + Docker skeleton + config layer** (milestone 1
foundation) before writing any feature. That single step bakes in the anti-hard-code
rules and gives every later prompt a clean place to land.
