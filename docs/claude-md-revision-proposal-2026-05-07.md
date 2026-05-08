# CLAUDE.md revision proposal — 2026-05-07 (v2)

**Status:** Proposal v2, not applied. Incorporates all corrections from Codex review.
**Author:** drafted by Claude, reviewed by Codex
**Trigger:** Adam flagged five issues with the current `CLAUDE.md` — outdated project description, stale branding bullets, weak adherence to lean/root-cause principles, missing reminder to consult external docs, and missing reminder to brief review agents with the same priorities.

**Changes from v1:** one-liner now uses visible hero copy ("AI consultant"); engineering-principles wording sharpened; verify section expanded to real external deps (ElevenLabs, Apify, SerpAPI, Maps Autocomplete, Cloud Scheduler, Secret Manager, Vertex Gemini); review-agent brief tightened; restored "When unsure, say so"; dev-server prohibition promoted near top; stale architecture facts (pipeline, transport, testing) corrected to match live code; length math corrected.

---

## 1. Concerns with the current CLAUDE.md

### 1.1 Project one-liner is stale

Current opening:

> AI-native market intelligence and competitor benchmarking for the restaurant industry. Four layers: data sources → platform → AI agents → human experts. Prerendered static SvelteKit site deployed to Firebase Hosting.

This describes the **old** product framing. The visible hero on the agent landing page (`src/lib/components/restaurants/RestaurantHero.svelte:208`) now says **"AI consultant for every restaurant."** The "four layers" framing has been removed from the live site.

(v1 of this proposal incorrectly used "Market analyst" — that phrase exists only in OG metadata at `src/routes/agent/+page.svelte:80`, not as visible page copy. Corrected.)

### 1.2 Branding section contains five obsolete bullets

The current Branding section carries five bullets that no longer reflect how copy is written:

- "Four layers" framing
- "Platform" positioning warning
- "Use 'service', 'delivered', 'combined'" word list
- '"Get Started" not "Get Access"' CTA rule
- Reference to `docs/copy.md`, `docs/notes.md`, `docs/scope.md`

Two factual problems: (a) the framing has shifted away from these concerns; (b) `docs/copy.md`, `docs/notes.md`, and `docs/scope.md` **do not exist** in this repo — that bullet has been pointing at nothing. Verified with `ls`.

### 1.3 "Simplicity and root causes" is not being followed

The current section lives at line 145 — eleven sections deep. Its phrasing ("build the simplest thing", "find the root cause") is generic enough that Claude reads it without changing behavior. Adam reports manually re-stating these rules every session, in stronger language:

> we want lean and clean code, ideally reduce net loc, aim to identify root causes for issues and remove them rather than treating symptoms, and that we don't want overly defensive hardening, and that we don't care about rare edge cases, and that we prefer stable and reliable core rather than solving all possible issues while expanding surface area for potential new issues

The official docs say: _"Make instructions more specific. 'Use 2-space indentation' works better than 'format code nicely.'"_ (Claude Code memory docs.) The fix here is the same — replace soft phrasing with concrete, named anti-patterns and behavioral gates.

### 1.4 External-docs verification rule is buried and partial

The current "Assume nothing — verify" section names docs only for ADK, and only inside the Agent System subsection. Adam wants this expanded and prominent: ADK, **Vertex AI Agent Engine**, **Google Cloud services**, **Firebase** — because Claude routinely proposes building things that already exist out of the box in those platforms. Codex review surfaced additional live external deps: ElevenLabs STT/TTS, Apify, SerpAPI, Secret Manager, Maps JavaScript Autocomplete (separate from the Places Web Service), and Cloud Scheduler.

### 1.5 No rule about briefing review agents

There is no instruction to pass the lean/root-cause/verification brief through to subagents when delegating reviews. Without it, review agents default to over-cautious "add more error handling, add more tests" feedback that contradicts how this codebase is built.

### 1.6 Stale architecture facts in current CLAUDE.md (surfaced by Codex)

While we're touching the file, Codex review found three statements in the current CLAUDE.md that are factually wrong relative to live code. Fixing them in the same revision:

