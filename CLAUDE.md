# Superextra Landing Page

AI-native market intelligence and competitor benchmarking for the restaurant industry. Four layers: data sources → platform → AI agents → human experts. Prerendered static SvelteKit site deployed to Firebase Hosting.

## Domains & hosting sites

- **This repo** (`superextra-landing` hosting site) → **`landing.superextra.ai`** — NOT `superextra.ai`
- `superextra-site` is a separate hosting site serving `superextra.ai` (main marketing page) — not part of this repo
- Agent UI routes: `/agent` (landing.superextra.ai/agent) and `/agent/chat`

## Commands

- `npm run dev` — port 5199, exposed on local network (`host: true`) for mobile testing
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

- `npm run test` — Vitest: SSE client (`src/lib/sse-client.spec.ts`), chat state machine (`src/lib/chat-state.spec.ts`), plus any `.spec.ts`/`.test.ts` files
- `cd functions && npm test` — Node test runner: Cloud Function utilities and ADK stream parser (`functions/utils.test.js`)
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — pytest: source extraction callback, Places tools, instruction providers

CI runs all three suites automatically. After ADK deploy, a smoke test hits `/health` on the Cloud Run service to verify the container started.

When modifying:

- **`functions/index.js` or `functions/utils.js`** → run `cd functions && npm test`
- **`src/lib/sse-client.ts`** → run `npx vitest run src/lib/sse-client.spec.ts`
- **`src/lib/chat-state.svelte.ts`** → run `npx vitest run src/lib/chat-state.spec.ts`
- **`agent/superextra_agent/specialists.py`** → run agent pytest (covers `_append_sources`)
- **`agent/superextra_agent/places_tools.py`** → run agent pytest
- **`agent/superextra_agent/agent.py`** (instruction providers) → run agent pytest
- **`agent/superextra_agent/instructions/router.md`** → run `npm run test:evals` (live Gemini calls, not in CI)

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

## Agent system

- Pipeline: Router → Context Enricher → Research Orchestrator → Specialists (via AgentTool) → Synthesizer
- Agent code lives in `agent/superextra_agent/`, instructions in `agent/superextra_agent/instructions/`
- **Read `instructions/AUTHORING.md` before writing or modifying any agent instruction file** — it documents the architecture, patterns, and pitfalls

## Deployment

Push to `main` → `.github/workflows/deploy.yml` runs 4 parallel jobs:

1. **detect-changes** — `dorny/paths-filter` checks if `agent/superextra_agent/**`, `agent/requirements.txt`, or `deploy.yml` changed
2. **test** — lint, format check, svelte-check, Vitest, functions tests, agent tests (only if agent changed)
3. **deploy-hosting** — Firebase Hosting + Cloud Functions (always runs after tests pass)
4. **deploy-agent** — ADK Cloud Run deploy + smoke test (skipped if agent code unchanged)

`deploy-hosting` and `deploy-agent` run in parallel after `test` passes. Agent deploy is the slowest step (~4-5 min) and is skipped on frontend-only pushes. Agent deps are pinned in `agent/requirements.txt` and cached via `actions/setup-python` pip cache.

The `agentStream` SSE endpoint is called directly via its Cloud Run URL (not `cloudfunctions.net`) — see "Cloud Functions streaming gotchas" below.

### ADK Cloud Run gotchas

