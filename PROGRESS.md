# PROGRESS — CIRCLO

_Claude Code: read this at the START of each session to restore state, and UPDATE it
at the END (what got done, what's next, any blockers). Keep it short and current.
The real source of truth is the code + git history; this file just helps orient fast._

## Standardized area vocabulary + working location filter (DONE ✅, 2026-09-07)

`listings.area` was free text typed by owners, so the browse filter couldn't
match "F-7" vs "F7" vs "F-7 Islamabad". Fixed by making area a fixed
vocabulary.

### The vocabulary
- **`app/services/areas.py`** — `CANONICAL_AREAS`: ~90 real Islamabad &
  Rawalpindi sectors/neighbourhoods (E/F/G/H/I/D sector series, Blue Area,
  DHA phases, Bahria Town + phases, Gulberg Greens/Residencia, Bani Gala,
  Bhara Kahu … / Saddar, Satellite Town, Chaklala schemes, Cantt, Westridge,
  Askari, Committee Chowk, Dhoke *, Murree Road …). Single source of truth
  for validation, dropdown rendering, and legacy remapping. Functions:
  `is_valid_area`, `city_for_area`, `areas_by_city` (optgroup source, falls
  back to the frozen list if the table is empty), `closest_area` (fuzzy map
  of legacy free text → canonical), `sync_areas` (idempotent upsert into DB).
- **`areas` reference table** (`app/models/area.py`) — `name` (the stored
  value), `slug`, `city`, `sort_order`. Migration **`e7a2c4b9f1d3`**
  (revises `d4f1a7c9e2b6`) creates it, populates it from `CANONICAL_AREAS`,
  then **remaps every existing listing** — `area` → `closest_area(...)`,
  `city` re-derived from that area. `flask seed` also calls `sync_areas()` and
  maps its 11 demo listings the same way.

### City is now derived from area
`listings_service._resolve_area()` validates the area and returns
`(area, city)` where city comes from the area — the two can't drift.
`create_listing` / `update_listing` raise the new `InvalidArea` on anything
off-list. The `city` kwarg is kept in the signatures (API compat) but ignored.

### Browse filter actually filters
- `browse_listings(..., area=?, city=?)` — `area` is an **exact** match on
  `Listing.area` (both sides now come from the same vocabulary), `city`
  narrows to one city. `web.index` reads `?area=` / `?city=` and passes
  `active_area` / `active_city`; category pills + the search form preserve the
  chosen area.
- The homepage's dead **"All areas"** `<span>` is now a real
  `<select name="area">` grouped by `<optgroup>` per city
  (`_partials/area_select.html`).

### Form: searchable dropdown, no free typing
- `listings/form.html` — the free-text area `<input>` is replaced by the same
  `area_select` macro (native `<select>`, optgroup per city). The City select
  is gone (derived from area).
- **`base.html`** carries a small progressive-enhancement script: it turns any
  `[data-area-combobox]` into a type-to-filter dropdown (filter the list as
  you type; you can still only pick a listed area). No JS → the native select
  still works (native type-to-jump, zero free typing).

### Verification
- **New tests** `tests/test_area_filter.py` (17): canonical list covers both
  cities; `is_valid_area` rejects "F7" / "F-7 Islamabad"; `closest_area` maps
  the common variants + falls back safely; `browse_listings` filters by exact
  area with **no cross-contamination** (F-7 filter never returns F-8), by
  city, and combined with category; archived listings excluded; create/update
  reject off-list areas and derive city; `/?area=F-7` route filter; the
  dropdown HTML is grouped by city; the listing form's area is a `<select>`
  not a text input; a free-text POST is rejected; `sync_areas` is idempotent;
  every seeded listing ends up canonical. **117 tests pass** (was 100).

## Stage-aware booking cancellation flow (DONE ✅, 2026-09-07)

Cancellation rules now depend on how far the booking has progressed
(blueprint §5, §7). All logic in `app/services/cancellation.py`.

### Rules by stage
- **REQUESTED / ACCEPTED** (`booking_service.FREE_CANCEL_STATUSES`) — either
  party cancels instantly via `booking_service.cancel()`. No money involved:
  booking → CANCELLED, the *other* party is emailed
  (`notifications.booking_cancelled`). `cancel()` was tightened — it used to
  also allow AWAITING_PAYMENT; that path now goes through the request flow.
- **AWAITING_PAYMENT / PAID** (`cancellation.ADMIN_CANCEL_STATUSES`) — money
  has moved, so an instant cancel is refused. Either party raises a
  **`CancellationRequest`** (`pending`) via
  `cancellation.request_cancellation()`; the other party is emailed
  (`notifications.cancellation_requested`). An admin then either:
  - **confirms** (`confirm_cancellation`) — records a matching **confirmed
    `refund` ledger entry** for whatever the renter actually paid in
    (`refundable_amount()` = confirmed `rental_payment` + `deposit` entries;
    zero if an AWAITING_PAYMENT booking was never payment-confirmed), moves
    the booking to CANCELLED, emails both parties. Reuses the M4
    manual-refund pattern (`ledger_service.record(..., TYPE_REFUND,
    status=confirmed)`).
  - **declines** (`reject_cancellation`) — request → `rejected`, booking
    untouched, requester emailed.
- **HANDED_OVER / ACTIVE / RETURNED** (`cancellation.DISPUTE_ONLY_STATUSES`) —
  the item is physically exchanged; cancellation is gone. Users are pointed at
  the existing dispute flow ("Report a problem").
- **COMPLETED / CANCELLED** — nothing offered.

### Surfacing the right control (`/my-rentals`)
`cancellation.available_action(booking, user)` → `"cancel"` / `"request"` /
`"pending"` / `"dispute"` / `None`. `web.my_rentals` computes it (plus the
open `CancellationRequest`) into `booking_detail`; the new
`cancellation_controls` macro in `rentals/my_rentals.html` renders, on each
in-flight booking row: an instant **Cancel booking** button, a **Request
cancellation** disclosure (with an optional reason box), a "cancellation
requested — admin is on it" note, or the "can't be cancelled, use Report a
problem" hint.

### Admin
New **Cancellation requests** section on `/admin/payments` (routes
`POST /admin/cancellations/<id>/confirm|reject` in `app/admin/payments.py`) —
lists each pending request with the booking's ledger, the exact refund amount
to send, and Confirm / Decline buttons.

### Schema
- **`cancellation_requests`** table — migration `d4f1a7c9e2b6` (revises
  `a3d8e1f4c6b7`, hand-written in the existing style). Columns: `booking_id`,
  `requested_by`, `reason` (nullable), `status`
  (`pending`/`confirmed`/`rejected`), timestamps, `resolved_by`. **Run `flask
  db upgrade` + sanity-check on Docker/Postgres.**
- New model `app/models/cancellation_request.py`, registered in
  `app/models/__init__.py`.

### New web/notification pieces
- `POST /bookings/<id>/request-cancellation` (`web.request_booking_cancellation`).
- `notifications.booking_cancelled` / `cancellation_requested` /
  `cancellation_confirmed` / `cancellation_rejected` — all `@_safe`,
  best-effort like the rest.

### Verification
- **New tests** `tests/test_cancellation.py` (15): free cancel at
  REQUESTED/ACCEPTED (+ other-party email); instant cancel refused once
  AWAITING_PAYMENT; request creates pending + notifies; double-request
  rejected; admin confirm records the full refund entry + cancels + emails
  both; admin decline leaves the booking PAID; AWAITING_PAYMENT-never-confirmed
  refund is zero; ACTIVE booking can't be cancelled (dispute instead);
  COMPLETED offers nothing; non-party blocked; `/my-rentals` shows the right
  control per stage; the request route + the admin confirm route end-to-end.
- **100 tests pass** (was 85).

## Account dropdown "Profile" link + profile/account page (DONE ✅, 2026-09-07)

### 1. "Profile" link in the account dropdown
`base.html`'s account menu (`<details>` dropdown) was missing a Profile entry —
it went straight from the name/email header to My Rentals. Added
`<a href="{{ url_for('web.user_profile', user_id=current_user.id) }}">Profile</a>`
as the first item under the header, linking to the existing public profile
route (`GET /users/<id>`).

### 2. Profile page now doubles as the account page (own view only)
`users/profile.html` already had a public profile (avatar, verified badge,
combined rating, joined date, reviews list) plus a self-only "Your contact
number" phone form. Extended the self-only region — nothing public changed —
with what was missing:
- **Editable name / email / phone** — the phone-only form became an "Account
  details" section (`POST /account` → new `web.update_account`). Backed by
  `auth_service.update_account(user, name, email, phone)`, which rejects an
  email already registered to another account (`EmailAlreadyRegistered`). The
  old `POST /account/phone` route is kept (unused by the template now, no
  callers removed).
- **Verification prompt** — a self-only amber panel shows when
  `not is_verified`, linking to `/verify`, with distinct copy for the
  `rejected` vs `pending` case. The existing green ✓ Verified badge in the
  header already covers the approved case.
- **Rating breakdown** — new `reviews_service.rating_breakdown(user)` groups
  received reviews by `Review.direction` into `as_owner`
  (`renter_on_owner`) / `as_renter` (`owner_on_renter`) / `overall`, each a
  `(Decimal|None, count)`. Rendered as a two-card "Reputation" section (shown
  to everyone; the header keeps the combined star). "No reviews yet" per card
  when empty.
- **Change password** — new `GET/POST /account/password`
  (`web.change_password` + `users/change_password.html`), backed by
  `auth_service.change_password(user, current, new)` which raises
  `IncorrectPassword` on a bad current password. The link and the route are
  **hidden / 404 for OAuth-only accounts** (`not current_user.has_password`).

### Verification
- **New tests** (`tests/test_profile_account.py`, 13): dropdown contains the
  Profile link → own `/users/<id>`; own profile renders the name/email/phone
  form + rating breakdown; verify prompt shows for pending & rejected, badge
  (no prompt) for approved; `POST /account` updates all three fields and
  rejects a duplicate email; change-password page loads, updates the hash,
  rejects a wrong current password; change-password link absent and route
  404s for an OAuth-only user. **85 tests pass** (was 72).
- Styled with the v3 "Organic Forest" tokens + spacious-section layout
  (labelled sections, `rounded-full` pill inputs, `bg-surface` cards) to match
  the rest of the migrated pages.

## Font-weight verification + contact/pickup reveal (DONE ✅, 2026-09-06)

### 1. Verified (and revised) the body font-weight fix
Last session's `font-medium` (Manrope 500) body-weight change was checked
live, not just re-read from source: `getComputedStyle(document.body).
fontWeight` on `/my-rentals` confirmed it really was applying (`"500"`, not
the browser default `400`). Visually, though, 500 was still too close to
default to read as an intentional pairing against the very heavy Barlow
Condensed headings. Rendered a live side-by-side (500 vs 600 on the actual
"Manage rental requests…" subtitle) and asked which to keep — **bumped to
`font-semibold` (Manrope 600)** in `base.html` per that comparison. See
`DESIGN_SYSTEM.md` §11.

### 2. Contact reveal + pickup location (new feature)
Once a booking reaches ACCEPTED or later (not before, not if cancelled), the
renter and owner now see a "Contact & pickup" panel on their `/my-rentals`
booking row: each other's phone number and the listing's pickup location /
optional Google Maps link. Plain data reveal — **no chat, no messaging**, as
specified.
- **`users.phone`** (new, nullable — migration `a3d8e1f4c6b7`): required at
  signup going forward (`app/web/auth.py`), nullable in the DB so existing
  accounts and OAuth signups (which skip the phone step entirely — there's no
  onboarding flow for that path) don't violate a NOT NULL constraint. Users
  without a phone (or who want to change it) can set one from their own
  profile page (`/users/<id>` — a "Your contact number" panel appears only
  when viewing your own profile, posts to new `POST /account/phone`).
- **`listings.pickup_location`** (`String(160)`, optional) and
  **`listings.map_link`** (`String(500)`, optional, validated as an
  `http(s)://` URL) — new fields on the create/edit listing form
  (`listings/form.html`), persisted via `listings_service.create_listing()` /
  `update_listing()`. The map link is stored and rendered as a plain
  `target="_blank"` link — no Maps API/embed, exactly as scoped.
- **Gating lives in the service layer**: `booking_service.
  CONTACT_REVEAL_STATUSES` (accepted through completed, i.e.
  `BLOCKING_STATUSES + (COMPLETED,)`) and `can_reveal_contact(booking)`.
  `web.my_rentals` computes this per booking into `booking_detail`, same
  pattern as `can_review`/`can_dispute`; requested/cancelled bookings are
  never in that dict's "in-flight" input set, so the reveal is structurally
  absent, not just hidden by CSS.
- **Styling**: one light `bg-surface` panel per booking row (`rentals/
  my_rentals.html`'s new `contact_reveal` macro) — matches the existing
  spacious-section rows, not a dense new card.

### Verification
- **New tests** (`tests/test_contact_reveal.py`, 3 tests): phone/pickup NOT
  present in `/my-rentals` HTML while a request is still REQUESTED; both
  parties' phone + pickup details ARE present once the owner accepts (checked
  from both the owner's and the renter's view); a direct unit check of
  `can_reveal_contact()` against every status. **72 tests pass** (was 69 —
  also added `test_signup_requires_phone` and updated every existing
  `/signup` test call site across 7 files to include a phone value now that
  it's a required form field).
- **Verified live end-to-end in-browser**: confirmed the computed 600 weight
  really applies; added a pickup location + map link to a real listing;
  requested it as one user (confirmed no contact/pickup leak while pending —
  checked both rendered text and raw HTML for the phone/pickup strings);
  accepted it as the owner; confirmed the "Contact & pickup" panel appears
  correctly on **both** the owner's and the renter's `/my-rentals` view, with
  working `tel:` and map links. Used each user's own profile page to set
  their phone via the new self-edit form as part of the same walkthrough.
  Scratch DB/script discarded after — nothing committed.

### Known gap (documented, not fixed this pass)
Google OAuth signups skip the phone step entirely (no onboarding form exists
for that path) and land with `phone = NULL`. They see "no phone on file"
instead of a number until they visit their profile and add one. Building a
post-OAuth onboarding step was out of scope for this pass.

## Homepage sections, nav/typography fixes, upload-time crop (DONE ✅, 2026-09-05)

### 1. Homepage now has a real body below the item grid
`index.html` gained four full-bleed sections after the browse grid, plus a
proper footer, closing the "stops after hero + grid" gap:
- **How it works** (`#how-it-works`) — 3-step visual (Browse & request →
  Verified handover → Return & review), links out to the existing full
  `/how-it-works` page.
- **Trust & safety** (`#trust-safety`) — the 4 trust mechanisms (verified
  identities, deposit protection, evidence photos, Trust & Safety Fund)
  consolidated in one place instead of scattered across pages; links out to
  `/trust-deposits`.
- **Stats row** — real numbers, never hardcoded: `listings_service.
  total_listings_count()`, `booking_service.completed_count()`, `reviews_
  service.platform_average_rating()` (new service functions), computed in
  `web.index` and rendered as `stats.listings` / `stats.completed_rentals` /
  `stats.avg_rating`. Shows "No ratings yet" instead of a fake "0.0" or "5.0"
  when nobody's reviewed anything yet.
- **FAQ accordion** — 5 questions using native `<details>/<summary>` (no JS
  library needed; `group-open:rotate-45` on a plus icon for the expand/
  collapse affordance). Answers are grounded in real backend behavior — e.g.
  the cancellation answer matches exactly what `booking_service.cancel()`
  allows (free before payment is confirmed, locked after).
- **Footer** (`base.html`) simplified to one row: a real `© {{ current_year
  }} CIRCLO` copyright line (new `inject_current_year` context processor in
  `app/__init__.py` — never a hardcoded year) on the left, Privacy/Terms/Help
  on the right.
- "How it works" / "Trust & deposits" in the nav now link to `#how-it-works`
  / `#trust-safety` (`web.index` + anchor) instead of `#` — they scroll to
  these new sections rather than a dead link. `scroll-mt-20` on both sections
  keeps the sticky header from covering the heading on arrival.

### 2. Nav hierarchy redesigned
`base.html`'s header nav was one flat row (marketing links, a filled CTA
pill, then more plain links) that read as visually disjointed. Regrouped
left to right into three clusters: **marketing links** (How it works, Trust &
deposits), then **account links** (My Rentals, My Listings — signed-in only,
set off by a `border-l`), then the **List an item CTA pill** — now the *only*
filled pill in the nav, immediately before the avatar/sign-in. See
`DESIGN_SYSTEM.md` §12.

### 3. Body text weight fixed
Subtitle/meta text (e.g. "Manage rental requests for your items…") read as
too thin against the heavy Barlow Condensed headings. `<body>` now carries
`font-medium` (Manrope 500) as the site-wide default instead of the browser's
normal 400 — plain text with no explicit weight utility inherits this, so it
pairs properly; anything already using `font-semibold`/`font-bold` is
unaffected. See `DESIGN_SYSTEM.md` §11.

### 4. Upload-time photo crop (Cropper.js)
`listings/form.html` now intercepts the `images` file input: each newly
selected photo opens in a crop modal (Cropper.js via CDN, scoped to this page
only through new `{% block extra_head %}` / `{% block extra_scripts %}`
hooks in `base.html`) fixed to a 4:3 aspect ratio, with drag/resize and a
"Use original" skip option. The cropped canvas replaces the original `File`
via `DataTransfer` before the form submits — the server-side upload path
(`app/services/storage.py`) is untouched, it just receives different bytes.
**Not** applied to `/verify` (CNIC/selfie) or booking evidence uploads —
those stay plain file inputs, a different concern from marketplace listing
photos.
- **Now that uploads are crop-normalized, listing photo containers went
  back to `object-cover`** (from the `object-contain` pass two sessions
  ago): browse grid (card aspect changed `4/5` → `4/3` to match the crop
  ratio), My Listings, My Rentals thumbnails, listing detail hero/gallery/
  related cards, and the edit-listing existing-photo gallery. Photos
  uploaded before this feature shipped may still be off-ratio and could crop
  slightly until re-uploaded — that's expected, not a bug. See
  `DESIGN_SYSTEM.md` §0.5/§0.6.
- **Verified end-to-end in-browser**, not just code review: simulated
  selecting a real portrait photo (via `DataTransfer` + a dispatched `change`
  event — no OS file dialog needed), confirmed the crop modal opens with a
  4:3 box over the actual image, clicked "Crop & continue", verified the
  file input held a single cropped JPEG (via `input.files[0]`), filled out
  and submitted the listing form with a patched storage layer, and confirmed
  the resulting listing shows the cropped photo filling the frame with
  `object-cover` on both the listing detail page and the browse grid — no
  letterboxing, no crop mismatch. **68 tests still pass** — no backend logic
  changed.

## Listing image crop fix + profile/admin-settings v3 migration (DONE ✅, 2026-09-05)

### 1. Fixed cropped listing photos (root cause + fix everywhere)
Root cause: every place a listing photo renders used `object-cover` inside a
fixed-ratio box (`aspect-[4/5]` browse cards, `aspect-[4/3]` My Listings
cards, fixed square My Rentals thumbnails, plus listing-detail's hero/gallery/
related cards and the edit-form photo gallery — all the same pattern).
`app/services/storage.py` does no server-side resize or aspect-ratio
enforcement at upload time, so real uploads are portrait phone photos,
landscape camera photos, and square crops all mixed together — `cover` was
silently cropping whichever dimension didn't fit the box, which is what
showed up as "half the photo visible."
- **Fix**: swapped `object-cover` → `object-contain` (keeps the `bg-surface`
  fill as an intentional-looking letterbox) everywhere a *listing* photo
  renders: `index.html` (browse grid), `listings/my_listings.html`,
  `rentals/my_rentals.html` (thumbnail), `listing_detail.html` (hero image,
  3-image grid, extra-photos strip, "Also nearby" cards), and
  `listings/form.html` (existing-photos gallery on edit).
  Deliberately **left on `cover`**: CNIC/selfie verification photos
  (`admin/verify_queue.html`) and booking before/after evidence thumbnails
  (`rentals/my_rentals.html` evidence panel) — those are framed close-up
  document/condition shots, a different concern from marketplace listing
  photos, and cropping to fill the box is fine there.
- **Verified with real images of three proportions**, not just code review:
  seeded 3 listings with actual generated JPEGs (900×1600 portrait, 1600×900
  landscape, 1200×1200 square, each with a full-frame border + corner-to-
  corner crosshair so any cropping would be immediately visible), monkey-
  patched the storage layer to serve them from local disk (no MinIO needed
  for the check), and confirmed in-browser that the full photo — border and
  crosshair intact — renders on the browse grid, My Listings, My Rentals
  (both as a booking thumbnail), and the listing detail page for all three
  orientations. Scratch DB/script/images discarded after, nothing committed.
- **68 tests still pass** — this was a template-only class change, no
  route/service/model touched.

### 2. Profile + admin settings migrated to v3
Per the same spacious-sections philosophy from the previous session
(`DESIGN_SYSTEM.md` §0.4): `users/profile.html` (plain header, reviews as
divided rows instead of bordered cards) and admin `settings.html` (v3 tokens,
the payment-details form kept as a light contained panel since it collects
input). Only `auth/forgot_password.html`, `auth/reset_password.html`, and the
legal pages are still v1 navy/teal/sand.

## Layout philosophy rework: spacious sections over stacked cards (DONE ✅, 2026-09-05)
Backend logic untouched — visual/IA pass only, per `DESIGN_SYSTEM.md` §0.4.

### 1. Spacious section layout
Reworked the pages that were densest with per-item bordered cards, replacing
most of them with plain divided rows (`divide-y divide-divider`) inside
clearly-labelled sections, reserving card/panel treatment for things that
truly need visual containment (a form collecting input, a photo thumbnail, a
distinct status readout):
- **My Rentals** (`rentals/my_rentals.html`) — full rewrite. Owner and renter
  views each restructured into three plain sections (Pending requests /
  Rentals in progress / Past rentals) of simple thumbnail + text + status-pill
  rows instead of a bordered card per booking. The payment-instructions panel,
  evidence-upload panel, dispute-report form, and review form all stay as
  light contained panels (bg-accent-100 / bg-amber-50 / bg-surface) since they
  collect input or need attention — only the outer per-booking wrapper lost
  its border/card treatment. The "My listings" quick-list at the bottom is now
  a plain divided list of links instead of pill-shaped chips. Same routes,
  same params, same Jinja macros for badges/panels — pure markup restructure.
- **My Listings** (`listings/my_listings.html`) — already matched the target
  philosophy (frameless card grid, card reserved for the thumbnail only,
  everything else plain text) from the earlier v3 pass; left as-is.
- **Admin panels** — `verify_queue.html`, `payments_queue.html`,
  `disputes_queue.html`, `trust_fund.html` all moved from the v1 navy/teal/
  sand dense-card style to v3 tokens + the same spacious philosophy: plain
  divided rows for bookings/disputes/documents, with the resolve-dispute form,
  the trust-fund starting-balance form, and the CNIC/selfie thumbnails kept as
  contained panels. Trust fund's three balance tiles stay as cards — they're a
  genuine "distinct status panel" case.

### 2. Dead nav links fixed
"How it works" and "Trust & deposits" in the header (`base.html`) pointed to
`#`. Built two real explainer pages instead of removing them:
- `app/web/templates/how_it_works.html` (`GET /how-it-works`) — numbered
  renting flow and listing flow, both grounded in the actual booking state
  machine (request → accept → pay → before/after evidence → deposit release).
- `app/web/templates/trust_deposits.html` (`GET /trust-deposits`) — identity
  verification, refundable deposit, before/after evidence, Trust & Safety
  Fund, and reviews — content pulled from blueprint §6/§7 and the existing
  "Protected by CIRCLO" copy on the listing-detail page, not invented.
- Both routes added to `app/web/routes.py`; both pages cross-link each other.

### 3. CNIC/selfie upload guidance
`verify/status.html` had a file-upload form with zero guidance. Added a
"Before you upload" panel with concrete, real-world instructions (even
lighting, all four corners of the CNIC visible, watch for glare, selfie must
clearly match the CNIC photo, accepted formats) plus a one-line hint under
each file input.

### Verification
- **68 tests pass** (one test updated: it asserted the literal string
  "Pending (awaiting owner)", which the rewritten section label no longer
  produces verbatim — now asserts on "Pending" + "As a renter" instead).
- **Verified live in-browser**, not just tests: seeded a throwaway sqlite DB
  (owner/renter/admin users, listings, bookings across every status —
  requested/accepted/awaiting_payment/paid/active/returned/completed, an open
  dispute, a resolved dispute, a pending identity document, a trust-fund
  balance) and walked through My Rentals (both owner and renter, every
  section and every in-flight panel), My Listings, all four admin pages,
  the verify upload page, and both new explainer pages. Scratch DB and script
  discarded after — nothing committed.

## Archive/deactivate listings + v3 design rollout (DONE ✅, 2026-09-05)

### 1. Archive/deactivate listings
An owner can now take a listing off the marketplace without deleting it —
the alternative for listings with rental history, which can't be
hard-deleted (see the delete-listing 500 fix above).
- **No new column** — `Listing.status` already existed (`draft/active/
  paused/removed` per blueprint §5, only `active` was ever used). Archiving
  sets it to `paused` (`listings_service.ARCHIVED_STATUS`); reactivating sets
  it back to `active` (`BROWSABLE_STATUS`). New service functions
  `archive_listing()` / `reactivate_listing()` (`app/services/listings.py`).
- **Routes**: `POST /listings/<id>/archive`, `POST /listings/<id>/reactivate`
  (`app/web/owner.py`), ownership-guarded like edit/delete.
- **Hidden from browse/search automatically** — `browse_listings()` already
  only returns `BROWSABLE_STATUS`, so no query changes needed there.
- **Visibility on direct link** (`web.listing_detail`, `app/web/routes.py`):
  a non-active listing now 404s for the public but stays viewable for (a)
  the owner and (b) anyone with a booking on it (new
  `booking_service.has_booking_on_listing()`), so rental history/evidence
  stays reachable. The booking sidebar swaps to "This listing is no longer
  available to rent" for non-owner viewers of an archived listing.
  Anonymous/unrelated users still get a 404 — no behavior change for them.
- **My Listings** (`listings/my_listings.html`): each card shows an Active/
  Archived badge and Archive/Reactivate + Edit buttons; **Delete only shows
  when the listing has no booking history** (new
  `booking_service.listing_ids_with_bookings()`) — otherwise it's replaced
  by Archive with a "Has rental history — archive instead of delete" note,
  exactly the case the earlier delete-listing 500 fix was guarding against.
  Same Archive/Reactivate controls added to the listing-detail owner bar for
  parity with the existing Edit/Delete there.
- **Tests**: `tests/test_archive_listing.py` (5 new) — archive removes from
  browse + stays visible to the owner + 404s for a logged-out visitor;
  reactivate restores browse visibility; non-owner gets 403 on both actions;
  a renter with a real booking can view an archived listing while an
  unrelated verified user gets 404; My Listings hides Delete once a booking
  exists. **68 tests pass** (was 63).
- **Verified live** end-to-end in-browser (not just tests): created a
  listing, archived it via My Listings, confirmed it vanished from the home
  grid, confirmed the owner could still open it directly, confirmed a
  logged-out visitor and an unrelated logged-in user both got 404; separately
  created a second listing, had a different verified user book it, archived
  it as the owner, confirmed My Listings showed only Archive (no Delete) for
  it, and confirmed the renter could still open it directly by link. Test
  data cleaned up after (back to 11 listings).

### 2. v3 design rollout — remaining pages
Applied the same "Organic Forest" system (`DESIGN_SYSTEM.md`) already used
on home/listing-detail/auth to the pages that were still on the old v1
navy/teal/sand look:
- **My Rentals** (`rentals/my_rentals.html`) — the biggest of the four: all
  macros (status badges, payment instructions, evidence upload, dispute/
  review forms) re-skinned in place, same URLs/logic/params untouched. Owner
  section tinted with the primary `accent` scale, renter section with the
  secondary `accent2` scale, to keep the two-tone grouping the v1 page had
  (navy owner / teal renter) using the new palette. Found and fixed a
  pre-existing Jinja nesting bug while rewriting the payment-details block
  (an `{% if %}` was missing its matching structure — was correct in the
  original, a transcription slip introduced it here, caught immediately by
  the test suite before it shipped).
- **My Listings** (`listings/my_listings.html`) — frameless v3 card grid,
  status badge, Archive/Reactivate/Edit/Delete controls (see above).
- **Identity verification** (`verify/status.html`) — v3 card, pill file
  inputs and submit button, accent-tinted "Verified" state.
- **Create/edit listing form** (`listings/form.html`) — pill inputs/selects,
  accent focus rings, pill buttons, matching the auth-page field style.
- No routes/services/models changed for the design pass itself (only the
  archive feature above touched backend logic). **68 tests pass.**
- **Not yet migrated**: admin queues, profile, legal pages, forgot/reset
  password — still v1 navy/teal/sand.

## Post-redesign bug fixes (DONE ✅, 2026-09-04)
Three bugs reported after the v3 redesign shipped, all confirmed and fixed:
1. **Oversized header search icon**: `base.html`'s search-bar SVG used
   `h-4.5 w-4.5` — not a real Tailwind utility (the default spacing scale has
   no `4.5` step), so it resolved to no explicit size and the SVG rendered at
   its browser-default intrinsic dimensions, ballooning over the nav. Fixed
   to `h-[18px] w-[18px]`. Grepped the whole template tree for the same
   `[hw]-N.5` mistake pattern — no other occurrences.
2. **Category mismatch — investigated, not a bug**: confirmed the real
   `Category` table (Cameras, Camping, Events, Formal Wear, Gaming, Tools —
   6 rows) against what `index.html` renders. The category pills loop over
   `categories` passed from `listings_service.all_categories()` (a real DB
   query) — the mockup's placeholder category list (Tools & DIY, Sport,
   Music, Baby & kids, etc.) was never hardcoded anywhere in the rebuilt
   templates/routes. Live page confirmed showing exactly the 6 real
   categories. No fix needed.
