# CIRCLO — Design System Reference (v3, source-exact "Organic Forest")

**Supersedes v2** (which was reverse-engineered from screenshots at ~60%
accuracy). v3 is transcribed directly from an exported Claude Design source
file covering three views — browse/home, auth (sign in/up), listing detail —
so every color, font size, weight, and spacing value below is exact, not
estimated, **except** the handful explicitly marked "chosen" in §0.2 where the
source referenced a token (`--radius-lg`, `--shadow-md`, `--font-body`) whose
definition lived in a sibling stylesheet we were not given.

The stack is unchanged: Tailwind via CDN with a `tailwind.config` override in
`base.html`. Arbitrary-value classes (e.g. `text-[88px]`) are used freely
where Tailwind has no stock utility for an exact px value — this is standard
Tailwind JIT syntax and works on the Play CDN build.

---

## 0. Migration status & adaptation notes

### 0.1 Migrated to v3
Shared header/footer (`base.html`), home/browse (`index.html`), listing
detail (`listing_detail.html`), login (`auth/login.html`), signup
(`auth/signup.html`), my-rentals, my-listings, identity verification
(`verify/status.html`), listing form, the new `how_it_works.html` /
`trust_deposits.html` explainer pages, and all four admin panels
(`verify_queue.html`, `payments_queue.html`, `disputes_queue.html`,
`trust_fund.html`).

**Not yet migrated** (still v1 navy/teal/sand): forgot/reset password,
legal pages. The v1 tokens stay in `tailwind.config` until those are
migrated too.

### 0.4 Layout philosophy (2026-09-05 rework)
My Rentals, My Listings, and the four admin panels moved away from
"everything in a bordered card" toward spacious sections with plain,
divided rows (`divide-y divide-divider`) for informational content
(booking status, dates, names). A bordered/tinted `rounded-2xl` container
is now reserved for things that genuinely need visual containment: a
form collecting input (resolve-dispute form, review form, payment
confirmation, trust-fund starting-balance form), a photo thumbnail (CNIC/
selfie, booking evidence), or a distinct status readout (trust fund
balance tiles). Section headers are plain uppercase labels with a count,
not another card. The profile page (`users/profile.html`) and admin settings
(`settings.html`) were migrated to v3 + this philosophy the same day.

### 0.5 Listing photo display: crop at upload, `object-cover` everywhere
Listing photos are normalized to a **4:3** crop at upload time (Cropper.js,
`listings/form.html` — see §0.6), so every place a listing photo renders
(browse grid, My Listings, My Rentals thumbnails, listing detail hero/gallery/
related cards, the edit-listing existing-photo gallery) can safely use
`object-cover` inside a 4:3 (or square, for small list thumbnails) box for a
clean, uniform grid — no letterboxing. The browse-grid card was changed from
`aspect-[4/5]` to `aspect-[4/3]` to match. This superseded an earlier
`object-contain` pass done before upload-time cropping existed; photos
uploaded before the crop tool shipped may still be off-ratio and can crop
slightly until re-uploaded. Photos that aren't listing photos — CNIC/selfie
verification images, before/after booking evidence — were always on
`object-cover` and are unaffected: those are framed close-up document/
condition shots, not put through the crop tool.

### 0.6 Upload-time photo crop
`listings/form.html` loads Cropper.js (CDN, scoped to this page only via
`{% block extra_head %}` / `{% block extra_scripts %}` in `base.html`) and
intercepts the `images` file input's `change` event: each newly-selected photo
is shown in a crop modal (4:3 fixed aspect, drag/resize), and the cropped
canvas replaces the original `File` (via `DataTransfer`) before the form ever
submits — the server still just stores whatever bytes it receives
(`app/services/storage.py` untouched). A "Use original" skip button exists per
photo for the rare case a user doesn't want to crop. Deliberately **not**
applied to `/verify` (CNIC/selfie) or booking evidence uploads — those are
document/condition photos, a different concern from marketplace listing
photos.

