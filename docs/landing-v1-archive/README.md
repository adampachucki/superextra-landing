# Landing page v1 — archive

The original generic marketing landing page (the `/landing` route and its
section components) was retired and removed from `main`. It was the pre-restaurant
design: a `Hero`, platform cards, audience grid, use cases, onboarding, FAQ, and a
generic CTA. The live home page (`/`) now uses the restaurant-specific hero/CTA
instead, so nothing else referenced these files.

This folder preserves the design so it can be brought back cleanly in the future,
without keeping dead code in the active source tree (where it would keep getting
built, type-checked, linted, and translated, and would rot against future changes).

## What it looked like

Full-page screenshots, captured before removal:

- `landing-desktop-light.png` / `landing-desktop-dark.png` — 1440px wide
- `landing-mobile-light.png` / `landing-mobile-dark.png` — 390px wide

## How to recover the code

The exact, buildable source lives at the annotated git tag **`landing-v1-design`**
(commit `50ecf60`, just before removal).

Inspect a single file without checking anything out:

```sh
git show landing-v1-design:src/routes/landing/+page.svelte
git show landing-v1-design:src/lib/components/Hero.svelte
```

Restore the files. Create the branch first, then check out the paths from the tag
(`git checkout -b <branch> <tag> -- <paths>` is invalid — you cannot switch branch
and check out paths in one command):

```sh
git checkout -b restore-landing
git checkout landing-v1-design -- \
  src/routes/landing \
  src/lib/components/Hero.svelte \
  src/lib/components/PlatformCards.svelte \
  src/lib/components/PlatformCard.svelte \
  src/lib/components/Audiences.svelte \
  src/lib/components/GetOnboard.svelte \
  src/lib/components/FAQ.svelte \
  src/lib/components/CTA.svelte \
  src/lib/components/mockups \
  messages
```

`messages/` is restored wholesale because the design's ~68 message keys
(`hero_l_*`, `hero_feat*`, `pc_*`, `aud_*`, `onboard_*`, `faq_*`, `cta_l_text`)
were deleted from the active catalogs — the tag has the full set. After restoring,
diff `messages/*.json` against the tag and re-add only the missing keys so you don't
clobber translations added since.

To actually serve the page again you must also undo the hosting retirement:

- Restore `src/lib/components/Navbar.svelte` from the tag if you need the old
  dual-mode navbar (center nav links + mobile hamburger). The current navbar has no
  `minimal` / `static` props.
- In `firebase.json`, the `landing` Hosting target now 301-redirects the whole domain
  to `agent.superextra.ai`. Re-add a route/rewrite for `/landing` (and locale
  variants) so the page is reachable, and set `prerender` back on if you want it
  emitted at build time.

## What was removed

- **Route:** `src/routes/landing/{+page.svelte,+page.ts}`
- **Components** (reachable only through that route): `Hero`, `PlatformCards`,
  `PlatformCard`, `Audiences`, `GetOnboard`, `FAQ`, `CTA`, and the whole
  `src/lib/components/mockups/` cluster (8 files).
- **Navbar:** the dual-mode `Navbar` was collapsed to its single live
  (hamburger-less) form — the `minimal` and `static` props, the center nav, the
  mobile hamburger, and the slide-down mobile menu are gone.
- **Message keys:** the four landing-nav keys (`nav_intelligence`, `nav_use_cases`,
  `nav_faq`, `nav_toggle_menu`) plus the ~68 section-content keys listed above, from
  `messages/{en,de,pl}.json`.
- **Hosting:** `static/robots-landing.txt` and the landing target's bespoke
  rewrites/redirects — the target is now a single catch-all redirect to the agent
  domain.
