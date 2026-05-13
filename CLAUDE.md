# Superextra Landing Page

Superextra is an AI consultant for every restaurant — a market-intelligence agent that synthesizes competitor, pricing, guest, delivery, and market signals into operator-ready answers about where to open, how to price, when to hire, and what's shifting around them.

This repo is a prerendered static SvelteKit site (landing + agent UI) on Firebase Hosting. The agent itself runs as a Vertex AI Agent Engine Reasoning Engine.

## Engineering principles — apply to every change

These rules get violated most often. Re-read before proposing or editing code.

### Lean, clean, root-cause

- **Optimize for the end state of the codebase, not the size of the diff.** A thorough structural fix that grows this commit but leaves the codebase smaller and cleaner is better than a small patch that wraps existing cruft in a guard. Deleting a function, a feature, or a whole file is a legitimate fix; so is rewriting a flawed module instead of patching around it.
- **Find the root cause and remove it.** Don't patch symptoms. If a bug needs three guards to "make it work safely," the approach is wrong — step back and reconsider.
- **Do not add guards, retries, fallbacks, abstractions, or config knobs unless tied to an observed failure, a documented external contract, or a core security/data-integrity invariant.** Trust internal invariants and framework guarantees.
- **Don't solve rare edge cases.** A reliable core beats a fragile everything-handler. If handling a corner case meaningfully expands surface area, skip it.
- **No abstractions for hypothetical futures.** Three similar lines beats a premature abstraction. Add the abstraction when the third real caller appears.
- **No half-finished work.** Either complete it or remove it. No `// TODO`, no commented-out blocks, no orphaned helpers.
- **When replacing an architecture, delete obsolete paths, docs, tests, and comments in the same change.** Stale references rot fastest.

### Verify, never assume

- **Read the official docs before writing code against any external system.** Many things you'd "build" are already provided out of the box. Check first, code second.
- Live external dependencies in this repo (consult docs when touched):
  - **ADK**: docs index `https://adk.dev/llms.txt`; samples `https://github.com/google/adk-samples`; Python source `https://github.com/google/adk-python`
  - **Vertex AI Agent Engine** (Reasoning Engine: `streamQuery`, `appendEvent`, session management) and **Vertex AI Gemini** models — official Google Cloud docs
  - **Firebase**: Hosting, Cloud Functions (Node 22), Firestore, Authentication
  - **Cloud Scheduler** (drives `watchdog.js`); **Secret Manager** + Firebase Functions secrets (agent and function secrets)
  - **Google Cloud Storage** (used by `agent/scripts/redeploy_engine.py`)
  - **Google Auth Library / ADC / IAM** (`functions/gear-handoff.js` for service-to-service auth)
  - **Google Maps JavaScript API** for Autocomplete (separate surface from the Places Web Service)
  - **Google Places Web Service** (server-side place lookups)
  - **ElevenLabs** (STT for dictation; TTS for voice playback)
  - **Apify** and **SerpAPI** (agent research tools)
  - **Resend** (intake email)
- **Never rely on training knowledge for factual claims** — versions, API signatures, behavior, defaults. Look it up or say "I don't know."
- **Verify before recommending.** Before suggesting a function, flag, or pattern, grep the codebase or fetch the SDK source to confirm it exists in the version we're on.
- **Verify UI changes in a browser.** Type checks and unit tests don't prove rendering. Use Chrome DevTools MCP.
- **`firebase deploy` REPLACES function env vars** — every var the function needs at runtime must be in `functions/.env.superextra-site` at deploy time, or the next deploy quietly removes it.
- **From the VM, ADC needs `quota_project_id=superextra-site`** or Google API calls (Firebase Hosting, Cloud Functions, Cloud Build) fail with `403 PERMISSION_DENIED`.

### When delegating to a review agent — ALWAYS pass these requirements

Every review-agent prompt MUST include this brief:

> Review with these priorities: optimize for the end state of the codebase (not diff size) — favor thorough structural fixes over patches that wrap existing cruft. Find root causes, prefer the smallest reliable core, delete dead paths, and reject speculative guards, retries, fallbacks, abstractions, or rare-edge handling that expands surface area. Verify against the codebase and official docs for any touched external system. State only facts; mark uncertainty.

This applies whether the delegated agent is a code reviewer, plan reviewer, security reviewer, or general-purpose investigator.

### Reviewing with Codex CLI

`codex` is installed on the VM (where Claude Code runs) and is the preferred second opinion for plans, proposals, and non-trivial diffs.

- **First call**: `codex exec "<prompt>"` — one-shot, non-interactive. The session UUID prints in the output and is saved under `~/.codex/sessions/`. Capture it.
- **Re-review / follow-up on the same artifact**: `codex exec resume <uuid> "<follow-up>"` — resumes the recorded session with prior transcript context. Always use the explicit UUID; `--last` can pick up another Claude session's run.
- The bare `codex` command launches a TUI that can't be driven from `Bash` — never use it from tool calls. Always `codex exec`.
- Include the verbatim review brief above in every codex prompt. No exceptions.

## Dev server (port 5199) — never run npm run dev

The Vite dev server is managed by a **systemd user service** that runs continuously and restarts on crash.

- **Service**: `superextra-dev.service` (`~/.config/systemd/user/superextra-dev.service`)
- **Config**: `Restart=always`, `RestartSec=3` — killing the vite process directly just respawns it 3s later
- **Restart**: `systemctl --user restart superextra-dev.service`
- **Status/logs**: `systemctl --user status superextra-dev.service`
- **Never run `npm run dev` manually** — it spawns a duplicate on port 5200/5201, leading to stale HMR and confusion about which server the browser is hitting
- **Never `kill` the vite process directly** — use `systemctl --user restart` instead
- Port 5199, exposed on local network (`host: true`) for mobile testing