3. **Admin/owner delete-listing 500**: reproduced locally — deleting a
   listing that has any booking (even just a pending request) hit
   `IntegrityError: null value in column "listing_id" of relation "bookings"
   violates not-null constraint`. `bookings.listing_id` is a required FK with
   no delete cascade; `Listing.delete()` was hard-deleting the row regardless
   of booking history. **Fix**: `listings_service.delete_listing()`
   (`app/services/listings.py`) now checks for any existing booking first and
   raises a new `ListingHasBookings` exception instead of deleting (rental
   history, and the ledger/evidence tied to it, must be preserved); the route
   (`app/web/owner.py`) catches it and flashes "This listing has rental
   history and can't be deleted." instead of letting the `IntegrityError`
   500. Pre-existing bug, not something the redesign introduced — the redesign
   just made someone click Delete on a listing that had bookings for the
   first time. **Verified live**: reproduced the 500 exactly (created an
   admin-owned listing, had a second verified user request a booking on it,
   deleted as the owner — got the raw `IntegrityError` traceback), applied
   the fix, reproduced again — got a 200 with the friendly flash and the
   listing intact. Deleting a listing with *no* bookings still works
   (regression-checked). Added `tests/test_listings_crud.py::
   test_delete_listing_with_bookings_is_refused_not_500` to lock this in.
   Test DB cleaned up after manual repro (stray test listings/booking/user
   removed) — back to the standard 11 listings.
