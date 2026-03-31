# Plan: Add Polish (de) and German (pl) Localization

## Context

The Superextra landing site is evolving from a static marketing page into an app (agent chat, login, future dashboard). We need to add Polish and German versions of all marketing pages while keeping app pages (chat, future dashboard) locale-free. This requires:

1. Paraglide (Inlang) for type-safe, compile-time translations
2. SvelteKit layout groups to separate marketing (locale-prefixed, prerendered) from app (no prefix, SPA)
3. ~300 strings extracted from ~15 components + 3 long-form pages translated

## Architecture

```
Marketing zone (prerendered, locale in URL):
  /en/          /de/          /pl/
  /en/agent     /de/agent     /pl/agent
  /en/memo      /de/memo      /pl/memo
  /en/privacy-policy  /de/privacy-policy  /pl/privacy-policy
  /en/terms     /de/terms       /pl/terms

App zone (SPA, locale from cookie/preference):
  /agent/chat

Standalone (no locale prefix):
  /login
  /mockups (internal)

Root / redirects to /en/ (or detected locale)
```

## Route Structure After Restructure

```
src/routes/
├── +layout.svelte           ← root: app.css, scroll restore, CookieBanner, password wall
├── +layout.ts               ← prerender = 'auto' (not true — groups override)
├── +page.svelte             ← redirect / → /en/
├── (marketing)/
│   ├── +layout.svelte       ← Navbar slot, Footer, meta tags, hreflang, PreviewBadge
│   ├── +layout.ts           ← prerender = true
│   ├── +page.svelte         ← homepage (Hero, About, PlatformCards, etc.)
│   ├── agent/+page.svelte   ← agent landing
│   ├── memo/+page.svelte
│   ├── privacy-policy/+page.svelte
│   └── terms/+page.svelte
├── (app)/
│   ├── +layout.svelte       ← minimal app shell
│   ├── +layout.ts           ← prerender = false, ssr = false
│   └── agent/chat/+page.svelte
├── login/+page.svelte
└── mockups/+page.svelte
```

---

## Phase 0: Install Paraglide + Configure

### 0.1 Install

```bash
npx sv add paraglide="languageTags:en,de,pl"
```

This scaffolds: `project.inlang/settings.json`, Vite plugin, hooks files, updates app.html and .gitignore.

### 0.2 Configure Vite plugin — `vite.config.ts`

Add Paraglide plugin with `urlPatterns` that define which routes get locale prefixes:

```ts
import { paraglide } from '@inlang/paraglide-js';

export default defineConfig({
  plugins: [
    tailwindcss(),
    paraglide({
      project: './project.inlang',
      outdir: './src/lib/paraglide',
      strategy: ['url', 'cookie', 'baseLocale'],
      urlPatterns: [
        // Homepage — explicit to avoid redirect loops
        {
          pattern: '/',
          localized: [['en', '/en'], ['de', '/de'], ['pl', '/pl']]
        },
        // Marketing pages — locale-prefixed
        {
          pattern: '/agent',
          localized: [['en', '/en/agent'], ['de', '/de/agent'], ['pl', '/pl/agent']]
        },
        {
          pattern: '/memo',
          localized: [['en', '/en/memo'], ['de', '/de/memo'], ['pl', '/pl/memo']]
        },
        {
          pattern: '/privacy-policy',
          localized: [['en', '/en/privacy-policy'], ['de', '/de/privacy-policy'], ['pl', '/pl/privacy-policy']]
        },
        {
          pattern: '/terms',
          localized: [['en', '/en/terms'], ['de', '/de/terms'], ['pl', '/pl/terms']]
        },
        // App routes — SAME URL for all locales (locale from cookie)
        {
          pattern: '/agent/chat/:path(.*)?',
          localized: [
            ['en', '/agent/chat/:path(.*)?'],
            ['de', '/agent/chat/:path(.*)?'],
            ['pl', '/agent/chat/:path(.*)?']
          ]
        },
        {
          pattern: '/login',
          localized: [['en', '/login'], ['de', '/login'], ['pl', '/login']]
        }
      ]
    }),
    sveltekit()
  ],
  server: { /* existing proxy config unchanged */ }
});
```