### 0.2 Values chosen where the source didn't define them
The exported file references `--radius-lg`, `--radius-md`, `--shadow-md` and
`--font-body` from a sibling design-system stylesheet (`_ds/organic-.../
styles.css`) that wasn't part of the export. Chosen equivalents:
- `--radius-lg` → **24px** (Tailwind `rounded-3xl`)
- `--radius-md` → **16px** (Tailwind `rounded-2xl`)
- `--shadow-md` → `0 8px 24px -8px rgba(16,26,22,0.14)` (custom `shadow-circlo`
  utility added to `tailwind.config.boxShadow`)
- `--font-body` → **Manrope** (already loaded from v2; the export never
  overrides it beyond headings, so the existing body font carries over)

### 0.3 Content adapted to real data (not fabricated)
The exported file is a static Claude Design mockup with placeholder
copy/data. Where its content has no backing field in our models, the page
uses real data instead of copying the mockup's placeholder values:
- **Auth fields**: the mockup shows a `+92` mobile-number field and an
  Islamabad/Rawalpindi/Both city selector. CIRCLO auth is email/password
  only (no phone field, no user `city` column) — the form uses **email**
  in the same pill input style, and the city selector is **dropped**
  (nothing to persist it to).
  - "Continue with Google" is wired to the real `web.google_login` route.
    "Continue with Apple" is **dropped** — there's no Apple provider.
  - "Keep me signed in" is dropped — `login_user()` isn't called with
    `remember=` anywhere in the app; adding that is a backend change, out of
    scope for a visual-only pass.
  - The three auth-page stats (`6,400+ items`, `Rs 2.1M deposits`, `4.9
    rating`) are kept as static marketing copy, exactly as authored in the
    source — same category as the hero tagline, not a claim of live data.
- **Listing detail "What's included" / "Pickup & rules"**: the mockup's
  per-item accessory/rules lists don't exist on the `Listing` model (there's
  no `included`/`rules` field). Rather than invent them, this section is
  replaced with the same real, marketplace-wide trust content the v1/v2
  pages already showed ("Protected by CIRCLO" — deposit escrow, before/after
  evidence, Trust Fund), laid out in the mockup's two-column check-list
  visual pattern.
  - Owner strip: the mockup's "Renting since 2024 · 41 items lent" has no
    backing fields. Uses real ones instead — `owner.created_at` year +
    `owner.review_count`.
  - "Message" button stays visual-only (no `onclick`) — this mirrors the
    pre-existing v1/v2 behavior; there's no messaging feature in the backend.
  - Meta row drops "· 1.2 km away" (no distance field, same gap flagged in
    v2).
  - **"Also nearby"**: wired for real via a small addition in
    `web.listing_detail` — same-category listings via the existing
    `listings_service.browse_listings()`, excluding the current one, capped
    at 4. Not a new business-logic path, just reuses the existing service
    call the browse page already makes.
  - **Booking sidebar**: the mockup hardcodes a date range and a "Service
    fee" line. CIRCLO has no service-fee concept (commission is taken from
    the owner's payout, not added to the renter's charge) and no upfront
    charge at request time ("You won't be charged yet"). The sidebar keeps
    the mockup's visual shape (price, inline date fields, breakdown box,
    pill CTA) but the breakdown shows **Rental estimate** (price × selected
    days, computed client-side as the dates change) and **Refundable
    deposit** only, and the CTA posts to the real `web.request_booking`
    route — replacing the old `<dialog>` modal with an inline sidebar form
    (same backend call, new location).
- **Browse "Show more"**: dropped — `browse_listings()` returns the full
  result set already (no pagination in the service), so a "Show more" button
  would have nothing to load.

---

## 1. Color tokens (exact)

