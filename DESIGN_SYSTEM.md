# CIRCLO — Design System Reference (v2, "White & Forest")

Replaces the earlier navy/teal/sand system (preserved below other pages until
they're migrated — see §0). This is the **single source of truth** for every
future page. Built from reference screenshots: white background, forest-green
accent, bold black condensed headlines, fully pill-shaped controls, frameless
minimal listing cards.

The stack is Tailwind via CDN with a `tailwind.config` override in
`base.html` (`app/web/templates/base.html`). All custom tokens below are
defined there.

---

## 0. Migration status

- **Done (v2 applied):** shared header/footer (`base.html`), home/browse
  (`index.html`), listing detail (`listing_detail.html`).
- **Not yet migrated (still old navy/teal/sand look):** auth pages, my-rentals,
  my-listings, listing form, profile, admin queues, legal pages. These keep
  working against the old tokens (still defined in `tailwind.config` for
  backward compatibility) until their own redesign pass.
- Do not delete the old `navy` / `teal` / `sand` tokens or the `font-sora`
  family until every page has been migrated off them.

---

## 1. Color palette

### Green (primary accent — buttons, prices, active pill states, links)
| Token | Hex | Used for |
|---|---|---|
| `green-50`  | `#F1F8F4` | tinted panel backgrounds, hover fills |
| `green-100` | `#DCEEE2` | verified-pill background, soft badges |
| `green-200` | `#B9DDC6` | subtle rings/borders on tinted panels |
| `green-600` | `#1F6F4A` | link/hover state, secondary green accents |
| `green-700` | `#1B5E3F` | **primary button fill**, prices, active category pill, focus rings |
| `green-800` | `#154A32` | primary button hover/active |
| `green-900` | `#0F3D26` | rarely used — deepest text-on-tint |

### Ink (near-black — headlines, body text)
| Token | Hex | Used for |
|---|---|---|
| `ink` (DEFAULT) | `#0B0B0C` | hero headline, card titles, all bold caps text |
| `ink-700`       | `#27272A` | standard body copy |

### Neutral gray (Tailwind defaults — surfaces, borders, muted text)
| Role | Class |
|---|---|
| Page background | `bg-white` |
| Image placeholder / empty media block | `bg-gray-100` (`#F3F4F6`) |
| Card/section borders, pill outlines (inactive) | `border-gray-300` (`#D1D5DB`) |
| Dividers | `border-gray-200` |
| Muted/meta text (location, "8 items available", helper copy) | `text-gray-500` |
| Placeholder text in inputs | `text-gray-400` |
| Search bar fill | `bg-gray-100` |

### Semantic / status colors (unchanged from v1 — reused as-is)
| Purpose | Classes |
|---|---|
| Success / positive | `border-green-200 bg-green-50 text-green-800` |
| Error / destructive | `text-rose-600`, `border-rose-200 bg-rose-50 text-rose-700` |
| Warning / pending | `bg-amber-100 text-amber-800` |
| Rating stars | `text-amber-400` (filled), `text-gray-300` (empty) |
| Notification badge | `bg-rose-600 text-white` |

---

## 2. Typography

Fonts loaded from Google Fonts in `base.html`: **Archivo Black** (display,
900), **Manrope** (400–800, body/UI — unchanged from v1).

| Family | Tailwind class | Usage |
|---|---|---|
| Manrope | `font-sans` (default on `body`) | all body copy, labels, inputs, buttons, nav |
| Archivo Black | `font-display` | hero headline, item/listing names, big price figures — always with `uppercase` |

Body base: `body` has `font-sans text-ink-700 antialiased bg-white`.

### Heading scale (as used on migrated pages)
| Role | Classes |
|---|---|
| Hero H1 (home) | `font-display uppercase text-5xl sm:text-6xl leading-[0.95] tracking-tight text-ink` |
| Listing detail H1 | `font-display uppercase text-3xl sm:text-4xl leading-tight tracking-tight text-ink` |
| Card / listing item name | `font-display uppercase text-sm sm:text-base leading-snug tracking-tight text-ink line-clamp-2` |
| Section heading ("About this item") | `font-sans text-base font-extrabold uppercase tracking-wide text-ink` |
| Logo wordmark | `font-display uppercase text-xl tracking-tight text-ink` |

### Body / supporting text
| Role | Classes |
|---|---|
| Standard body | `text-sm text-ink-700 leading-relaxed` |
| Caption / meta (distance, area, "sorted by") | `text-xs text-gray-500` |
| Price figure | `font-display text-lg text-green-700` (card) → `font-display text-3xl text-green-700` (detail) |
| Prices always formatted | `Rs {{ "{:,}".format(value|int) }}` — "Rs" prefix, comma thousands, no decimals |
| Button label | `text-sm font-extrabold uppercase tracking-wide` |

---

## 3. Layout & spacing

| Pattern | Value |
|---|---|
| Page max width | `max-w-7xl` |
| Horizontal gutter | `px-4` |
| Hero vertical padding | `py-16 sm:py-20` |
| Section rhythm | `mt-8`–`mt-10` between major sections |
| Grid gap (card grids) | `gap-6` |
| Card grid columns | `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4` |
| Two-column detail | `grid-cols-1 lg:grid-cols-2 gap-10` |
| Header | `sticky top-0 z-30`, `bg-white`, `border-b border-gray-200` (no blur — flat white) |
| Footer | `mt-16 border-t border-gray-200 bg-white` |

---

## 4. Cards

**Listing card (frameless, minimal):**
```
group flex flex-col
```
- No border, no shadow, no rounded card wrapper — the card *is* just an image
  block + text stack.
- Image wrapper: `relative aspect-[4/3] overflow-hidden rounded-2xl bg-gray-100`
- Image: `h-full w-full object-cover transition duration-300 group-hover:scale-105`
- Distance badge: absolutely positioned top-left on the image (see §7).
- Text stack starts directly below the image, `mt-3`, no card padding/border.

**Content card (price/deposit box, owner card — detail page only):**
Kept as a bordered surface since the reference screenshots show these as
distinct panels, just restyled to the new palette:
```
rounded-2xl border border-gray-200 bg-white p-5
```
No `shadow-sm` — v2 favors flat borders over shadows.

**Empty state:**
```
rounded-2xl border border-dashed border-gray-300 bg-white py-16 text-center
```

---

## 5. Buttons

**Primary (forest green, pill):**
```
rounded-full bg-green-700 px-6 py-3 text-sm font-extrabold uppercase tracking-wide text-white
hover:bg-green-800 focus:outline-none focus:ring-2 focus:ring-green-200
```
Compact/nav variant: `px-5 py-2.5`.

**Secondary (outline on white, pill):**
```
rounded-full border border-gray-300 bg-white px-6 py-3 text-sm font-extrabold uppercase tracking-wide text-ink
hover:border-gray-400 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200
```

**Ghost / nav link:**
```
rounded-full px-3 py-2 text-sm font-semibold text-ink hover:bg-gray-100
```

**Destructive (outline):**
```
rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-bold text-rose-600 hover:bg-rose-50
```

All buttons are `rounded-full` in v2 — no more `rounded-xl` rectangles.

---

## 6. Form controls / search bar

**Pill search bar (home hero):**
Single fully-rounded container, divided into three zones — search icon +
input, a vertical divider, an "All areas" location button, and a docked
green SEARCH pill:
```
flex items-center gap-3 rounded-full border border-gray-200 bg-gray-100 p-2 pl-5
```
- Input: `flex-1 bg-transparent text-sm text-ink placeholder:text-gray-400 focus:outline-none`
- Location button: `hidden sm:inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-semibold text-ink hover:bg-white`
- Search button: `rounded-full bg-green-700 px-6 py-3 text-sm font-extrabold uppercase tracking-wide text-white hover:bg-green-800`

**Standard text input / select (detail page, forms):**
```
w-full rounded-2xl border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-ink
placeholder:text-gray-400
focus:border-green-600 focus:outline-none focus:ring-2 focus:ring-green-100
```

**Label:** `block text-sm font-bold text-ink`

---

## 7. Badges & pills

**Distance badge (top-left on card image):**
```
absolute left-3 top-3 rounded-full bg-white px-2.5 py-1 text-xs font-bold text-ink shadow-sm
```
Content: `{{ "%.1f"|format(distance_km) }} KM`

**Verified pill (on cards / overlaid on images):**
```
inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1
text-xs font-bold text-green-700 shadow-sm ring-1 ring-green-100
```

**Verified pill (inline, on tinted bg):**
```
inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5
text-xs font-bold text-green-700 ring-1 ring-green-100
```

**Category filter pill (home):**
```
shrink-0 rounded-full px-5 py-2.5 text-sm font-extrabold uppercase tracking-wide transition
/* active:   */ bg-green-700 text-white
/* inactive: */ bg-white text-ink border border-gray-300 hover:border-gray-400
```
(Matches the "black/dark when active" reference direction using the forest
green primary rather than pure black, so the active state still reads as the
brand accent.)

**Popular-search link (home, under search bar):**
```
text-sm font-semibold text-ink-700 underline decoration-gray-300 underline-offset-4 hover:text-green-700 hover:decoration-green-700
```

**Status dot:** `h-2 w-2 rounded-full bg-green-600` (available).

---

## 8. Avatars

```
grid place-items-center rounded-full bg-green-700 font-bold text-white
```
Sizes: `h-9 w-9 text-sm` (nav), `h-12 w-12 text-base` (owner card). Content is
`user.initials`.

---

## 9. Icons

Inline SVG only. Heroicons outline set (`fill="none" stroke="currentColor"
stroke-width="2"`) for line icons; solid (`fill="currentColor"`) for
check/star. Sizes: `h-4 w-4` inline with text, `h-5 w-5` in buttons.

Brand mark (header logo): wordmark only, no circle glyph —
`font-display uppercase text-xl tracking-tight text-ink` reading "CIRCLO",
with a small gray-500 uppercase caption beside it: `ISLAMABAD · RAWALPINDI`
(`text-xs font-semibold tracking-wide text-gray-500`).

---

## 10. Flash messages

Same structure as v1, restyled:
```
success → border-green-200 bg-green-50 text-green-800
error   → border-rose-200 bg-rose-50 text-rose-700
info    → border-gray-200 bg-gray-50 text-ink-700
```

---

## 11. Motion

- Card images: `transition duration-300 group-hover:scale-105`.
- Buttons/pills: default Tailwind `transition` (150ms) on background/border.
- No shadows-on-hover lift (v1's `-translate-y-0.5` is dropped — v2 favors flat,
  whitespace-driven hierarchy over elevation).

---

## 12. Redesign checklist (apply when migrating a new page to v2)

- [ ] Body/page background is plain `bg-white`, not `bg-slate-50`.
- [ ] Headlines/item names use `font-display uppercase`; body stays `font-sans`.
- [ ] Every button/pill/search bar is `rounded-full`.
- [ ] Primary action = `bg-green-700` solid; secondary = white + gray border outline.
- [ ] Listing cards are frameless: no border/shadow on the card, only on the
      image's `rounded-2xl bg-gray-100` placeholder.
- [ ] Prices: `Rs ` + comma thousands, `font-display text-green-700`.
- [ ] Category/filter pills: green-700 active, white+gray-300-border inactive.
- [ ] Keep old `navy`/`teal`/`sand` tokens untouched for not-yet-migrated pages.
