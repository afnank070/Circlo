# CIRCLO — Backlog / Deferred Items

_This file is the permanent memory for anything flagged as "later" during development.
Update it every time something is deferred — don't rely on chat history alone._

## Account & Profile
- [ ] Profile page: add profile picture upload
- [ ] Profile page: consider a separate "Settings" page for users (currently minimal)
- [ ] Admin settings page: has payment config + user management (promote/revoke admin,
      2026-09-09) — expand further as needed
- [ ] Admin settings: commission rate — currently hardcoded at 20%, deferred until real
      transaction volume / real payment gateway makes it worth making dynamically
      configurable (need to decide retroactive vs new-bookings-only when this becomes real)
- [ ] Admin settings: minimum rental hours — hardcoded at 1, deferred, unlikely to need
      changing soon
- [ ] Admin settings: platform contact info — hardcoded in templates, deferred, unlikely
      to change soon since contact@circlo.pk is on our own domain

## Trust & Payments
- [ ] **In-app disclaimer: owner payout timing.** Owners must clearly understand payout
      happens AFTER rental completion, not immediately on acceptance. Add clear copy
      wherever an owner accepts a request and/or on the booking status card.
- [ ] Real payment gateway integration (EasyPaisa/JazzCash/card via Safepay or similar) —
      BLOCKED on company bank account existing. No code work possible until then.
- [ ] Business model decision: current escrow + 20% commission model vs. a simpler
      Peerby-style direct-pay + separate platform fee model. Revisit before public launch.
- [ ] SMS/phone OTP — deferred due to per-message cost. Revisit once budget/scale justifies it.
- [ ] Automated CNIC verification (replace manual admin approval) — revisit at ~500+ users.

## Search & Discovery
- [ ] "Sort by distance" — currently a decorative label with no function (fix in progress).
- [ ] Real distance/proximity calculation — needs user geolocation or area-based estimate.
      Bigger feature, not urgent.
- [ ] Search typo-tolerance / fuzzy matching — never verified if current search is forgiving
      enough (e.g. "camping tent" vs "tent").
- [ ] Auto-expire stale pending rental requests (e.g. after 48h with no owner response).

## Support & Content
- [ ] Visible "Contact us" form on-site — currently only an email address (contact@circlo.pk),
      no actual form/channel embedded in the product.
- [ ] Replace/clean seed/demo data before real users see the site (currently shows test
      listings like "Bosch drill", "Canon camera" etc. with fake reviews).

## Infrastructure & Hardening
- [ ] Confirm Google OAuth consent screen moved from Testing → Production (unverified).
- [ ] Add www → non-www (or vice versa) redirect at Cloudflare/DNS level for URL consistency.
- [ ] Mobile responsiveness — never explicitly tested on a real phone across core flows.
- [ ] Email deliverability — confirm notifications land in inbox (not spam) across providers
      other than the one used for testing so far.

## Known bugs — non-functional UI found during testing
- [ ] "Message" button on the owner card (listing detail page, `/listings/<id>`) is
      static/non-functional — leftover from before in-app chat was rejected in favor of
      phone reveal + pickup location. Either remove the button, or repoint it to the
      phone-reveal flow (post-acceptance), or hide it until a booking is accepted.

## Booking model change — hourly rentals (real feature, not a quick patch)
- [ ] **Change minimum rental unit from days to hours.** Currently bookings are date-range
      only (whole days). Need to support hourly rentals (e.g., rent a projector for 3 hours).
      This is NOT a simple relabeling — must be done properly end-to-end:
      - Booking model: date+time range instead of date-only (start/end datetime, not just date)
      - Pricing: price/day vs price/hour — decide if listings need BOTH rates, or owners pick
        one pricing unit per listing, and how the total is calculated correctly either way
      - Request-to-rent form: needs time pickers, not just date pickers
      - All booking cards/displays (My Rentals, admin panels, emails) that currently show
        "X days" need to correctly show hours where relevant
      - Availability/overlap-checking logic (already built for date ranges) needs to work
        correctly with hour-level granularity, not just whole-day granularity
      - This touches Booking model, listing form, pricing display everywhere (browse cards,
        detail page, checkout), and probably the ledger/commission calculation too
      - Explicitly flagged: no shortcuts, no half-implemented flow — full proper support
        across the whole booking lifecycle, not just the request form.

## Explicitly rejected / not doing
- In-app real-time chat — decided against for now; using phone number reveal +
  pickup location/map link instead (simpler, already built).
- Mobile app (M6 API work) — deferred indefinitely, not currently planned.

---
_Whenever an item here gets built, move it to PROGRESS.md's "Done" history and delete it
from this file. Whenever something new gets deferred mid-task, add it here immediately —
don't wait._
