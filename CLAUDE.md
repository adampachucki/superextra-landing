# Superextra Landing Page

AI-native market intelligence and competitor benchmarking for the restaurant industry. Four layers: data sources → platform → AI agents → human experts. Prerendered static SvelteKit site deployed to Firebase Hosting.

## Commands

- `npm run dev` — port 5199, exposed on local network (`host: true`) for mobile testing
- `npm run build` / `npm run check`
- Deploy: push to `main` → GitHub Actions → Firebase (project: superextra-site)

## Branding

- Name is **Superextra** — not SuperExtra, Super Extra, or SUPEREXTRA
- Avoid "you/your" — product-focused, Apple-style, minimalistic tone
- Four layers: data sources → platform → AI agents → human experts — lead with outcomes, not any single layer
- "Platform" is valid but shouldn't headline — it's one layer, not the whole product
- Use "service", "delivered", "combined" — don't lead with "platform" or "dashboard" alone
- CTAs: "Get Started" (not "Get Access")
- Refer to `docs/copy.md`, `docs/notes.md`, `docs/scope.md` when working on copy or features

## Stack

- SvelteKit 2 + **Svelte 5** + TypeScript (strict)
- **Tailwind CSS v4** — `@theme`, `@utility`, `@plugin` syntax (not v3)
- adapter-static, Firebase Hosting + Cloud Functions (Node 22), Resend, Google Places API

## Svelte 5 — no legacy syntax

```svelte
let { title }: { title: string } = $props()
let open = $state(false)
let valid = $derived(name !== '')
$effect(() => { … return () => cleanup() })
{#snippet label()}{/snippet} → {@render label()}
```

No `export let`, `$:`, `on:click`, or `<slot>`.

## Tailwind v4

- Custom utility `btn-primary` in `src/app.css`
- Desktop-first — `md:` breakpoint adapts down to mobile
- Fluid type: `text-[clamp(2rem,4vw,3.25rem)]`
- Container: `mx-auto max-w-[1200px] px-6`

## Dark mode

- Class-based dark mode via `.dark` on `<html>` — configured with `@variant dark` in `app.css`
- CSS variables (`--color-cream`, `--color-text`, `--mockup-text`, `--mockup-bg`) swap in `:root.dark`
- Theme toggle in footer cycles light → dark → system; state persisted in `localStorage('se_theme')`
- `theme` singleton (`theme.svelte.ts`) manages mode — follows `formState` pattern
- **All new/changed UI must support both modes** — use `dark:` variants for `text-black`/`border-black` patterns (e.g. `text-black dark:text-white`, `border-black/10 dark:border-white/10`)
- Cream-based classes (`bg-cream`, `border-cream-200`) auto-switch via CSS variables — no `dark:` needed
- Mockup `<style>` blocks use `rgba(var(--mockup-text), X)` and `rgb(var(--mockup-bg))` — not hardcoded `rgba(0,0,0,...)` or `#fff`
- SVGs should use `stroke="currentColor"` / `fill="currentColor"` with `text-black dark:text-white` on the parent
- Default is light; inline script in `app.html` prevents FOUC

## Patterns

- Components are self-contained — data defined inline, types inline in `$props()`
- CSS keyframes + `animation-delay` for staggered animations (not Svelte transitions)
- Visibility classes (`max-lg:hidden`/`lg:hidden`) — never duplicate blocks for mobile/desktop
- `formState` singleton (`form-state.svelte.ts`) controls access form modal
- `/api/intake` → Cloud Function → Resend email; dev proxy in vite.config.ts

## Don'ts

- No Svelte 4 syntax (`export let`, `$:`, `on:click`, `<slot>`)
- No Tailwind v3 config (`tailwind.config.js`, `@apply` in components)
- No duplicating mobile/desktop blocks — use visibility classes
- No killing processes on other ports — ask if 5199 is occupied