- **`adk deploy cloud_run` returns exit 0 even when gcloud fails.** The `deploy-agent` job in `deploy.yml` snapshots the revision before/after and fails if no new revision was created. If the ADK deploy "succeeds" but changes don't appear, check the deploy step output — it may have silently failed. **Always verify** after agent changes: `gcloud run revisions list --service=superextra-agent --region=us-central1 --project=superextra-site --limit=3` — check the latest revision timestamp matches your deploy.
- **Auto-generated Dockerfile** bakes `GOOGLE_CLOUD_LOCATION=us-central1` into the image from `--region`. Do not override this env var — Agent Engine sessions require `us-central1`.
- **Model routing is separate from session routing.** Some models (Gemini 3.1) only work via the global Vertex AI endpoint. `specialists.py` handles this by overriding `api_client` with `location='global'` on Gemini instances. If adding new models, check regional availability first.
- **`agent/.env` is NOT read at runtime in the container.** The file gets copied into the image but ADK's server ignores it. Any env var the agent code needs (e.g. `GOOGLE_PLACES_API_KEY`) must be set as a Cloud Run service-level env var. The deploy pipeline passes these via `--update-env-vars` in the gcloud passthrough after `--` in `deploy.yml`. **When adding a new env var:** add it as a GitHub secret, then append it to the `--update-env-vars` flag in `deploy.yml`. Use `--update-env-vars` (merges) not `--set-env-vars` (replaces all). Service-level env vars persist across deploys.
- **Filesystem is read-only** except `/tmp`. Detect Cloud Run via `K_SERVICE` env var.
- **AgentTool discards sub-agent grounding metadata.** Specialist agents called via `AgentTool` produce `grounding_metadata.grounding_chunks` with source URLs, but AgentTool only propagates text output back to the parent. The `_append_sources` callback in `specialists.py` works around this by appending a `## Sources` markdown section to the specialist's response text before AgentTool captures it.
- **ADK callbacks use keyword arguments.** Agent-level callbacks like `after_model_callback` receive `(*, callback_context, llm_response)` — not positional args. Wrong signatures cause silent TypeErrors.
- **Local deploy**: `cd agent && .venv/bin/adk deploy cloud_run --project=superextra-site --region=us-central1 --service_name=superextra-agent --session_service_uri=agentengine://2746721333428617216 --trace_to_cloud superextra_agent -- --no-allow-unauthenticated`

### Cloud Functions streaming gotchas

- **`cloudfunctions.net` GFE proxy kills SSE streams.** The Google Frontend proxy for Cloud Functions v2 terminates SSE/streaming responses after the first `res.write()`. The `agentStream` function bypasses this by having the frontend call the Cloud Run `run.app` URL directly (`agentstream-907466498524.us-central1.run.app`), not the `cloudfunctions.net` URL. Non-streaming endpoints (`agentCheck`, `agent`) can stay on `cloudfunctions.net`.
- **Use `res.on('close')`, never `req.on('close')` for SSE disconnect detection.** On Cloud Run with HTTP/2, `req.on('close')` fires when the request body stream ends — immediately for a POST request — not when the client disconnects. Using `req.on('close')` will abort the SSE stream at +0.0s. The `res.on('close')` event correctly fires only when the response connection is actually closed by the client.
- **The `agentStream` Cloud Run service must allow unauthenticated access** (`allUsers` with `roles/run.invoker`) since the frontend calls it directly without a Firebase auth layer.

### Debugging agent issues

- **Always read Cloud Run logs first**: `gcloud run services logs read superextra-agent --region=us-central1 --project=superextra-site --limit=30`
- **Check env vars**: `gcloud run services describe superextra-agent --region=us-central1 --project=superextra-site --format="yaml(spec.template.spec.containers[0].env)"`
- **Test end-to-end via Cloud Function**: `curl -X POST https://us-central1-superextra-site.cloudfunctions.net/agent -H 'Content-Type: application/json' -d '{"message":"hello","sessionId":"test"}'`
- **IAM**: Cloud Function SA `907466498524-compute@developer.gserviceaccount.com` needs `roles/run.invoker` on the Cloud Run service

## Assume nothing — verify

- Never rely on training knowledge for factual claims. Every time you explore a topic, hit a coding issue, or reason through a decision — stop and check the real source: docs, code, APIs, actual data.
- If you can look it up, look it up. If you can't, say you don't know. Never fill a gap with a plausible guess.
- This applies to everything: library APIs, platform behavior, syntax, error causes, configuration options. Read the source before you answer.
- **External APIs and services:** When integrating any external tool, SDK, or API (ElevenLabs, Firebase, Google, etc.), read the official documentation first — before writing any code. Understand the exact message formats, data flow, and expected behavior. Do not guess how an API works based on naming conventions or assumptions.

## Don'ts

- No Svelte 4 syntax (`export let`, `$:`, `on:click`, `<slot>`)
- No Tailwind v3 config (`tailwind.config.js`, `@apply` in components)
- No duplicating mobile/desktop blocks — use visibility classes
- No killing processes on other ports — ask if 5199 is occupied