Key: marketing routes have different paths per locale; app routes have identical paths (locale falls back to cookie/baseLocale).

### 0.3 Hooks — `src/hooks.ts`

```ts
import type { Reroute } from '@sveltejs/kit';
import { deLocalizeUrl } from '$lib/paraglide/runtime';

export const reroute: Reroute = (request) => deLocalizeUrl(request.url).pathname;
```

### 0.4 Hooks — `src/hooks.server.ts`

```ts
import type { Handle } from '@sveltejs/kit';
import { paraglideMiddleware } from '$lib/paraglide/server';

export const handle: Handle = ({ event, resolve }) =>
  paraglideMiddleware(event.request, ({ request, locale }) => {
    event.request = request;
    return resolve(event, {
      transformPageChunk: ({ html }) =>
        html.replace('%lang%', locale).replace('%dir%', 'ltr')
    });
  });
```

### 0.5 Update `app.html`

Change `<html lang="en">` to `<html lang="%lang%" dir="%dir%">`.

### 0.6 Update `svelte.config.js`

```js
kit: {
  adapter: adapter({ fallback: '200.html' }),  // changed from 404.html for SPA fallback
  paths: { relative: false }                    // required for static + i18n
}
```

### 0.7 Inlang config — `project.inlang/settings.json`

```json
{
  "sourceLanguageTag": "en",
  "languageTags": ["en", "de", "pl"],
  "modules": [
    "https://cdn.jsdelivr.net/npm/@inlang/plugin-message-format@latest/dist/index.js"
  ],
  "plugin.inlang.messageFormat": {
    "pathPattern": "./messages/{locale}.json"
  }
}
```

### 0.8 Create initial message files

- `messages/en.json` — single test key: `{ "test": "Hello" }`
- `messages/de.json` — `{ "test": "Hallo" }`
- `messages/pl.json` — `{ "test": "Cześć" }`

### 0.9 Update `.gitignore`

Add `src/lib/paraglide/`.

### Verify Phase 0

Run `npm run build`. Confirm build succeeds and output contains `/en/`, `/de/`, `/pl/` directories for marketing pages.

---

## Phase 1: Route Restructuring

Move files into layout groups. No text changes — site looks identical after.

### 1.1 Create `(marketing)` group

Create `src/routes/(marketing)/`. Move into it:
- `+page.svelte` (homepage)
- `agent/+page.svelte` (agent landing — NOT agent/chat/)
- `memo/+page.svelte`
- `privacy-policy/+page.svelte`
- `terms/+page.svelte`

Create `src/routes/(marketing)/+layout.ts`:
```ts
export const prerender = true;
```

Create `src/routes/(marketing)/+layout.svelte` — extract from current root layout:
- `<svelte:head>` meta tags (og:title, og:description, twitter)
- PreviewBadge component
- Wrap `{@render children()}` (Navbar/Footer stay in page components as they are now)

### 1.2 Create `(app)` group

Create `src/routes/(app)/`. Move `agent/chat/+page.svelte` into `src/routes/(app)/agent/chat/+page.svelte`.

Create `src/routes/(app)/+layout.ts`:
```ts
export const prerender = false;
export const ssr = false;
```

Create `src/routes/(app)/+layout.svelte` — minimal: just `{@render children()}`.

### 1.3 Slim root layout — `src/routes/+layout.svelte`

Keep:
- `import '../app.css'`
- Scroll restoration logic (lines 9-30)
- CookieBanner
- Password wall (disabled)
- `{@render children()}`

Move to `(marketing)/+layout.svelte`:
- All `<svelte:head>` meta tags
- PreviewBadge + pathname conditional

### 1.4 Root `+layout.ts`

Remove `export const prerender = true` (each group now controls its own).

### 1.5 Create root redirect — `src/routes/+page.svelte` or `+page.ts`