```
--color-bg:        #ffffff
--color-surface:   #f4f7f5
--color-divider:   #dde5e0
--color-text:      #101a16   (near-black body/heading ink)

--color-accent:     #0f6b5c   (primary — same as accent-500)
--color-accent-100: #e6f2ef
--color-accent-200: #c6e2db
--color-accent-300: #9ecfc4
--color-accent-400: #6bb5a6
--color-accent-500: #0f6b5c
--color-accent-600: #0c5a4d
--color-accent-700: #0a4a40
--color-accent-800: #073830
--color-accent-900: #052922

--color-accent-2:     #2f5d4a   (secondary accent — avatars, check icons)
--color-accent-2-100: #eaf1ec
--color-accent-2-200: #cfe0d5
--color-accent-2-300: #b0cdbd
--color-accent-2-400: #7ba992
--color-accent-2-500: #2f5d4a
--color-accent-2-600: #274f3f
--color-accent-2-700: #1f4033
--color-accent-2-800: #163027
--color-accent-2-900: #0f231c

--color-neutral-100: #f5f7f6
--color-neutral-200: #e8edea
--color-neutral-300: #d7ded9
--color-neutral-400: #b9c3bd
--color-neutral-500: #8e9a94
--color-neutral-600: #6d7973
--color-neutral-700: #4f5b55
--color-neutral-800: #333c38
--color-neutral-900: #1d2421
```

Tailwind config (`base.html`) exposes these as `accent` / `accent2` /
`neutral` color scales (`bg-accent-700`, `text-neutral-600`, etc.), plus
flat `bg`, `surface`, `divider`, `ink` for the four non-scaled tokens.
`bg-accent` / `text-accent` (no shade) resolve to accent-500, matching
`var(--color-accent)`.

### Usage
| Role | Token |
|---|---|
| Page background | `bg-white` (`--color-bg`) |
| Card/panel surface | `bg-surface` (`--color-surface`) |
| Borders, dividers, input borders | `border-divider` (`--color-divider`) |
| Body text, headings | `text-ink` (`--color-text`) |
| Primary buttons, prices, active pill, links | `bg-accent` / `text-accent-700` |
| Avatar fills, "included" check icons, trust-panel icons | `bg-accent2-300` / `text-accent2-700` |
| Muted/meta text | `text-neutral-600` / `text-neutral-700` |
| Distance badge text | `text-neutral-800` |

Semantic colors (errors, warnings) are unchanged Tailwind defaults —
`rose`/`amber` — since the source file has no error-state screens.

---

## 2. Typography (exact)

Fonts: **Barlow Condensed** 500/600/700 (display — all headings, prices,
buttons, pills, nav wordmark) + **Manrope** (body — chosen per §0.2).

```
h1,h2,h3,h4,h5,h6 { font-family: "Barlow Condensed"; font-weight: 700; letter-spacing: -0.01em; }
```