- **Agent pipeline** says "Router → Context Enricher → Research Orchestrator → Specialists (via AgentTool) → Synthesizer." Actual structure (`agent/superextra_agent/agent.py:145-167`): Router → `research_pipeline` (a `SequentialAgent` of Context Enricher + `research_lead`); the `research_lead` calls specialists as tools and writes `final_report`. There is no separate Synthesizer agent.
- **Transport** says "Browser reads state via two `onSnapshot` observers (`sessions/{sid}` for terminal; the per-session subcollection `sessions/{sid}/events` for progress)." Actual (`src/lib/chat-state.svelte.ts:4-16`): four live Firestore listeners — sidebar (`sessions where participants array-contains uid`), active session (`sessions/{sid}`), turns (`sessions/{sid}/turns order by turnIndex`), and events (`sessions/{sid}/events where runId == currentRunId`). Terminal content lives in `turns`, not the session doc alone.
- **Testing** description references "worker" in the agent test list. The worker source has been removed.

---

## 2. Best-practice anchors driving the design

Pulled from the official Claude Code memory docs and Anthropic-aligned community guidance:

| Principle                                                                                | Source                                                                                                                         | How it shapes this proposal                                                                      |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| Keep CLAUDE.md concise; specific instructions are followed more reliably than vague ones | [Claude Code memory docs](https://code.claude.com/docs/en/memory)                                                              | Replace "build the simplest thing" with named anti-patterns and behavioral gates                 |
| Use markdown headers and bullets — Claude scans structure like readers                   | Memory docs                                                                                                                    | Engineering principles broken into three named subsections                                       |
| Eliminate contradictions and duplications                                                | Memory docs                                                                                                                    | Merge "Assume nothing", "Simplicity and root causes", and the ADK-docs sub-bullet into one block |
| Promote high-priority rules to the top                                                   | [HumanLayer: Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)                               | Engineering principles move from §11 to §2; dev-server prohibition moved up too                  |
| Delete instructions Claude already follows correctly                                     | HumanLayer + [How Anthropic teams use Claude Code](https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf) | Trim Branding                                                                                    |

Note: the "first 200 lines or 25 KB" load cap in the official docs applies to **auto memory's `MEMORY.md`**, not to project `CLAUDE.md` files (which load in full). For `CLAUDE.md`, official guidance sets a **soft target under 200 lines** and emphasises that shorter, specific instructions are followed more reliably.

---

## 3. Net changes

| Change            | Section                                                                                                       | Reason                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Rewrite**       | Project one-liner                                                                                             | Use visible hero copy "AI consultant for every restaurant" (concern 1.1)                     |
| **Add**           | Engineering principles (new §2) with sharpened, gate-style wording                                            | Make lean/root-cause/no-defensive-hardening behaviorally specific (concern 1.3)              |
| **Add**           | "Verify, never assume" subsection — full external-docs list                                                   | Cover all live external deps (concern 1.4)                                                   |
| **Add**           | "When delegating to a review agent" subsection with verbatim brief                                            | Force consistent reviewer framing (concern 1.5)                                              |
| **Fix**           | Agent pipeline description                                                                                    | Match live `agent.py:145-167` (concern 1.6)                                                  |
| **Fix**           | Transport description                                                                                         | Match live `chat-state.svelte.ts:4-16` — four listeners, terminal from `turns` (concern 1.6) |
| **Fix**           | Testing description                                                                                           | Drop "worker" reference (concern 1.6)                                                        |
| **Remove**        | 5 stale Branding bullets                                                                                      | Concern 1.2                                                                                  |
| **Remove**        | "Assume nothing — verify" standalone section                                                                  | Folded into new Engineering principles                                                       |
| **Remove**        | "Simplicity and root causes" standalone section                                                               | Folded into new Engineering principles                                                       |
| **Remove**        | ADK reference sub-bullet under Agent system                                                                   | Folded into new Engineering principles                                                       |
| **Remove**        | Duplicate dev-server "don'ts" (kept once, promoted higher)                                                    | De-duplication + prominence                                                                  |
| **Reorder**       | Engineering principles + dev-server warning + Branding + Honesty to the top; hosting/deploy/MCP at the bottom | Hot rules first, cold reference last                                                         |
| **Keep verbatim** | Stack, Svelte 5, Tailwind v4, Dark mode, Patterns, Code Quality, Commands, Deployment, Chrome DevTools MCP    | These are working as intended                                                                |
| **Restore**       | "When unsure, say so. Don't guess confidently."                                                               | v1 incorrectly removed it                                                                    |

---

## 4. Proposed final ordering

1. Project one-liner
2. Engineering principles **(new, prominent)**
3. Dev server (port 5199) — **promoted from §3 to §3, with the operational prohibition surfaced**
4. Branding (trimmed)
5. Honesty and pushback (kept)
6. Stack
7. Svelte 5 — no legacy syntax
8. Tailwind v4
9. Dark mode
10. Patterns
11. Agent system (corrected pipeline; ADK refs moved up to §2)
12. Transport architecture (corrected: four listeners, terminal from `turns`)
13. Domains & hosting sites
14. Commands
15. Code Quality
16. Testing (corrected; no `worker`)
17. Deployment
18. Chrome DevTools MCP
19. Don'ts

**Rationale:** sections 2–5 apply to _every_ change Claude makes, so they go first. The dev-server warning is operational, not cold reference, so it joins them rather than living among hosting/deploy material. Sections 6–12 are consulted only when editing matching code. Sections 13–19 are infrastructure/operational reference.

---

## 5. Full proposed CLAUDE.md (ready to drop in)

The block below is the complete replacement for `/home/adam/src/superextra-landing/CLAUDE.md`.

````markdown
# Superextra Landing Page

Superextra is an AI consultant for every restaurant — a market-intelligence agent that synthesizes competitor, pricing, guest, delivery, and market signals into operator-ready answers about where to open, how to price, when to hire, and what's shifting around them.

This repo is a prerendered static SvelteKit site (landing + agent UI) on Firebase Hosting. The agent itself runs as a Vertex AI Agent Engine Reasoning Engine.

## Engineering principles — apply to every change

These rules get violated most often. Re-read before proposing or editing code.

### Lean, clean, root-cause

- **Prefer the smallest diff that fixes the root cause.** Justify any net LOC increase. A change that removes more than it adds is usually the better change. Deleting a function, a feature, or a whole file is a legitimate fix.
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
  - **Cloud Scheduler** (drives `watchdog.js`) and **Secret Manager** (agent secrets)
  - **Google Maps JavaScript API** for Autocomplete (separate surface from the Places Web Service)
  - **Google Places Web Service** (server-side place lookups)
  - **ElevenLabs** (STT for dictation; TTS for voice playback)
  - **Apify** and **SerpAPI** (agent research tools)
  - **Resend** (intake email)
- **Never rely on training knowledge for factual claims** — versions, API signatures, behavior, defaults. Look it up or say "I don't know."
- **Verify before recommending.** Before suggesting a function, flag, or pattern, grep the codebase or fetch the SDK source to confirm it exists in the version we're on.

### When delegating to a review agent — ALWAYS pass these requirements

Every review-agent prompt MUST include this brief:

> Review with these priorities: find root causes, prefer the smallest reliable core, reduce net LOC, delete dead paths, and reject speculative guards, retries, fallbacks, abstractions, or rare-edge handling that expands surface area. Verify against the codebase and official docs for any touched external system. State only facts; mark uncertainty.

This applies whether the delegated agent is a code reviewer, plan reviewer, security reviewer, or general-purpose investigator. Without this brief, reviewers default to over-cautious "add more error handling, add more tests" feedback that contradicts how this codebase is built.

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

Browser state is driven by **four live Firestore listeners** (`src/lib/chat-state.svelte.ts:4-16`):

1. **Sidebar** — `sessions where participants array-contains uid order by updatedAt desc`
2. **Active session** — `sessions/{sid}` (drives `loadState`, `canDelete`)
3. **Active turns** — `sessions/{sid}/turns order by turnIndex` — source of truth for the message list and current turn status
4. **Active events** — `sessions/{sid}/events where runId == latestTurn.runId` — attached for the in-flight turn, and briefly for completed turns with `turnSummary` to hydrate completed activity

Watchdog (`watchdog.js`, scheduled by Cloud Scheduler every 2 min) flips stuck sessions to `status=error` inside a fenced transaction.

Plans: `docs/gear-migration-implementation-plan-2026-04-26.md`, `docs/gear-phase9-decommission-plan-2026-04-27.md`.

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
- `npm run test:evals` — live Gemini eval calls for router instructions (not in CI)

## Deployment

Push to `main` → `.github/workflows/deploy.yml`:

1. **test** — lint, format check, svelte-check, Vitest, functions tests, rules emulator, agent tests
2. **deploy-hosting** — Firebase Hosting + Cloud Functions + Firestore rules/indexes.

The agent app itself is hosted as a Vertex AI Agent Engine Reasoning Engine; redeploy via `agent_engines.update(...)` from the agent venv when the agent code changes.

For deployment gotchas (Firebase env-var replace behavior, Firestore indexes, watchdog, rerun policy, Chrome MCP E2E flow): read `docs/deployment-gotchas.md` when working on those areas — but verify every operational claim against source first. That doc is known stale for `DEFAULT_RESOURCE`, watchdog reason names, and Firestore index inventory.

## Chrome DevTools MCP

- **Always use Chrome DevTools MCP** for browser tasks — never Playwright (removed)
- Configured with `--isolated` (temp profile per session). Dev server runs on **port 5199**.
- **Two providers exist**: `mcp__chrome-devtools__*` (headful, fails with "Missing X server" on remote VMs) and `mcp__chrome-devtools-mcp__*` (headless, works everywhere). On the GCP VM use the `-mcp` suffix one — it's already running with `--headless --isolated --no-sandbox`. Both can drive `agent.superextra.ai` end-to-end.
- **"browser is already running"**: `pkill -f "chrome.*chrome-devtools-mcp"` then `rm ~/.cache/chrome-devtools-mcp/chrome-profile/SingletonLock`
- **CDP connection drops**: close Chrome DevTools (F12) — it kicks remote CDP clients

## Don'ts

- No Svelte 4 syntax (`export let`, `$:`, `on:click`, `<slot>`)
- No Tailwind v3 config (`tailwind.config.js`, `@apply` in components)
- No duplicating mobile/desktop blocks — use visibility classes
- No killing processes on other ports — ask if 5199 is occupied
````

---

## 6. Length check

|                           | Lines                                                  |
| ------------------------- | ------------------------------------------------------ |
| Current `CLAUDE.md`       | 175                                                    |
| Proposed `CLAUDE.md` (v2) | ~197                                                   |
| Best-practice target      | shorter is better; specificity matters more than count |

Slightly longer than current because the Engineering principles section is more concrete and the external-deps list is complete. The v1 claim of "~165 lines" was wrong.

---

## 7. Open questions for Adam

- **Sign-off to apply** v2 to `CLAUDE.md`?
- The `docs/deployment-gotchas.md` file has known stale content (`DEFAULT_RESOURCE`, watchdog reason names) per Codex review. Worth a separate cleanup pass — out of scope for this proposal but worth flagging.

---

## 8. Possible follow-ups (out of scope here)

- The "always pass this brief to review agents" rule is behavioral, not enforced. If review-agent briefs still get forgotten, the next-best mechanism is a custom slash command (e.g. `/review-strict`) that injects the brief automatically.
- No CLAUDE.md change can guarantee adherence — Claude Code treats CLAUDE.md as context, not enforced configuration. For truly deterministic enforcement, use hooks.
- `docs/deployment-gotchas.md` cleanup (separate ticket).

---

## Sources

- [Claude Code memory docs — official guidance on CLAUDE.md](https://code.claude.com/docs/en/memory)
- [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)
- [Writing a good CLAUDE.md — HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [How Anthropic teams use Claude Code (PDF)](https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf)
