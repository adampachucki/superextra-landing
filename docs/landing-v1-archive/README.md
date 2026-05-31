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
(the commit just before removal).

Inspect a single file without checking anything out:

```sh
git show landing-v1-design:src/routes/landing/+page.svelte
git show landing-v1-design:src/lib/components/Hero.svelte
```

Restore the files into a working branch:

```sh
git checkout -b restore-landing landing-v1-design -- \
  src/routes/landing \
  src/lib/components/Hero.svelte \
  src/lib/components/PlatformCards.svelte \
  src/lib/components/Audiences.svelte \
  src/lib/components/GetOnboard.svelte \
  src/lib/components/FAQ.svelte \
  src/lib/components/CTA.svelte
```

## What was removed

- **Route:** `src/routes/landing/+page.svelte`, `src/routes/landing/+page.ts`
- **Components** (used only by that route):
  `Hero`, `PlatformCards`, `Audiences`, `GetOnboard`, `FAQ`, `CTA`
- **Navbar:** the dual-mode `Navbar` was collapsed to its single live (hamburger-less)
  form. The old `minimal={false}` mode — center nav links, the mobile hamburger, and
  the slide-down mobile menu — only existed for this landing page. The tag has the
  original `Navbar.svelte` if those interactions are needed again.
- **Message keys:** `nav_intelligence`, `nav_use_cases`, `nav_faq`, `nav_toggle_menu`
  (removed from `messages/{en,de,pl}.json`). The section components' own keys
  (`hero_*`, `faq_*`, etc.) were left in place — restoring from the tag expects them.

## What was intentionally kept

- The `firebase.json` 301 redirects from `/landing` (and `/de/landing`, `/pl/landing`)
  to the agent home still stand, so any old links keep resolving.
