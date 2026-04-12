# Superextra Landing Page

AI-native market intelligence and competitor benchmarking for the restaurant industry. Four layers: data sources → platform → AI agents → human experts. Prerendered static SvelteKit site deployed to Firebase Hosting.

## Domains & hosting sites

- **This repo** deploys to two Firebase Hosting sites (both in project `superextra-site`):
  - `superextra-landing` → **`landing.superextra.ai`** (marketing landing page)
  - `superextra-agent` → **`agent.superextra.ai`** (agent UI)
- `superextra-site` is a separate hosting site serving `superextra.ai` (main marketing page) — not part of this repo
- Agent UI routes: `agent.superextra.ai/` (agent landing) and `agent.superextra.ai/chat`
- `landing.superextra.ai/agent` 301-redirects to `agent.superextra.ai`

## Dev server (port 5199)

The Vite dev server is managed by a **systemd user service** — it runs automatically and restarts on crash.

- **Service**: `superextra-dev.service` (`~/.config/systemd/user/superextra-dev.service`)
- **Config**: `Restart=always`, `RestartSec=3` — killing the process directly just respawns it 3s later
- **Restart**: `systemctl --user restart superextra-dev.service`
- **Status/logs**: `systemctl --user status superextra-dev.service`
- **Never run `npm run dev` manually** — it creates a duplicate instance on port 5200/5201, leading to stale HMR and confusion about which server the browser is hitting
- **Never `kill` the vite process directly** — use `systemctl --user restart` instead
- Port 5199, exposed on local network (`host: true`) for mobile testing

## Commands

- `npm run build` / `npm run check`
- `npm run lint` — Prettier check + ESLint
- `npm run format` — auto-format all files
- `npm run test` — run Vitest unit tests (SSE client, chat state)
- `cd functions && npm test` — run Cloud Function tests (utils, stream parser)
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — run agent Python tests
- Deploy: push to `main` → GitHub Actions → Firebase (project: superextra-site)

## Code Quality

- **Prettier** formats on save (Cursor) and pre-commit (husky + lint-staged)
- **ESLint** with `eslint-plugin-svelte` — Svelte 5 runes-aware, TypeScript-integrated
- **Vitest** for unit tests — test files use `.spec.ts` or `.test.ts` extension
- CI runs `format:check`, `eslint`, `svelte-check`, and `test` before every deploy
- Run `npm run lint` before pushing if you bypass the pre-commit hook

## Testing

Three test suites — **run all before pushing changes to chat, SSE, Cloud Functions, or agent code**:

- `npm run test` — Vitest: SSE client, chat state machine, plus any `.spec.ts`/`.test.ts` files
- `cd functions && npm test` — Node test runner: Cloud Function utilities and ADK stream parser
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — pytest: source extraction, Places tools, instruction providers
- `npm run test:evals` — live Gemini eval calls for router instructions (not in CI)

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
- **All new/changed UI must support both modes** — use `dark:` variants for `text-black`/`border-black` patterns
- Cream-based classes (`bg-cream`, `border-cream-200`) auto-switch via CSS variables — no `dark:` needed
- Mockup `<style>` blocks use `rgba(var(--mockup-text), X)` and `rgb(var(--mockup-bg))` — not hardcoded colors
- SVGs: `stroke="currentColor"` / `fill="currentColor"` with `text-black dark:text-white` on parent

## Patterns

- Components are self-contained — data defined inline, types inline in `$props()`
- CSS keyframes + `animation-delay` for staggered animations (not Svelte transitions)
- Visibility classes (`max-lg:hidden`/`lg:hidden`) — never duplicate blocks for mobile/desktop
- `formState` singleton (`form-state.svelte.ts`) controls access form modal
- `theme` singleton (`theme.svelte.ts`) manages dark mode — follows `formState` pattern
- `/api/intake` → Cloud Function → Resend email; dev proxy in vite.config.ts

## Agent system

- Pipeline: Router → Context Enricher → Research Orchestrator → Specialists (via AgentTool) → Synthesizer
- Agent code lives in `agent/superextra_agent/`, instructions in `agent/superextra_agent/instructions/`
- **Read `instructions/AUTHORING.md` before writing or modifying any agent instruction file**

## Deployment

Push to `main` → `.github/workflows/deploy.yml` runs 4 parallel jobs:

1. **detect-changes** — `dorny/paths-filter` checks if agent code changed
2. **test** — lint, format check, svelte-check, Vitest, functions tests, agent tests
3. **deploy-hosting** — Firebase Hosting + Cloud Functions (always runs after tests pass)
4. **deploy-agent** — ADK Cloud Run deploy + smoke test (skipped if agent code unchanged)

For deployment gotchas (ADK, SSE streaming, debugging): @docs/deployment-gotchas.md

## Assume nothing — verify

- Never rely on training knowledge for factual claims — check the real source: docs, code, APIs, actual data.
- If you can look it up, look it up. If you can't, say you don't know.
- **External APIs and services:** Read the official documentation first — before writing any code.

## Chrome DevTools MCP

- **Always use Chrome DevTools MCP** for browser tasks — never Playwright (removed)
- Configured with `--isolated` (temp profile per session). Dev server runs on **port 5199**.
- **"browser is already running"**: `pkill -f "chrome.*chrome-devtools-mcp"` then `rm ~/.cache/chrome-devtools-mcp/chrome-profile/SingletonLock`
- **CDP connection drops**: close Chrome DevTools (F12) — it kicks remote CDP clients

## Don'ts

- No Svelte 4 syntax (`export let`, `$:`, `on:click`, `<slot>`)
- No Tailwind v3 config (`tailwind.config.js`, `@apply` in components)
- No duplicating mobile/desktop blocks — use visibility classes
- No killing processes on other ports — ask if 5199 is occupied
- No running `npm run dev` or killing vite processes — use `systemctl --user restart superextra-dev.service`