- **63 tests pass** (was 62 — one new regression test added).

## Visual redesign v3 — "Organic Forest" (source-exact, DONE ✅, 2026-09-04)
_Supersedes v2 below — v2 was reverse-engineered from screenshots (~60%
accuracy); v3 is transcribed directly from an exported Claude Design source
file the user provided, so colors/fonts/spacing are exact, not estimated._
- **`DESIGN_SYSTEM.md` rewritten (v3)**: exact tokens — `#0f6b5c` forest-green
  accent (9-step `accent` scale) + `#2f5d4a` secondary `accent2` scale (owner
  avatars, check icons), `#101a16` `ink` text, `#f4f7f5` `surface` /
  `#dde5e0` `divider`, custom `neutral` scale (not Tailwind's default gray —
  the source's neutrals have different hex values). **Barlow Condensed**
  replaces Archivo Black as the display font (`font-display`, still
  uppercase). All heading/price/button sizes are exact px values from the
  source via Tailwind arbitrary-value classes (`text-[88px]`, `text-[23px]`,
  etc.), not rounded to Tailwind's scale. New `shadow-circlo` +
  `rounded-3xl`/`rounded-2xl` stand in for the source's undefined
  `--shadow-md`/`--radius-lg`/`--radius-md` (that stylesheet wasn't part of
  the export — documented as a chosen approximation in `DESIGN_SYSTEM.md`
  §0.2). v1 `navy`/`teal`/`sand`/`font-sora` tokens still kept for
  not-yet-migrated pages.
- **Migrated to v3**: shared header/footer (`base.html`), home/browse
  (`index.html`), listing detail (`listing_detail.html`), **and now
  login/signup** (`auth/login.html`, `auth/signup.html` — new this pass).
- **Auth pages rebuilt**: two-column layout (marketing panel + tabbed card)
  matching the source. Real differences from the mockup, since our backend
  is email/password only (no phone/city columns on `User`): mobile-number
  field → email; Islamabad/Rawalpindi/Both city selector → dropped (nothing
  to persist it to); "Continue with Apple" → dropped (no Apple provider);
  "Keep me signed in" → dropped (`login_user()` isn't called with `remember=`
  anywhere — adding that is a backend change, out of scope for a visual
  pass). **"Continue with Google" is wired to the real `web.google_login`**
  (gated on the existing `google_oauth_enabled` flag, `next=` preserved on
  login). The three stat figures (6,400+ items / Rs 2.1M deposits / 4.9
  rating) are kept as static marketing copy exactly as authored in the
  source — same category as the hero tagline, not a live-data claim.
- **Listing detail rebuilt again** on top of the v2 pass: exact image grid
  (2/3-width hero + two stacked, falls back to a single hero when a listing
  has under 3 photos — no fabricated placeholder photos), owner strip using
  real `owner.created_at`/`review_count` (mockup's "41 items lent" has no
  backing field), "What's included"/"Pickup & rules" replaced with the same
  real marketplace-wide trust content in the mockup's two-column check-list
  layout (no per-listing accessory data exists), "Also nearby" wired for
  real via a small addition to `web.listing_detail` (`app/web/routes.py`) —
  reuses the existing `listings_service.browse_listings()` call, same-category,
  capped at 4, not a new business-logic path. **Booking sidebar rebuilt as an
  inline form** (replacing the old `<dialog>` modal) with real `From`/`Until`
  date inputs, a client-side-computed "Rental estimate" (price × selected
  days — no fabricated "service fee" since CIRCLO doesn't charge one), real
  deposit amount, and a real `POST` to `web.request_booking`. **Verified
  live**: submitting the form as a freshly-signed-up (unverified) user
  correctly redirected to `/verify` — confirms the form hits the real,
  unmodified booking/verification gate, not a stub.
- Browse page's old price/area/verified filter sidebar (a v1/v2 visual
  placeholder, never wired to the backend) is **dropped** — not present in
  the v3 source design. "Show more" button also dropped — `browse_listings()`
  has no pagination, so there's nothing for it to load.
- Header/footer updated again on top of v2: exact `CIRCLO` wordmark styling
  (Barlow Condensed, `0.06em` tracking, accent-700), "How it works" / "Trust
  & deposits" nav links (decorative — no such pages exist yet, same status
  as in the source mockup), nav collapses to a single "Sign in" (auth page's
  tabs handle the sign-up switch, matching the source exactly).