## Branding

- Name is **Superextra** — not SuperExtra, Super Extra, or SUPEREXTRA
- Avoid "you/your" — product-focused, Apple-style, minimalistic tone

## Honesty and pushback

- Don't change position simply because the user pushes back or expresses frustration. New arguments and evidence should change the assessment. Displeasure alone should not.
- When approach A was recommended and the user suggests B, evaluate B on its merits. If A is still better, say so and explain why. If B is actually better, switch and explain what changed the assessment.
- Point out errors and unchecked assumptions in the user's reasoning, even when stated confidently.
- When unsure, say so. Don't guess confidently.
- No filler preambles ("Sure!", "Of course!", "Great question!") or hollow closings ("Let me know if you need anything!").

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

- Pipeline: Router → `research_pipeline` (`SequentialAgent` of Context Enricher + `research_lead`). The `research_lead` plans the work, calls specialists as `AgentTool` tools, and writes `final_report`. No separate synthesizer agent.
- Agent code: `agent/superextra_agent/`. Instructions: `agent/superextra_agent/instructions/`
- **Read `instructions/AUTHORING.md` before writing or modifying any agent instruction file**
- ADK / Agent Engine docs: see "Verify, never assume" above

## Transport architecture

Browser POSTs to `agentStream` (Cloud Function) → `agentStream` hands off directly to a deployed Vertex AI Agent Engine Reasoning Engine (`GEAR_REASONING_ENGINE_RESOURCE`) via `gearHandoff()`. The agent runs inside Agent Engine; `FirestoreProgressPlugin` (in `agent/superextra_agent/firestore_progress.py`) writes progress + terminal state to Firestore from inside the engine. Runs survive client disconnect for ≥240s.

Browser state is driven by **four live Firestore listeners** (`src/lib/chat-state.svelte.ts`):

1. **Sidebar** — `sessions where participants array-contains uid order by updatedAt desc`
2. **Active session** — `sessions/{sid}` (drives `loadState`, `canDelete`)
3. **Active turns** — `sessions/{sid}/turns order by turnIndex` — source of truth for the message list and current turn status
4. **Active events** — `sessions/{sid}/events where runId == latestTurn.runId` — attached for the in-flight turn, and briefly for completed turns with `turnSummary` to hydrate completed activity

Watchdog (`watchdog.js`, scheduled by Cloud Scheduler every 2 min) flips stuck sessions to `status=error` inside a fenced transaction.

Historical migration plans are archived outside this repo; current deployment gotchas live in `docs/deployment-gotchas.md`.

## Domains & hosting sites

- **This repo** deploys to two Firebase Hosting sites (both in project `superextra-site`):
  - `superextra-landing` → **`landing.superextra.ai`** (marketing landing page)
  - `superextra-agent` → **`agent.superextra.ai`** (agent UI)
- `superextra-site` is a separate hosting site serving `superextra.ai` (main marketing page) — not part of this repo
- Agent UI routes: `agent.superextra.ai/` (agent landing) and `agent.superextra.ai/chat`
- `landing.superextra.ai/agent` 301-redirects to `agent.superextra.ai`

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

Four test suites — **run all before pushing changes to chat transport, Cloud Functions, or agent code**:

- `npm run test` — Vitest: Firestore stream client, chat state machine, chat-recovery, plus any `.spec.ts`/`.test.ts` files
- `cd functions && npm test` — Node test runner: agentStream, gearHandoff, watchdog, utils
- `npm run test:rules` — Firestore rules emulator (sessions + per-session `turns` and `events` reads/writes)
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — pytest: Firestore-event mapper, source extraction, Places tools, instruction providers

Optional (live, not in CI): `npm run test:evals` — live Gemini eval calls for router instructions.

## Deployment

Push to `main` → `.github/workflows/deploy.yml`:

1. **test** — lint, format check, svelte-check, Vitest, functions tests, rules emulator, agent tests
2. **deploy-hosting** — Firebase Hosting + Cloud Functions + Firestore rules/indexes.

The agent app itself is hosted as a Vertex AI Agent Engine Reasoning Engine; redeploy via `agent_engines.update(...)` from the agent venv when the agent code changes.

Deployment gotchas (agent engine deploy, env-var REPLACE, Firestore shape, watchdog, ADC quota, Chrome MCP E2E): `docs/deployment-gotchas.md`.

## Chrome DevTools MCP

- **Always use Chrome DevTools MCP** for browser tasks — never Playwright (removed)
- Configured with `--isolated` (temp profile per session). Dev server runs on **port 5199**.
- **Two providers exist** in `.mcp.json`: `mcp__chrome-devtools__*` (headful — fails with "Missing X server" on remote VMs) and `mcp__chrome-devtools-mcp__*` (headless). On the GCP VM use the `-mcp` suffix one — it's the permitted provider and is already running with `--headless --isolated --no-sandbox`.
- **"browser is already running"**: `pkill -f "chrome.*chrome-devtools-mcp"` then `rm ~/.cache/chrome-devtools-mcp/chrome-profile/SingletonLock`
- **CDP connection drops**: close Chrome DevTools (F12) — it kicks remote CDP clients

## Don'ts

- No Svelte 4 syntax (`export let`, `$:`, `on:click`, `<slot>`)
- No Tailwind v3 config (`tailwind.config.js`, `@apply` in components)
- No duplicating mobile/desktop blocks — use visibility classes
- No killing processes on other ports — ask if 5199 is occupied
