# Superextra Landing Page

AI-native market intelligence and competitor benchmarking for the restaurant industry. Four layers: data sources → platform → AI agents → human experts. Prerendered static SvelteKit site deployed to Firebase Hosting.

## Commands

- `npm run dev` — port 5199, exposed on local network (`host: true`) for mobile testing
- `npm run build` / `npm run check`
- `npm run lint` — Prettier check + ESLint
- `npm run format` — auto-format all files
- `npm run test` — run unit tests once
- Deploy: push to `main` → GitHub Actions → Firebase (project: superextra-site)

## Code Quality

- **Prettier** formats on save (Cursor) and pre-commit (husky + lint-staged)
- **ESLint** with `eslint-plugin-svelte` — Svelte 5 runes-aware, TypeScript-integrated
- **Vitest** for unit tests — test files use `.spec.ts` or `.test.ts` extension
- CI runs `format:check`, `eslint`, `svelte-check`, and `test` before every deploy
- Run `npm run lint` before pushing if you bypass the pre-commit hook

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

- Pipeline: Router → Context Enricher → Research Planner → Specialists (via AgentTool) → Synthesizer
- Agent code lives in `agent/superextra_agent/`, instructions in `agent/superextra_agent/instructions/`
- **Read `instructions/AUTHORING.md` before writing or modifying any agent instruction file** — it documents the architecture, patterns, and pitfalls

## Deployment

Push to `main` → `.github/workflows/deploy.yml` deploys: Firebase Hosting (static SvelteKit), Cloud Functions (`functions/index.js` — proxies to agent), ADK agent on Cloud Run (`superextra-agent` in `us-central1`).

### ADK Cloud Run gotchas

- **Auto-generated Dockerfile** bakes `GOOGLE_CLOUD_LOCATION=us-central1` into the image from `--region`. Do not override this env var — Agent Engine sessions require `us-central1`.
- **Model routing is separate from session routing.** Some models (Gemini 3.1) only work via the global Vertex AI endpoint. `specialists.py` handles this by overriding `api_client` with `location='global'` on Gemini instances. If adding new models, check regional availability first.
- **`agent/.env` is NOT copied into the container.** It works locally but ADK in the container can't find it. Use `--set-env-vars` for Cloud Run, and note that **service-level env vars persist across deploys** — use `--remove-env-vars` to clean up.
- **Filesystem is read-only** except `/tmp`. Detect Cloud Run via `K_SERVICE` env var.
- **Local deploy**: `cd agent && .venv/bin/adk deploy cloud_run --project=superextra-site --region=us-central1 --service_name=superextra-agent --session_service_uri=agentengine://2746721333428617216 --trace_to_cloud superextra_agent -- --no-allow-unauthenticated`

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