- **Verified live** via the dev overlay: home hero/search/pills/11-card grid,
  listing detail (image grid, trust panels, owner strip, related listings,
  booking form), login and signup pages (tab switching, Google button
  presence) all render correctly — confirmed via DOM/text inspection after
  the screenshot tool exhibited a scroll-capture timing artifact (blank
  frames at certain mid-scroll offsets) unrelated to the page itself; content
  was confirmed present and correctly styled via `getBoundingClientRect` and
  page-text extraction at every scroll depth. Also ran a real signup →
  logged-in nav check → booking-form submission end-to-end.
- **Next**: migrate my-rentals/my-listings/listing-form/profile/admin/legal +
  forgot/reset-password to v3; then retire the v1 `navy`/`teal`/`sand`/
  `font-sora` tokens.

## Visual redesign v2 — "White & Forest" (home + listing detail, superseded by v3 above, 2026-09-04)
- **New `DESIGN_SYSTEM.md`** (v2): white background, forest-green primary
  (`green-700 #1B5E3F`), near-black `ink` headline/body color, Archivo Black
  display font (`font-display`, uppercase headlines/card titles/prices) +
  Manrope body (unchanged). Fully pill-shaped controls (`rounded-full`
  everywhere — buttons, search bar, category pills). Listing cards are now
  frameless: no border/shadow, just a `bg-gray-100` rounded image block +
  text stack. Old navy/teal/sand tokens + `font-sora` **kept** in
  `tailwind.config` (`base.html`) for pages not yet migrated — see the
  migration-status table at the top of `DESIGN_SYSTEM.md`.