| Element | Classes (exact px/weight from source) |
|---|---|
| Nav wordmark "CIRCLO" | `font-display font-bold text-[30px] leading-none tracking-[0.06em] text-accent-700` |
| Nav city caption | `text-[11px] tracking-[0.14em] uppercase text-neutral-600` |
| Browse hero H1 | `font-display font-bold text-[88px] leading-[0.94] uppercase` |
| Browse hero subtitle | `text-[17px] text-neutral-700` |
| Search input text | `font-display font-medium text-[30px] tracking-[0.01em]` |
| Search button | `font-display font-bold text-[19px] tracking-[0.08em] uppercase` |
| "All areas" location label | `text-[15px] text-neutral-700` |
| "Popular:" label | `text-[12px] text-neutral-600` |
| Popular search term | `text-[13px] text-neutral-700` (underline `border-neutral-400`) |
| Category pill | `font-display font-semibold text-[15px] tracking-[0.05em] uppercase` |
| "N items available" | `text-[14px] text-neutral-700`, count in `font-bold` |
| "Sorted by" | `text-[13px] text-neutral-700` |
| Card title (h3) | `font-display font-bold text-[23px] leading-[1.05] uppercase` |
| Card price | `font-display font-bold text-[20px] text-accent-700` |
| Card "/ day" | `text-[13px] text-neutral-600` |
| Card area/rating row | `text-[13px] text-neutral-600` |
| Distance badge | `text-[11px] tracking-[0.06em] uppercase text-neutral-800` |
| Auth kicker | `text-[12px] tracking-[0.14em] uppercase text-accent-700` |
| Auth headline | `font-display font-bold text-[80px] leading-[0.94] uppercase` |
| Auth subtitle | `text-[17px] leading-[1.6] text-neutral-700` |
| Auth stat value | `font-display font-bold text-[38px] text-accent-700` |
| Auth stat label | `text-[13px] leading-[1.4] text-neutral-700` |
| Auth tab button | `font-display font-bold text-[16px] tracking-[0.07em] uppercase` |
| Field label | (bundle default — kept at `text-sm font-bold text-ink`, matching the `.field label` role) |
| "or" divider | `text-[11px] tracking-[0.12em] uppercase text-neutral-500` |
| Fine-print | `text-[12.5px] leading-[1.5] text-neutral-700` |
| Detail back link | `text-[13px] tracking-[0.08em] uppercase text-neutral-700` |
| Detail category label | `text-[12px] tracking-[0.14em] uppercase text-accent-700` |
| Detail H1 | `font-display font-bold text-[62px] leading-[0.95] uppercase` |
| Detail meta row | `text-[14px] text-neutral-700` |
| Section h4 ("About this item", etc.) | `font-display font-bold text-[22px] uppercase` |
| About body copy | `text-[16px] leading-[1.65] text-neutral-800` |
| Included/rules row | `text-[15px] text-neutral-800` |
| Owner name | `font-display font-bold text-[22px] uppercase leading-[1.1]` |
| Owner meta | `text-[13px] text-neutral-700` |
| Related card title | `font-display font-bold text-[18px] leading-[1.05] uppercase` |
| Related card meta | `text-[13px] text-neutral-600` |
| Sidebar price | `font-display font-bold text-[44px] text-accent-700` |
| Sidebar "per day" | `text-[14px] text-neutral-700` |
| Sidebar breakdown rows | `text-[14px] text-neutral-800` |
| Sidebar total row | `font-display font-bold text-[20px] uppercase` |
| Sidebar CTA button | `font-display font-bold text-[19px] tracking-[0.08em] uppercase` |
| "Usually replies within an hour" | `text-[12px] text-neutral-600` |

Prices are still `Rs ` + comma-thousands, no decimals — unchanged rule from
v1/v2.

---

## 3. Layout & spacing (exact px from source)

| Pattern | Value |
|---|---|
| Page max width | `1440px` → `max-w-[1440px]` (was `max-w-7xl`) |
| Horizontal gutter | `56px` → `px-14` |
| Header row padding | `22px 56px` → `py-[22px] px-14` |
| Hero top/bottom padding | `56px 0 12px` |
| Search bar padding | `12px 12px 12px 30px`, height `58px` on the Search button |
| Search bar → popular gap | `24px 0 10px` margin |
| Popular row bottom margin | `44px` |
| Category row bottom padding | `26px`, `border-bottom: 1px solid divider` |
| "N items" row padding | `26px 0 22px` |
| Card grid gap | `44px 32px` (row/column) — `gap-x-8 gap-y-11` |
| Card grid columns | `4` desktop (`grid-cols-1 sm:grid-cols-2 xl:grid-cols-4` — source is a
  fixed 1440px design with no responsive breakpoints defined; the 1/2/4
  progression is added for our real, non-fixed viewport) |
| Card image→text gap | `12px` |
| Auth two-column gap | `80px`, card padding `30px` |
| Auth stats grid gap | `26px` |
| Detail two-column gap | `64px` |
| Detail image grid | `2fr 1fr` columns, `190px 190px` rows, `12px` gap |
| Detail included/rules gap | `34px` |
| Detail owner strip padding | `22px 26px` |
| Detail "also nearby" gap | `24px` |
| Sidebar padding | `26px`, sticky `top: 24px` |
| Sidebar date-fields gap | `10px` |

---

## 4. Cards