Redirect bare `/` to `/en/`:
```ts
// src/routes/+page.ts
import { redirect } from '@sveltejs/kit';
export const prerender = true;
export function load() {
  redirect(307, '/en/');
}
```

### Verify Phase 1

All existing functionality works. `npm run build` succeeds. Marketing pages prerender. `/agent/chat` works via SPA fallback.

---

## Phase 2: String Extraction (Component by Component)

Extract hardcoded English text into `messages/en.json`. Replace inline text with `m.key()` calls. Each component is an independent unit of work.

Import pattern added to each component:
```svelte
<script lang="ts">
  import { m } from '$lib/paraglide/messages.js';
  import { localizeHref } from '$lib/paraglide/runtime.js';
</script>
```

### Components to extract (in suggested order):

| # | Component | File | Approx Keys | Notes |
|---|-----------|------|-------------|-------|
| 1 | Navbar | `src/lib/components/Navbar.svelte` | 8 | + localizeHref for all `href` attributes |
| 2 | Footer | `src/lib/components/Footer.svelte` | 8 | + language switcher added here + localizeHref |
| 3 | CookieBanner | `src/lib/components/CookieBanner.svelte` | 2 | + localizeHref for privacy link |
| 4 | Hero | `src/lib/components/Hero.svelte` | 12 | Headline, tagline, 3 feature cards |
| 5 | About | `src/lib/components/About.svelte` | 5 | Default prop values become m.() calls |
| 6 | PlatformCards | `src/lib/components/PlatformCards.svelte` | 20 | Section strings + 7 cards + show more/less |
| 7 | UseCases | `src/lib/components/UseCases.svelte` | 20 | Default items array + section strings |
| 8 | GetOnboard | `src/lib/components/GetOnboard.svelte` | 8 | 3 steps + section header |
| 9 | FAQ | `src/lib/components/FAQ.svelte` | 18 | 8 Q&A pairs + section header |
| 10 | DataSources | `src/lib/components/DataSources.svelte` | 3 | Title, subtitle, "And more" |
| 11 | CTA | `src/lib/components/CTA.svelte` | 3 | Message + 2 buttons |
| 12 | AccessForm | `src/lib/components/AccessForm.svelte` | 55 | Largest: 3-step form, business types, countries, labels, placeholders, validation, success/error |
| 13 | RestaurantHero | `src/lib/components/restaurants/RestaurantHero.svelte` | 25 | 6 prompts (desktop+mobile), headline, topic pills, placeholders |
| 14 | HowItWorks | `src/lib/components/restaurants/HowItWorks.svelte` | 8 | 3 steps + section header |
| 15 | RestaurantCTA | `src/lib/components/restaurants/RestaurantCTA.svelte` | 3 | Headline + subtitle + aria |

### Route pages with inline text:

| # | Page | File | Approx Keys | Notes |
|---|------|------|-------------|-------|
| 16 | Agent landing | `src/routes/(marketing)/agent/+page.svelte` | 20 | 8 restaurant use cases defined inline + About/UseCases/DataSources prop overrides |
| 17 | Chat page | `src/routes/(app)/agent/chat/+page.svelte` | 30 | Prompts, sidebar labels, placeholders, relative time strings |
| 18 | Login page | `src/routes/login/+page.svelte` | 15 | Form labels, placeholders, footer links |
| 19 | Marketing layout | `src/routes/(marketing)/+layout.svelte` | 5 | Meta tag content |

**Total: ~300 message keys**

### Message key naming convention

```
{component}_{element}
```
Examples: `navbar_link_intelligence`, `hero_headline`, `hero_tagline`, `faq_q1_question`, `faq_q1_answer`, `access_form_step1_title`, `access_form_business_single_venue`

### Link localization

Every `href` pointing to a marketing page needs `localizeHref()`:
- `href="/"` → `href={localizeHref('/')}`
- `href="/privacy-policy"` → `href={localizeHref('/privacy-policy')}`
- `href="/agent"` → `href={localizeHref('/agent')}`