- **Migrated**: shared header/footer (`base.html` — necessarily site-wide
  since they're shared chrome; every other page's *body* is untouched and
  still renders in the old navy/teal look until its own pass), home/browse
  (`index.html` — bold caps hero, pill search bar with "All areas" + popular
  searches, green/white category pills, frameless card grid), listing detail
  (`listing_detail.html` — bold caps title, green price, pill "Request to
  Rent"/"Message owner" buttons, restyled owner card + "Protected by CIRCLO"
  panel as a bordered white card instead of a dark navy panel).
- **Not migrated yet** (still old navy/teal/sand): auth pages, my-rentals,
  my-listings, listing form, profile, admin queues, legal pages — planned as
  follow-up passes.
- No routes/services/models touched — visual-only. Distance badges
  (`{{ "%.1f"|format(listing.distance_km) }} KM`, top-left on card image, per
  the reference screenshots) are wired in the template but **guarded with
  `is defined`** — there's no `distance_km` on `Listing`/the browse query yet,
  so the badge silently doesn't render until that field exists. Flagged, not
  fabricated.
- Verified live via the dev overlay (`docker compose -f docker-compose.yml -f
  docker-compose.dev.yml up -d app`): home hero/search/pills/cards and listing
  detail (gallery, price card, owner card, trust panel, request modal) all
  render correctly in-browser, no console errors.
