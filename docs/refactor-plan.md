# Codebase Review & Refactor Plan

Deep review conducted April 2026 across all four layers: SvelteKit frontend, Cloud Functions, Python agent, and project architecture.

## What's already been done

- Deleted `src/lib/vitest-examples/` boilerplate (dead code)
- Removed unused `SPECIALIST_KEYS` and `TOOL_LABELS` imports from Cloud Functions
- Extracted shared canvas helpers (`noise`, `lerp`, `lerpColor`, `smoothstep`, `CANVAS_COLORS`) to `src/lib/canvas-helpers.ts`
- Added `btn-ghost` utility in `app.css`, replacing duplicated 100-char class strings in CTA, PlatformCards, and Navbar
- Deduplicated Navbar chat icon + badge via Svelte 5 snippet and shared `iconBtnClass` derived

---

## Findings

### Critical — Safety & Stability

| #   | Issue                                                | Location                                                         | Impact                                                                                                                                                                                         |
| --- | ---------------------------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Stream not aborted on conversation switch**        | `chat-state.svelte.ts:278-410`                                   | `switchTo()` changes `currentId` but never calls `abortController.abort()`. Old stream continues, callbacks update wrong conversations, bandwidth wasted.                                      |
| 2   | **ADK callback signatures missing `*,`**             | `agent.py:71`, `specialists.py:168,182,202`                      | `_inject_code_execution`, `_inject_geo_bias`, `_make_skip_callback` inner fn, `_on_tool_error` all lack keyword-only arg separator. Works by coincidence today but violates ADK contract.      |
| 3   | **RAF memory leaks in streaming UI**                 | `ChatThread.svelte:50-89`, `StreamingProgress.svelte` (multiple) | `typewriterRaf` cleanup skipped on early return; RAF ID maps (`dataRafs`, `excerptRafs`, `readRafs`) grow unbounded; completed entries never removed.                                          |
| 4   | **Interval leak in handleReturn**                    | `chat-state.svelte.ts:505-511`                                   | Polling interval can leak if timeout fires while `loading` is already false.                                                                                                                   |
| 5   | **No input validation on Cloud Function boundaries** | `functions/index.js`                                             | `placeContext.name` interpolated into agent queries (prompt injection risk), `history` array never validated, intake form fields have no length/type checks, `x-forwarded-for` used as userId. |
| 6   | **`agentDebug` endpoint unauthenticated**            | `functions/index.js:694-735`                                     | Exposes full ADK session state with `cors: true` and zero auth.                                                                                                                                |
| 7   | **Rate limit maps grow unbounded**                   | `functions/index.js:116,522,560`                                 | Three `Map` objects never clean expired entries. Long-running instances leak memory.                                                                                                           |

### Medium — Code Quality & Architecture

| #   | Issue                                                 | Location                                                                         | Impact                                                                                                          |
| --- | ----------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 8   | **AccessForm.svelte is 765 lines**                    | `AccessForm.svelte`                                                              | Form state, Google Places API, validation, animation, 5 steps of UI all in one file. Unmaintainable.            |
| 9   | **Missing `+error.svelte` route**                     | `src/routes/`                                                                    | No custom error boundary. 404s and runtime errors show Firebase defaults.                                       |
| 10  | **ESLint ignores `functions/` entirely**              | `eslint.config.js:46`                                                            | Cloud Functions code gets zero linting.                                                                         |
| 11  | **Vite patch undocumented**                           | `patches/vite+7.3.1.patch`                                                       | Custom Mobile Safari HMR fix exists but isn't documented.                                                       |
| 12  | **Error state cleared before recovery**               | `chat-state.svelte.ts:520-525`                                                   | `handleReturn()` clears error before trying to recover. If recovery also fails, original context is lost.       |
| 13  | **Inconsistent HTTP error codes**                     | `functions/index.js`                                                             | Mixed use of 200+`ok:false`, 400, 500, 502 across endpoints.                                                    |
| 14  | **Missing Firebase security headers**                 | `firebase.json`                                                                  | No `X-Content-Type-Options`, `X-Frame-Options`, or CSP.                                                         |
| 15  | **Agent JSON parsing unprotected**                    | `places_tools.py`, `tripadvisor_tools.py`                                        | `resp.json()` can throw if API returns non-JSON. Caught by broad except but not handled explicitly.             |
| 16  | **HTTP clients never closed**                         | `places_tools.py:57-64`, `tripadvisor_tools.py:6-13`                             | `httpx.AsyncClient` created once, never closed on container shutdown.                                           |
| 17  | **Silent pagination failure**                         | `tripadvisor_tools.py:148-151`                                                   | If a later page fails, returns partial data with `status: "success"`. User doesn't know results are incomplete. |
| 18  | **Google Maps script can be injected multiple times** | `AccessForm.svelte:81-96`                                                        | No check for existing script tag before injecting.                                                              |
| 19  | **`console.log` in production SSE client**            | `sse-client.ts:51`                                                               | Debug logging left in production code.                                                                          |
| 20  | **Heading typography duplicated**                     | `SectionHeader.svelte`, `About.svelte`, `Audiences.svelte`, `DataSources.svelte` | Same `text-[clamp(2rem,4vw,3.25rem)] leading-[1.1]` pattern repeated across 4+ components.                      |