**Listing card (frameless, as v2 — now with exact spacing):**
```
flex flex-col gap-3
```
- Image wrapper: `relative rounded-2xl overflow-hidden bg-surface`, aspect
  ratio **4:5** (mockup's default `cardAspect: "portrait"`) —
  `aspect-[4/5]`.
- Image hover: `transition-transform duration-[280ms] ease-[cubic-bezier(.2,.7,.3,1)] group-hover:-translate-y-1`
  (matches `.circ-shot:hover { transform: translateY(-4px) }`).
- Distance badge: `absolute left-3 top-3 rounded-full bg-white/88 backdrop-blur-sm px-[11px] py-1`.
- Text stack starts `gap-[5px]` below the image.

**Auth card / sidebar / owner strip / trust panels (surface cards):**
```
bg-surface border border-divider rounded-3xl p-[26px] sm:p-[30px] shadow-circlo
```
Radius/shadow per §0.2. This replaces v2's plain white-bordered cards.

---

## 5. Buttons & pills

**Primary (accent, pill):**
```
rounded-full bg-accent text-white hover:bg-accent-600
font-display font-bold uppercase tracking-[0.08em]
```
Heights vary by context: `h-[58px]` (search), `h-[52px]` (auth CTA, sidebar
CTA) — always `rounded-full`.

**Secondary (outline pill, `btn-secondary`):**
```
rounded-full border border-divider bg-white text-ink
font-display font-semibold uppercase tracking-[0.05em]
```
Used for "Message", auth OAuth buttons.

**Category / tab pill (toggle):**
```
rounded-full px-[18px] py-2 font-display font-semibold text-[15px] tracking-[0.05em] uppercase transition
/* active:   */ bg-accent-700 text-white border border-accent-700
/* inactive: */ bg-transparent text-neutral-800 border border-divider hover:text-accent-700 hover:border-accent-400
```

**Auth sign-in/sign-up tab (segmented, no border on the pill itself):**
```
flex-1 rounded-full py-2.5 font-display font-bold text-[16px] tracking-[0.07em] uppercase transition
/* active:   */ bg-accent-700 text-white
/* inactive: */ bg-transparent text-neutral-700
```
wrapped in `flex gap-1.5 bg-white border border-divider rounded-full p-1`.

---

## 6. Form controls

**Pill text input** (`.input` role — search, auth fields, sidebar dates):
```
rounded-full border border-divider bg-white px-4 py-[11px] text-[15px] text-ink
placeholder:text-neutral-500 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-100
```
Search-bar input itself is borderless/transparent (the pill *is* the search
bar's outer container, per §4 spacing table) — larger text (30px, display
font) per §2.

**Field label:** `block text-sm font-bold text-ink mb-1.5`.

---

## 7. Badges & icons

- **Distance badge**: white/88%-opacity pill, blurred backdrop, uppercase
  11px neutral-800 text — see §4.
- **Star rating icon**: solid star, `fill: var(--color-accent)`, 12–14px.
- **Check icon** (trust/included lists): `stroke: accent2-700`, 2.75 stroke
  width, 16–18px.
- **Shield icon** (fine-print, trust note): `stroke: accent2-700`.
- All icons: Heroicons-style outline, `stroke-width: 2.75` (heavier than
  v1/v2's `2`), `stroke-linecap: round`. Filled icons (star) use
  `fill="currentColor"` or a pinned accent fill, no stroke.

---

## 8. Avatars

```
rounded-full bg-accent2-300 text-accent2-800 font-display font-bold
grid place-items-center
```
Sizes: `34px` (nav), `62px` (detail owner strip). Content: `user.initials`.

---

## 9. Motion

- Card image lift on hover: `translateY(-4px)`, `280ms cubic-bezier(.2,.7,.3,1)`.
- Buttons/pills: default Tailwind `transition` (150ms) on background/border/color.

---

## 10. Redesign checklist (apply when migrating a new page to v3)

- [ ] Page background `bg-white`; panels use `bg-surface` + `border-divider`, not `bg-white` + `border-gray-*`.
- [ ] Headlines/prices/buttons use `font-display` (Barlow Condensed), uppercase where the source shows uppercase.
- [ ] Exact px sizes from §2/§3 via arbitrary-value classes — don't round to the nearest Tailwind step.
- [ ] Every button/pill/input is `rounded-full` (cards/panels use `rounded-3xl`/`rounded-2xl`).
- [ ] Primary = `bg-accent`; secondary = white + `border-divider`; active toggle = `bg-accent-700`.
- [ ] No fabricated data — if the mockup shows a field with no backing model column, replace with real data or drop it (see §0.3 for the running list of these adaptations).
- [ ] Keep v1 `navy`/`teal`/`sand`/`font-sora` tokens untouched for not-yet-migrated pages.

---

## 11. Body text weight (2026-09-05, bumped 2026-09-06)

`<body>` carries `font-semibold` (Manrope 600) as the site-wide default, not
the browser's normal 400. Plain paragraph text with no explicit `font-*`
utility (subtitles under headings, meta lines, descriptions) inherits this, so
it pairs properly against the heavy `font-display` (Barlow Condensed 700)
headings instead of reading as thin/mismatched. Elements that already set
their own weight (`font-bold`, etc.) are unaffected — this only changes the
*default* for text that doesn't specify one. Don't add `font-normal` back to
body copy; if something needs to look lighter, that's a color/size choice
(`text-neutral-600` etc.), not a weight one.

Verified twice, not just assumed from the CSS: confirmed via
`getComputedStyle(document.body).fontWeight` in-browser on `/my-rentals` that
the value actually applies (not just present in source), then A/B-compared
500 vs 600 side by side on the real subtitle text and 600 read clearly better
against the heading — the original 500 (from the first pass) was too close to
the browser default to read as an intentional pairing.

## 12. Nav hierarchy (2026-09-05)

The header nav is grouped into three visually distinct clusters, left to
right: **marketing links** (How it works, Trust & deposits — plain text,
`lg:` and up only), **account links** (My Rentals, My Listings — only when
signed in, separated from the marketing links by a `border-l border-divider`),
then the **List an item CTA pill** (`bg-accent`, always the one filled pill in
the nav), then the avatar menu / sign-in. The CTA is deliberately the only
filled pill so it reads as *the* highlight rather than one interruption among
several — don't add another filled pill to the nav without reconsidering this
hierarchy. "How it works" / "Trust & deposits" link to `#how-it-works` /
`#trust-safety` anchors on the homepage (§13), not to standalone pages.

## 13. Homepage sections below the grid (2026-09-05)

`index.html` continues past the item grid with four full-bleed sections
(alternating `bg-surface` / `bg-white`, each `id`-anchored for the nav links
in §12), then the shared footer:

1. `#how-it-works` — 3-step visual (Browse & request → Verified handover →
   Return & review), links out to the full `/how-it-works` page for detail.
2. `#trust-safety` — the 4 trust mechanisms (verified identities, deposit
   protection, evidence photos, Trust & Safety Fund) consolidated in one
   place instead of scattered across pages; links out to `/trust-deposits`.
3. Stats row (`bg-accent-700`, high-contrast) — **real numbers from the DB**,
   never hardcoded: `listings_service.total_listings_count()`,
   `booking_service.completed_count()`, `reviews_service.
   platform_average_rating()`, computed in `web.index` and passed as `stats`.
   Average rating shows "—" / "No ratings yet" when nobody has left a review
   rather than fabricating a number.
4. `#faq` — a 5-question accordion using native `<details>/<summary>` (no JS
   library needed — `group-open:rotate-45` on a plus icon gives the
   expand/collapse affordance). Answers are grounded in actual backend
   behavior (e.g. the cancellation-policy answer matches exactly what
   `booking_service.cancel()` allows), not generic marketing copy.

The footer (`base.html`) is a single minimal row: a real `©
{{ current_year }} CIRCLO` copyright line (year injected by the
`inject_current_year` context processor in `app/__init__.py`, never
hardcoded) on the left, Privacy/Terms/Help on the right.