- **Next**: migrate auth/my-rentals/my-listings/admin/profile/legal to v2 in
  follow-up passes; then retire the v1 `navy`/`teal`/`sand`/`font-sora` tokens
  once nothing references them.

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
- **Auto-seed on first boot** (`docker/entrypoint.sh`): Render's free tier
  has no shell access, so there's no way to manually run `flask seed` after
  deploy. The entrypoint now checks `Listing.query.count()` after migrations
  run — if the table is empty, it automatically runs `flask seed` (demo
  categories/listings/images) and `flask seed-test-accounts` (`user@circlo.test`
  / `admin@circlo.test`); if listings already exist, it skips seeding
  entirely so a restart never re-seeds or wipes real data. Identical logic
  for local Docker Compose and Render — same entrypoint script, no
  environment-specific branching. Seed failures are non-fatal (logged as a
  warning) so a network hiccup fetching demo photos doesn't block boot.
  Verified locally: `docker compose down -v` (full wipe) → `docker compose
  up --build` → log shows `listings table is empty; seeding demo data ...`
  → `Seeded 11 owners, 6 categories, 11 listings, 11 images` + both test
  accounts created → `/health` 200. Then `docker compose restart app` →
  log shows `listings already present; skipping seed.` → confirmed via a
  direct query: still exactly 11 listings and one of each test account, no
  duplication.
- **Next**: enable the R2 public dev URL (above), then a real Render deploy
  attempt to confirm the Postgres-wait fix resolves the original
  `[entrypoint] ERROR: Postgres did not become ready in time` failure, and
  that the auto-seed fires correctly with no shell access.

## Email — Brevo transactional API — DONE ✅ (2026-09-03)
_Final state. Supersedes the four earlier dated email notes (see git log
5eb13f6..deebc16 for the full trail: creds rotation → Render "silent send"
diagnosis → SMTP→API rewrite → debug-route cleanup)._
- **Transport**: `app/services/email.py` calls Brevo's REST API
  (`POST https://api.brevo.com/v3/smtp/email`, port 443) via stdlib `urllib`.
  SMTP was abandoned — ports 587/465 are blocked outbound on **both** the dev
  network and Render (confirmed, infra-level). Same `send_email(to, subject,
  body_html, raise_on_error=False)` signature; callers unchanged.
- **Config**: `BREVO_API_KEY` (a v3 `xkeysib-…` key, NOT the SMTP key),
  `BREVO_API_URL` (default set), `MAIL_FROM_ADDRESS`, `MAIL_FROM_NAME`.
  `is_configured()` needs `BREVO_API_KEY` + `MAIL_FROM_ADDRESS`.
- **Logging**: `app/__init__.py` `_configure_logging()` binds `app.logger` to
  Gunicorn's handlers + honours `LOG_LEVEL` (default INFO) — without it every
  `logger.info` was dropped on Render. `send_email` logs attempt (INFO) /
  success+messageId (INFO) / failure with full body+traceback (ERROR).
- **Verified**: live send works on Render, `From: CIRCLO <help@circlo.pk>`;
  forgot-password round-trip confirmed; 61 tests pass. The stale
  `afnank070@gmail.com` sender was a leftover Render dashboard env var (no code
  default) — corrected there.