### Low — Nice to Have

| #   | Issue                                       | Location                    | Impact                                                                                                                                                               |
| --- | ------------------------------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 21  | **AccessForm modal missing focus trap**     | `AccessForm.svelte`         | Users can tab to elements behind modal. Accessibility issue.                                                                                                         |
| 22  | **Suggestion dropdown missing ARIA**        | `AccessForm.svelte:484-505` | No `role="listbox"`, `aria-selected`, or `aria-autocomplete`.                                                                                                        |
| 23  | **DataSources images lack lazy loading**    | `DataSources.svelte:65-69`  | 28 logo images loaded eagerly.                                                                                                                                       |
| 24  | **No `robots.txt` or `sitemap.xml`**        | `static/`                   | Missing for SEO.                                                                                                                                                     |
| 25  | **No `.env.example` files**                 | root, `agent/`              | New developers don't know what env vars are needed.                                                                                                                  |
| 26  | **TypeScript `any` rule is warn not error** | `eslint.config.js:25`       | Allows `any` to slip into production.                                                                                                                                |
| 27  | **Test coverage gaps**                      | Multiple                    | Cloud Functions: only utils tested. Agent: no malformed JSON tests. Chat state: `onActivity` not in shared mock. SSE: malformed progress/token events silently fail. |
| 28  | **Missing specialist brief key validation** | `specialists.py:207-223`    | Typos in specialist names silently skip the specialist.                                                                                                              |
| 29  | **Image encoding without size validation**  | `agent.py:106-108`          | No size check before base64-encoding model images.                                                                                                                   |

---

## Three-Sprint Refactor Plan

### Sprint 1 — Safety & Stability ✓

Fix the issues that can cause data loss, race conditions, or security exposure.

**Chat system:**

- [x] Abort stream on conversation switch — call `abortController.abort()` in `switchTo()` when `loading` is true
- [x] Fix RAF cleanup in `ChatThread.svelte` — move cleanup out of early return path
- [x] Fix RAF map leaks in `StreamingProgress.svelte` — clear completed entries from `dataRafs`, `excerptRafs`, `readRafs`
- [x] Fix interval leak in `handleReturn()` — use flag to ensure single cleanup

**Agent callbacks:**

- [x] Add `*,` keyword separator to `_inject_code_execution` in `agent.py:71`
- [x] Add `*,` to `_inject_geo_bias` in `specialists.py:168`
- [x] Add `*,` to `_make_skip_callback` inner fn in `specialists.py:182`
- [x] Fix `_on_tool_error` signature — add `*,`, rename `args` to `tool_args` in `specialists.py:202`

**Cloud Functions security:**

- [x] Add input validation for `message`, `sessionId`, `placeContext`, `history` in agent/agentStream endpoints
- [x] Add auth check to `agentDebug` endpoint (or remove it)
- [x] Add periodic cleanup to rate limit maps (evict expired entries when map exceeds threshold)
- [x] Fix error state recovery — only clear error after successful recover()

### Sprint 2 — Code Quality ✓

Reduce complexity, improve maintainability, enable linting across all code.

**Component architecture:**

- [x] Break `AccessForm.svelte` (765 lines) into step components + shared state:
  - `AccessFormStep1.svelte` (business type)
  - `AccessFormStep2.svelte` (business details + Google Places)
  - `AccessFormStep3.svelte` (contact info)
  - `AccessFormSuccess.svelte`
- [x] Add Google Maps script deduplication check in AccessForm
- [x] Create `+error.svelte` with branded error page

**Configuration & linting:**

- [x] Remove `functions/` from ESLint ignores, add separate config if needed
- [x] Document Vite HMR patch in a comment in `vite.config.ts`
- [x] Standardize Cloud Function error codes (4xx for client errors, 5xx for server)
- [x] Add Firebase security headers to `firebase.json`

**Agent hardening:**

- [x] Add explicit JSON parsing error handling in `places_tools.py` and `tripadvisor_tools.py`
- [x] Add `httpx.AsyncClient` cleanup function for graceful shutdown
- [x] Add pagination incomplete indicator in TripAdvisor reviews response
- [x] Validate specialist brief keys against allowed set

### Sprint 3 — Hardening & Polish ✓

Expand test coverage, improve accessibility, handle edge cases.

**Test coverage:**

- [x] Add Cloud Function endpoint tests (mock Resend, ElevenLabs, Vertex AI, ADK)
- [x] Add agent tests for malformed JSON responses and concurrent tool calls
- [x] Add `onActivity` to shared test mock factories in chat-state and sse-client specs
- [x] Add test for malformed progress/token SSE events

**Accessibility & SEO:**

- [x] Add focus trap to AccessForm modal
- [x] Add ARIA attributes to suggestion dropdown (`role="listbox"`, `aria-selected`, `aria-autocomplete`)
- [x] Add `loading="lazy"` to DataSources logo images
- [x] Add `robots.txt` and `sitemap.xml`

**Developer experience:**

- [x] Create `.env.example` files for root and `agent/`
- [x] Change `@typescript-eslint/no-explicit-any` from warn to error
- [x] Extract heading typography as Tailwind utility (used in 4+ components)
- [x] Add image size validation before base64 encoding in agent