Links to app/standalone pages stay absolute:
- `href="/agent/chat"` — unchanged
- `href="/login"` — unchanged

### Language switcher in Footer

Add after theme toggle in `Footer.svelte`:
```svelte
<script>
  import { locales, localizeHref, getLocale } from '$lib/paraglide/runtime.js';
  import { page } from '$app/state';
</script>

{#each locales as locale}
  <a
    href={localizeHref(page.url.pathname, { locale })}
    class:active={getLocale() === locale}
  >
    {locale.toUpperCase()}
  </a>
{/each}
```

### Verify Phase 2

Site displays identically in English. All links work. Language switcher navigates between `/en/`, `/de/`, `/pl/` (showing English text for all — translations come in Phase 4).

---

## Phase 3: Long-Form Pages

Privacy policy, terms, and memo are full documents (~7.5k words total). Too large for individual message keys. Use per-locale Svelte components.

### 3.1 Create content directory

```
src/lib/content/
├── privacy-policy/
│   ├── en.svelte
│   ├── de.svelte
│   └── pl.svelte
├── terms/
│   ├── en.svelte
│   ├── de.svelte
│   └── pl.svelte
└── memo/
    ├── en.svelte
    ├── de.svelte
    └── pl.svelte
```

Each file contains the full HTML content in that language. The page components dynamically import the correct locale:

```svelte
<!-- src/routes/(marketing)/privacy-policy/+page.svelte -->
<script lang="ts">
  import { getLocale } from '$lib/paraglide/runtime.js';
  import En from '$lib/content/privacy-policy/en.svelte';
  import De from '$lib/content/privacy-policy/de.svelte';
  import Pl from '$lib/content/privacy-policy/pl.svelte';

  const components = { en: En, de: De, pl: Pl } as const;
  const Content = components[getLocale() as keyof typeof components];
</script>

<Content />
```

### 3.2 Memo page specifics

The memo page has a HeroCanvas header and `marked` for markdown. Extract the chrome (header, canvas, article wrapper) into the page component. Move the body content into per-locale components.

### Verify Phase 3

Legal pages render correctly for all locales (English content initially, de/pl filled in Phase 4).

---

## Phase 4: Translations

Populate `messages/de.json`, `messages/pl.json`, and the per-locale long-form content files.

### 4.1 UI strings (~300 keys)

Direct translation of all message keys. Paraglide falls back to English for any missing key, so this can be done incrementally.

### 4.2 Legal documents

Professional translation of privacy policy and terms for DE and PL markets. Follow local legal best practices (GDPR for DE, Polish data protection law for PL).

### 4.3 Memo

Editorial translation of the manifesto page.

### Verify Phase 4

All 3 locales display correct translated content. Language switching works end-to-end.

---

## Phase 5: SEO + Deployment

### 5.1 hreflang tags

Add to `(marketing)/+layout.svelte`:

```svelte
<script>
  import { locales, localizeHref } from '$lib/paraglide/runtime.js';
  import { page } from '$app/state';
</script>

<svelte:head>
  {#each locales as locale}
    <link rel="alternate" hreflang={locale}
      href="https://superextra.ai{localizeHref(page.url.pathname, { locale })}" />
  {/each}
  <link rel="alternate" hreflang="x-default"
    href="https://superextra.ai{localizeHref(page.url.pathname, { locale: 'en' })}" />
</svelte:head>
```

### 5.2 Update Firebase config — `firebase.json`

```json
{
  "hosting": {
    "site": "superextra-landing",
    "public": "build",
    "cleanUrls": true,
    "redirects": [
      { "source": "/", "destination": "/en/", "type": 302 },
      { "source": "/agent", "destination": "/en/agent", "type": 302 },
      { "source": "/privacy-policy", "destination": "/en/privacy-policy", "type": 302 },
      { "source": "/terms", "destination": "/en/terms", "type": 302 },
      { "source": "/memo", "destination": "/en/memo", "type": 302 }
    ],
    "rewrites": [
      { "source": "/api/intake", "function": "intake" },
      { "source": "/api/agent", "function": "agent" },
      { "source": "**", "destination": "/200.html" }
    ]
  }
}
```