- **Local checks**: `flask send-test-email <addr>` (works from a network that
  doesn't block 443 — i.e. anywhere). The temporary `/debug/test-email` route
  has been removed.
- **Next / follow-ups**: verify SPF/DKIM for `circlo.pk` in Brevo so mail lands
  in inbox not spam; reuse `send_email` for an email-verification link on signup
  (optional — identity is gated by CNIC/selfie, not email); move the inline HTML
  bodies to Jinja templates if they grow (M5 follow-up, still open).

## "Sign in with Google" (OAuth2 / OIDC) — DONE ✅ (2026-09-03)
- **Library**: Authlib 1.3.2 (`authlib.integrations.flask_client.OAuth`) +
  `requests` — both added to `requirements.txt`. `oauth` singleton in
  `app/extensions.py`; `app/__init__.py` `_init_oauth()` registers the `google`
  provider via OIDC discovery **only when** `GOOGLE_CLIENT_ID` +
  `GOOGLE_CLIENT_SECRET` are set (otherwise the button hides and the routes
  bounce to `/login` with a friendly flash). Email/password auth untouched.
- **Config**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_DISCOVERY_URL`
  (default = Google's well-known metadata URL). In `.env.example` + `render.yaml`
  (`sync: false`).
- **Routes** (`app/web/auth.py`): `GET /auth/google/login` (stashes a safe
  `?next=` in the session, redirects to Google) and `GET /auth/google/callback`
  (`authorize_access_token()` → `userinfo`; requires a verified email).
- **Account logic** (`auth.get_or_create_oauth_user`): email already exists →
  log that user in (name NOT overwritten, password intact); else create a
  **passwordless** `User` (`password_hash` NULL) with `verification_status =
  pending` — a Google signup still needs the same CNIC/selfie check.
  `User.check_password()` returns False when there's no hash;
  `User.has_password` property added.
- **Schema**: migration `f7b2c9e4a1d8` (revises `c4e6f8a0d2b5`) makes
  `users.password_hash` nullable. Applied clean on Docker/Postgres.
- **UI**: "Sign in / Sign up with Google" button + divider on `auth/login.html`
  and `auth/signup.html`, gated on `google_oauth_enabled` (context processor).
- **Tests**: `tests/test_oauth.py` (9) — button shown/hidden, login redirect
  targets Google, callback creates unverified passwordless user, callback logs
  into an existing email account without dupe/overwrite, OAuth-only user can't
  password-login, email/password signup still works, missing-email rejected.
  `conftest.TestConfig` blanks the Google keys so a dev's real `.env` can't
  leak in. **61 pass total.**
- **Verified live**: buttons render; `/auth/google/login` 302s to
  `accounts.google.com/o/oauth2/v2/auth` with the right client_id, redirect_uri
  (`/auth/google/callback`), scope and `state`+`nonce`. Full consent round-trip
  is a manual browser check (needs the redirect URI registered in Google Cloud).
- **Next / follow-ups**: register the prod redirect URI + move the OAuth app out
  of "Testing" to "In production" in Google Cloud before public launch; consider
  storing `oauth_provider` on `User` if a second provider is ever added.

## OAuth redirect URI + legal pages (2026-09-03, follow-up)
- **Legal pages for Google verification**: `/privacy` and `/terms`
  (`app/web/routes.py` → `app/web/templates/legal/{privacy,terms}.html`,
  extend `base.html`). Content is specific to what CIRCLO does — data collected
  (name, email, phone, CNIC/selfie for verification, listing/booking/payment
  records), used only to run the marketplace, **not sold to third parties**,
  privacy contact `help@circlo.pk`; terms cover 18+, accurate info,
  owner↔renter rental agreement with CIRCLO as facilitator, deposit-dispute
  review, account suspension for fraud. Footer now links to both (was dead `#`).
- **Redirect URI drift fix** (`app/web/auth.py`): the callback URL was
  `url_for("web.google_callback", _external=True)`, which echoes the request
  `Host` header → drifted between `circlo.pk` / `www.circlo.pk`. New
  `_google_redirect_uri()` pins it to `PUBLIC_BASE_URL` (falls back to the
  request-derived URL when unset, for local dev/tests). **`PUBLIC_BASE_URL`
  also already drives every email link** (`password_reset._build_reset_url`,
  `notifications._abs_url`) — those were only hitting `localhost:5000` because
  the env var was unset on Render, not a code bug. Set
  `PUBLIC_BASE_URL=https://www.circlo.pk` on Render and register exactly
  `https://www.circlo.pk/auth/google/callback` in Google Cloud Console; add a
  301 apex→www redirect so users never sit on the non-canonical host.
- **Callback 500 fix**: a first cut also passed
  `authorize_access_token(redirect_uri=...)`. Authlib already replays the
  redirect_uri from session state into `fetch_access_token`, so the explicit
  kwarg collided → `TypeError: ... got multiple values for keyword argument
  'redirect_uri'`, uncaught → **500 at `/auth/google/callback`**. Fixed by
  calling `authorize_access_token()` with no args; test stub locked to a
  no-kwargs signature so a re-add fails CI. **62 tests pass.**
- **Blocked on user**: confirm `PUBLIC_BASE_URL` is actually set on Render and
  that the Google Cloud redirect URI matches it exactly (with `www`). Needs a
  Render redeploy of commit with the 500 fix, then a live consent round-trip.

## Current milestone: M5 — Trust & Polish (DONE ✅)
_(Reviews & ratings, disputes, trust-fund bookkeeping, and real transactional
email via Brevo SMTP. Phone OTP / SMS stays deferred — per-message cost,
blueprint §13.)_

### Done — M5
- **Email service** (`app/services/email.py`): one `send_email(to, subject,
  body_html)` over `smtplib` against Brevo's SMTP relay. Config from env only
  (`BREVO_SMTP_SERVER/PORT/LOGIN/KEY`, `MAIL_FROM_ADDRESS/NAME`, `PUBLIC_BASE_URL`).
  If login/key/from are unset it logs the message and returns `False` (dev/tests
  never deliver); delivery errors are caught and logged — email is best-effort
  and never breaks a flow. `.env.example` updated with placeholders.
- **Forgot-password flow** (real): `PasswordResetToken` model (SHA-256 hash
  only, 1-hour TTL, single-use) + `app/services/password_reset.py`
  (`request_reset` — no account enumeration, `verify`, `consume` — also burns
  the user's other outstanding tokens). Routes `/forgot-password` +
  `/reset-password/<token>`, "Forgot password?" link on the login page,
  `auth/forgot_password.html` + `auth/reset_password.html`.
- **Notifications** (`app/services/notifications.py`, wired from the service
  layer so `/api/v1` gets them too, each call `@_safe` so it can't break the
  caller): identity verification submitted/approved/rejected → user; new rental
  request → owner; request accepted/rejected → renter; payment confirmed →
  renter; rental completed → both parties (with a review prompt).
- **Reviews & ratings** (`Review` model, `app/services/reviews.py`): after a
  booking is COMPLETED both parties can leave one 1–5 rating + comment
  (`direction` = renter_on_owner / owner_on_renter; unique on
  `(booking_id, author_id)`). Leaving a review recomputes the subject's cached
  `User.rating`, which already drives the star on listing cards; new public
  profile page `/users/<id>` shows the average, review count, and the reviews.
  Review form appears on completed bookings in My Rentals.
- **Disputes** (`Dispute` model, `app/services/disputes.py`): either party on an
  ACTIVE / RETURNED / COMPLETED booking clicks "Report a problem" → opens a
  dispute (one open per booking). `/admin/disputes` lists open + resolved;
  admin resolves with resolution notes, a deposit decision
  (released / withheld / undecided) and a tracked `amount_from_fund`. The
  booking's own status is left unchanged for the MVP (the Dispute row is the
  record) — a real `disputed` booking state is a follow-up.
- **Trust & Safety Fund** (`app/services/trust_fund.py`, `/admin/trust-fund`):
  bookkeeping only. Admin sets a starting balance once (stored in `app_settings`);
  `current_balance = starting − Σ amount_from_fund` over resolved disputes.
  Shows the three figures + a disbursements table. No gateway payout (§7).
- **Migration** `c4e6f8a0d2b5` (revises `b1c3d5e7f9a2`) — `password_reset_tokens`,
  `reviews`, `disputes`. Hand-written in the existing style (**run `flask db
  upgrade` + sanity-check on Docker/Postgres**).
- **Admin nav**: account menu gains Disputes / Trust fund links for admins.
- **Tests**: `tests/test_trust_polish.py` (8 tests — reset flow incl.
  single-use + expiry + no-enumeration, notification fires on booking request,
  reviews update rating + one-per-direction + not-before-completed, dispute
  open/resolve decrements the fund + no double-open + not-before-active, admin
  pages 403/200). `conftest.py` now has an autouse fixture + blanked SMTP config
  so **no test ever opens a real SMTP connection** even with live creds in
  `.env`. **52 passing** total (`pytest -q`, incl. the 6 MinIO verification
  tests when Docker is up).

### Known follow-ups (M5)
- No `disputed` booking status / state-machine branch — disputes are tracked
  alongside the booking, not as a lifecycle state.
- Dispute resolution doesn't create ledger entries — the deposit decision is
  recorded as text, not reflected in `ledger_entries`.
- Reviews are visible to everyone once written (no "both submitted before
  reveal" blind period).
- Trust-fund top-ups aren't modelled — only a single starting balance minus
  disbursements.
- Email templates are inline HTML strings — fine at this volume; move to Jinja
  templates if they grow.
- Admin isn't emailed on new verification / new dispute (still a log line).

## Previous milestone: M4 — Money & Evidence (DONE ✅)
_(Semi-manual money per blueprint §7 — no gateway. Every rupee is tracked in a
ledger; an admin confirms real bank/JazzCash transfers. Plus the before/after
handover evidence system. Extends the booking state machine to the full
blueprint §5 lifecycle.)_

### Done — M4
- **`LedgerEntry` model** (`app/models/ledger_entry.py`): `booking_id`, `type`
  (`rental_payment`/`deposit`/`commission`/`payout`/`refund`), `amount`,
  `status` (`pending`/`confirmed`), `created_at`, `confirmed_by` (admin
  user_id), `confirmed_at`. Named constants for every type/status.
- **`EvidenceMedia` model** (`app/models/evidence_media.py`): `booking_id`,
  `phase` (`before`/`after`), `uploaded_by`, `object_key` (private bucket),
  `media_type`, `created_at`. Write-once (no update/delete) per blueprint §8.
- **Booking state machine extended** (`app/models/booking.py` +
  `app/services/booking.py`) to the full blueprint §5 lifecycle:
  `requested → accepted → awaiting_payment → paid → (handed_over) → active →
  returned → completed`, plus `cancelled`. `handed_over` is instantaneous in the
  MVP (recorded then promoted to `active`). New `Booking.rental_amount` column —
  snapshot of `price_per_day * days` at request time (nullable; service
  backfills old rows on read). `has_overlapping_acceptance` now blocks on any
  committed status, not just `accepted`. `cancel()` allowed only through
  `awaiting_payment` (before money is confirmed).
- **Services (all logic here, API-reusable):**
  - `services/ledger.py` — `record`, `record_payment_received` (confirmed
    rental+deposit), `record_completion_entries` (pending commission/payout/
    refund), `confirm_entry`, `confirm_all_for_booking`. `COMMISSION_RATE =
    0.20` of the rental fee (not the deposit), per blueprint §1.
  - `services/payments.py` — `mark_awaiting_payment` (renter asserts they've
    transferred), `bookings_awaiting_payment_confirmation`,
    `confirm_payment_received` (→ PAID + confirmed ledger entries),
    `bookings_awaiting_payout`, `confirm_payout` (flip pending entries to
    confirmed). Custom exceptions mirror the booking-service pattern.
  - `services/evidence.py` — `upload_evidence` (validates party + phase +
    booking state, uploads to the **private** bucket under
    `evidence/<booking>/<phase>/<user>/<uuid>.<ext>`), advances the booking once
    **both** renter and owner have uploaded for a phase. `has_uploaded`,
    `both_parties_uploaded`, `evidence_for_booking` helpers.
- **`booking.confirm_return`** (owner-only, RETURNED → COMPLETED): triggers
  `ledger.record_completion_entries` — 20% commission, owner payout (rental −
  commission), full deposit refund — all `pending` until an admin confirms.
- **Admin `/admin/payments`** (`app/admin/payments.py` +
  `templates/payments_queue.html`): two queues — *Awaiting payment
  confirmation* (renter says paid → "Confirm payment received" creates the
  ledger entries + moves to PAID) and *Awaiting payout & refund* (completed
  rentals with pending entries → "Confirm payout & refund sent"). `admin_required`
  on every view. Account menu in `base.html` gains Admin · Verifications / Admin ·
  Payments links for admins.
- **Web routes** (`app/web/booking.py`): `POST /bookings/<id>/mark-paid`,
  `POST /bookings/<id>/evidence` (multipart, `phase` + `photo`),
  `POST /bookings/<id>/confirm-return`.
- **My Rentals redesign** (`templates/rentals/my_rentals.html`): owner +
  renter "in progress" cards now show the full-lifecycle status pill
  (Awaiting Payment, Paid — Upload Evidence, Active, Returned — Awaiting
  Confirmation, Completed) matching the existing card style, plus the relevant
  inline action: pay-now panel, before/after photo upload with per-party
  progress + thumbnails, owner "Confirm item returned" button. Owner/renter
  history sections now include completed rentals.
- **Migration** `9a2f4c1d7b83` (revises `7c3f9a1b2e4d`) — creates
  `ledger_entries` + `evidence_media`, adds `bookings.rental_amount`.
  Hand-written in the existing style (no Docker/Postgres this session —
  **run `flask db upgrade` and sanity-check the DDL on Docker**).
- **Tests**: `tests/test_money_evidence.py` — 10 new tests (rental-amount
  snapshot, renter-marks-paid → admin-confirms + ledger, wrong-state guards,
  evidence advances only when both upload, non-party/wrong-phase rejection,
  full cycle → completion → commission maths (2400 → 480/1920) + payout
  confirmation, confirm-return state guard, no-cancel-after-paid, admin page
  403/200). Storage stubbed via monkeypatch so no MinIO needed.
  **`python -m pytest -q` → 40 passed** locally (SQLite, no Docker). The 3
  `test_verification.py` MinIO uploads still need `docker-compose up`.

- **Admin-configurable payment details** (`app/models/app_setting.py`,
  `app/services/settings.py`, `/admin/settings`): a `app_settings` key/value
  table (migration `b1c3d5e7f9a2`) holding CIRCLO's EasyPaisa number / bank
  account. `settings.get()` = DB value → `Config` env-var fallback → default, so
  the anti-hard-code rule (blueprint §9) still holds and it's editable with no
  redeploy once the company account is ready. The renter's payment card on
  `/my-rentals` (accepted + awaiting_payment) now shows the **exact amount due**
  (rental + deposit, bold total) beside these instructions; a fallback
  "contact support" line shows when nothing is configured. New env-var
  fallbacks `PAYMENT_*` in `.env.example` (all blank by default).

### Known follow-ups (M4)
- No cancellation/refund *policy* (partial refunds, late fees) — business
  decision, blueprint §13.
- Evidence has no "after" deadline enforcement — renter/owner can upload
  after-photos any time while `active`.
- Commission entry is created `pending` and only confirmed as part of the
  payout step; there's no separate CIRCLO revenue reconciliation view yet.
- No dispute path yet (`disputed` status) — M5.
- Migration hand-written — confirm `flask db upgrade` applies cleanly on real
  Postgres.

## Previous milestone: M3 — Booking core (rental state machine, DONE ✅)
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
- M6 API & mobile handoff: stabilise `/api/v1`, add JWT, hand Abdullah the
  contract (blueprint §12).
- Add CSRF protection to all forms (Flask-WTF) — long-standing, do before public
  deploy. NOTE: the Google OAuth flow already has CSRF protection (Authlib
  `state`); this is about the plain POST forms.
- Phone OTP (deferred — per-message SMS cost, blueprint §13).
- CNIC/selfie retention policy (delete raw docs after approval?) — blueprint §8.
- ~~Real transactional email~~ — DONE ✅ (Brevo API, see Email section above).
- ~~Sign in with Google~~ — DONE ✅ (see OAuth section above). Before public
  launch: register the prod redirect URI + publish the Google OAuth app.
- ~~M5 Trust & polish~~ — DONE ✅ (see M5 section above).
- ~~M4 Money & evidence~~ — DONE ✅ (see M4 section above).

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
