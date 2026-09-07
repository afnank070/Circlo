# CIRCLO — Backlog / Deferred Items

_This file is the permanent memory for anything flagged as "later" during development.
Update it every time something is deferred — don't rely on chat history alone._

## Account & Profile
- [ ] Profile page: add profile picture upload
- [ ] Profile page: consider a separate "Settings" page for users (currently minimal)
- [ ] Admin settings page: currently only contains payment-related config — expand as needed

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

## Explicitly rejected / not doing
- In-app real-time chat — decided against for now; using phone number reveal +
  pickup location/map link instead (simpler, already built).
- Mobile app (M6 API work) — deferred indefinitely, not currently planned.

---
_Whenever an item here gets built, move it to PROGRESS.md's "Done" history and delete it
from this file. Whenever something new gets deferred mid-task, add it here immediately —
don't wait._