Redirects catch old non-prefixed marketing URLs → English. Use 302 initially, upgrade to 301 when stable. English slugs kept for legal pages (no translated slugs).

### 5.3 Sitemap

Generate sitemap with all locale variants. Either maintain manually or add a build script.

### Verify Phase 5

- `/` redirects to `/en/`
- `/en/`, `/de/`, `/pl/` serve localized homepages
- Language switcher works across all marketing pages
- `/agent/chat` works without locale prefix
- `/login` works without locale prefix
- `/api/*` endpoints unchanged
- Dark mode works in all locales
- AccessForm modal works in all locales
- hreflang tags present on marketing pages
- `npm run build` succeeds with all locale variants in output

---

## Key Files Modified

| File | Change |
|------|--------|
| `vite.config.ts` | Add Paraglide plugin + urlPatterns |
| `svelte.config.js` | fallback → 200.html, paths.relative: false |
| `src/app.html` | lang="%lang%" dir="%dir%" |
| `src/hooks.ts` | NEW — reroute hook |
| `src/hooks.server.ts` | NEW — handle hook with paraglideMiddleware |
| `src/routes/+layout.svelte` | Slim down (move meta + PreviewBadge to marketing) |
| `src/routes/+layout.ts` | Remove prerender = true |
| `src/routes/+page.svelte` or `+page.ts` | NEW — redirect / → /en/ |
| `src/routes/(marketing)/+layout.svelte` | NEW — marketing shell |
| `src/routes/(marketing)/+layout.ts` | NEW — prerender = true |
| `src/routes/(app)/+layout.svelte` | NEW — app shell |
| `src/routes/(app)/+layout.ts` | NEW — prerender = false, ssr = false |
| All 15 components listed in Phase 2 | Extract strings → m.key() calls |
| 4 route pages listed in Phase 2 | Extract inline text |
| `firebase.json` | Add redirects for old URLs, SPA fallback |
| `messages/en.json` | NEW — ~300 message keys |
| `messages/de.json` | NEW — German translations |
| `messages/pl.json` | NEW — Polish translations |
| `src/lib/content/` | NEW — 9 per-locale content files (3 pages x 3 locales) |
| `project.inlang/settings.json` | NEW — Inlang project config |

## Risks and Mitigations

1. **Paraglide + adapter-static prerendering**: The reroute hook maps `/en/about` and `/de/about` to the same internal route. SvelteKit's crawler must discover all locale variants via language switcher links. Verify in Phase 0 that the build output contains all expected locale directories.

2. **Agent route split**: `/agent` (marketing, prerendered) and `/agent/chat` (app, SPA) live in different layout groups. SvelteKit resolves by specificity — `/agent/chat` is more specific. Test carefully.

3. **SPA fallback**: Changing from `fallback: '404.html'` to `'200.html'` to match Firebase's `** → /200.html` rewrite. The app zone (chat page) relies on this fallback since it's not prerendered.

4. **AccessForm complexity**: 612-line component with ~55 strings. Consider splitting into sub-components (FormStep1/2/3) during extraction to improve maintainability.

5. **Legal translations**: DE and PL privacy policy / terms need proper legal review, not just direct translation. Budget time for this.

6. **Old URL breakage**: External links to `/privacy-policy`, `/terms`, etc. will hit Firebase redirects → `/en/privacy-policy`. Single redirect hop, but update any hardcoded links in emails, Resend templates, etc.

## Execution Order

Phases 0+1 are foundational and must be done together. After that:
- Phase 2 can be done component by component (each is independently shippable)
- Phase 3 is independent of Phase 2
- Phase 4 depends on Phase 2+3 being complete
- Phase 5 can start after Phase 0+1, hreflang added early, Firebase config updated last
