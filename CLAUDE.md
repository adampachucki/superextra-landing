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
- `npm run test` — run Vitest unit tests (Firestore stream client, chat state)
- `cd functions && npm test` — run Cloud Function tests (agentStream, gearHandoff, watchdog, utils)
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — run agent Python tests
- `npm run test:rules` — Firestore rules emulator tests (needs Java + Firestore emulator)
- Deploy: push to `main` → GitHub Actions → Firebase (project: superextra-site)

## Code Quality

- **Prettier** formats on save (Cursor) and pre-commit (husky + lint-staged)
- **ESLint** with `eslint-plugin-svelte` — Svelte 5 runes-aware, TypeScript-integrated
- **Vitest** for unit tests — test files use `.spec.ts` or `.test.ts` extension
- CI runs `format:check`, `eslint`, `svelte-check`, and `test` before every deploy
- Run `npm run lint` before pushing when bypassing the pre-commit hook

## Testing

Four test suites — **run all before pushing changes to chat transport, Cloud Functions, worker, or agent code**:

- `npm run test` — Vitest: Firestore stream client, chat state machine, chat-recovery, plus any `.spec.ts`/`.test.ts` files
- `cd functions && npm test` — Node test runner: agentStream, gearHandoff, watchdog, utils
- `npm run test:rules` — Firestore rules emulator (sessions + events collection-group reads/writes)
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — pytest: worker, Firestore-event mapper, source extraction, Places tools, instruction providers
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
- **ADK reference:** when writing or debugging ADK code, consult the official live docs — don't rely on training knowledge:
  - Docs index: `https://adk.dev/llms.txt` (top-level TOC; follow links into specific pages)
  - Canonical patterns: `https://github.com/google/adk-samples` (sample agents, actively maintained)
  - Python source: `https://github.com/google/adk-python` (for API signatures and recent changes)

## Transport architecture

Browser POSTs to `agentStream` (Cloud Function) → `agentStream` hands off directly to a deployed Vertex AI Agent Engine Reasoning Engine (`GEAR_REASONING_ENGINE_RESOURCE`) via `gearHandoff()`. The agent runs inside Agent Engine; `FirestoreProgressPlugin` (in `agent/superextra_agent/firestore_progress.py`) writes progress + terminal state to Firestore from inside the engine. Runs survive client disconnect for ≥240s.

Browser reads state via two `onSnapshot` observers (`sessions/{sid}` for terminal; `collectionGroup('events')` for progress).

Watchdog (`watchdog.js`, scheduled every 2 min) flips stuck sessions to `status=error` inside a fenced transaction.

Plans: `docs/gear-migration-implementation-plan-2026-04-26.md`, `docs/gear-phase9-decommission-plan-2026-04-27.md`.

## Deployment

Push to `main` → `.github/workflows/deploy.yml`:

1. **test** — lint, format check, svelte-check, Vitest, functions tests, rules emulator, agent tests
2. **deploy-hosting** — Firebase Hosting + Cloud Functions + Firestore rules/indexes.

The agent app itself is hosted as a Vertex AI Agent Engine Reasoning Engine; redeploy via `agent_engines.update(...)` from the agent venv when the agent code changes.

For deployment gotchas (Firebase env-var replace behavior, Firestore indexes, watchdog, rerun policy, Chrome MCP E2E flow): read `docs/deployment-gotchas.md` when working on those areas.

## Assume nothing — verify

- Never rely on training knowledge for factual claims — check the real source: docs, code, APIs, actual data.
- When something can be looked up, look it up. Otherwise, say "I don't know."
- **External APIs and services:** Read the official documentation first — before writing any code.

## Simplicity and root causes

- Build the simplest thing that solves the problem. Every line is a regression surface — fewer lines, fewer ways to break.
- Solutions must be **complete** for the real cases, but skip rare edge cases when handling them adds meaningful complexity. The extra code costs more than the edge case saves.
- When something breaks — bug, regression, poor experience — find the **root cause**, even several layers down. Don't patch symptoms; symptom-fixes accrete and create more bugs than they solve.
- Deleting code, functions, or whole features is a legitimate fix. If the root cause is that the feature shouldn't exist in its current form, remove it rather than propping it up.
- When a fix requires surrounding complexity to "make it work safely," that's a signal the approach is wrong — step back and reconsider the root.

## Honesty and pushback

- Don't change position simply because the user pushes back or expresses frustration. New arguments and evidence should change the assessment. Displeasure alone should not.
- When approach A was recommended and the user suggests B, evaluate B on its merits. If A is still better, say so and explain why. If B is actually better, switch and explain what changed the assessment.
- Point out errors and unchecked assumptions in the user's reasoning, even when stated confidently.
- When unsure, say so. Don't guess confidently.
- No filler preambles ("Sure!", "Of course!", "Great question!") or hollow closings ("Let me know if you need anything!").

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
