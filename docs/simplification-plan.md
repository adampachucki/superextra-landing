# Superextra Simplification Plan

**Status:** active, awaiting review before execution.
**Scope:** 5 phases (Phase 6 from prior draft dropped — see end).
**Goal:** reduce ~5k LOC of low-value complexity and clarify three oversized frontend components, without changing product behavior or agent output quality.

---

## 1. Context

The Superextra codebase (SvelteKit landing + agent UI on two Firebase Hosting targets, Cloud Functions, ADK-based Python agent) has accumulated three classes of weight:

- **Dead code** — a non-streaming Cloud Function endpoint with zero callers, 14 mockup component variants that are gallery-only, an unused TTS import, 8 aspirational planning docs.
- **Duplicated logic** — Google Places autocomplete implemented twice (RestaurantHero + agent chat page), RAF typewriter pattern implemented 4× in one file and 2× elsewhere.
- **Oversized monoliths** — `RestaurantHero.svelte` (1063 LOC), `StreamingProgress.svelte` (508 LOC), `chat-state.svelte.ts` (611 LOC) each do several loosely-coupled things.

Five phases, easiest and lowest-risk first. Each phase has an explicit design, targeted regression tests, and a rollback path.

---

## 2. Ground rules (all phases)

### Don't-touch (load-bearing workarounds — do not regress)

- `_append_sources` callback in `agent/superextra_agent/specialists.py` — ADK `AgentTool` drops grounding metadata.
- `res.on('close')` in `agentStream` (`functions/index.js`) — Cloud Run HTTP/2 quirk.
- `agentStream` served from `run.app`, not `cloudfunctions.net` — GFE kills SSE on the `cloudfunctions.net` proxy.
- `vite.config.ts` HMR patches — mobile Safari reconnect fix.
- Context-injection instruction providers (`_orchestrator_instruction`, `_synthesizer_instruction`, `_follow_up_instruction`, `_router_instruction`) — keep untouched unless the phase explicitly edits them.
- Anti-sycophancy checkpoints in orchestrator/specialist/synthesizer prompts.
- `_skip_enricher_if_cached` in `agent/superextra_agent/agent.py:85-90` — out of scope per user.

### Verified facts (carried over from prior verification round)

- `/build/` is gitignored at `.gitignore:10`. No action needed.
- `/api/agent` non-streaming endpoint in `functions/index.js:149-332` has no frontend caller. Its rewrite at `firebase.json:87-89` is orphaned. Safe to delete together.
- **DO NOT delete `src/routes/agent/` or `src/routes/agent/chat/`.** These are the production agent UI served on `agent.superextra.ai` via the `agent` Firebase hosting target (`firebase.json:50-108`). Only the `landing` target 301-redirects `/agent/*` to the subdomain.
- `src/routes/memo/+page.svelte` is linked from `Footer.svelte:59`. Leave untouched.
- TTS import at `ChatThread.svelte:4` is never called in the file — safe to remove.
- Production mockup usage (confirmed via `PlatformCards.svelte` imports): `MarketLandscapeWideV1`, `MenuPricingV1`, `RevenueSalesV2`, `MarketingV2`, `GuestIntelligenceV2`, `LocationTrafficV1`, `OperationsV1`. Everything else in `src/lib/components/mockups/` is gallery-only.

### Test commands (per CLAUDE.md)

| Command                                               | Scope                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------- |
| `npm run test`                                        | Vitest — SSE client, chat state, new utilities                      |
| `cd functions && npm test`                            | node:test — stream parser, endpoints                                |
| `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` | pytest — agent                                                      |
| `npm run test:evals`                                  | live Gemini eval calls — **manual approval required**, Phase 5 only |
| `npm run lint`, `npm run check`, `npm run build`      | static checks                                                       |

### Branching

- One phase = one branch. Branch name pattern: `simplify/phase-N-short-name`.
- Phase 4 is three sub-PRs on one phase branch (4.1, 4.2, 4.3 each as a commit chain or stacked branches) for bisectability.
- Dev server stays as systemd service on port 5199 — never run `npm run dev` manually.

### Baseline capture (do once, before Phase 1 starts)

Capture and stash in `docs/_baseline/` (gitignored):

1. Chrome DevTools MCP screenshots of `/`, `/agent/`, `/agent/chat/`, `/memo/`, `/login/` in both light and dark mode.
2. A live agent transcript for three fixed prompts (1 market-research, 1 pricing-comparison, 1 follow-up). Save synthesized report text.
3. `npm test`, `cd functions && npm test`, `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` output for a green baseline.

All phases diff against this.

---

## 3. Phase 1 — Free wins

**Single PR, no behavior change. Pure deletion + `git mv`.**

### Problem

Dead code and stale docs inflate the codebase without contributing value:

- `agent()` non-streaming endpoint with no callers.
- Four exported constants in `utils.js` consumed only by their own tests.
- Unused TTS import in `ChatThread.svelte`.
- 14 mockup component variants outside the production flow.
- 8 markdown planning docs that describe aspirational or superseded work.

### Solution

Execute in this order to surface hidden callers via clean 404s:

1. **Remove `/api/agent` rewrite** at `firebase.json:87-89` — do before endpoint delete so a stray caller fails loudly.
2. **Delete `agent()`** in `functions/index.js:149-332` (function + its helper inline title generation).
3. **Delete its tests** in `functions/index.test.js:310-377`.
4. **Delete unused constants** in `functions/utils.js:139-180`: `SPECIALIST_KEYS`, `TOOL_LABELS`, `SPECIALIST_OUTPUT_KEYS`, `PLACES_TOOL_LABELS`. **Keep** `SPECIALIST_RESULT_KEYS` (used in `index.js`).
5. **Delete their meta-test** at `functions/utils.test.js:298-316`.
6. **Delete unused TTS import** at `src/lib/components/restaurants/ChatThread.svelte:4`.
7. **Delete unused mockup variants** in `src/lib/components/mockups/`: `GuestIntelligenceV1`, `GuestIntelligenceV3`, `LocationTrafficV2`, `LocationTrafficV3`, `MarketingV1`, `MarketingV4`, `MarketLandscapeV2`, `MarketLandscapeV3`, `MenuPricingV2`, `MenuPricingV4`, `OperationsV2`, `RevenueSalesV1`, `RevenueSalesV3`, `MockupBar.svelte`.
8. **Delete `src/routes/mockups/+page.svelte`** (internal gallery, no inbound links — verify with `grep -r '/mockups' src/` first).
9. **Archive stale docs** via `git mv` into `docs/archived/`:
   - `agent-architecture-review.md`, `agent-architecture-simplification.md`, `agent-capabilities-roadmap.md`, `two-phase-research.md`, `shared-prompt-architecture.md`, `cross-session-memory.md`, `browser-agent-research.md`, `data-acquisition-research.md`.
   - For `agent-improvements-plan.md`: scan each "Phase X" heading against code; add a front-matter block tagging each section as `shipped` / `not-built` / `superseded`, **then** archive.
   - Keep in `docs/` root: `deployment-gotchas.md`, `ios-safari-safe-areas.md`, `vm-setup.md`, `agent-subdomain-options.md`, this plan.

### Testing

**Automated (must all pass green):**

```bash
npm run lint \
  && npm run check \
  && npm run build \
  && npm run test \
  && cd functions && npm test && cd .. \
  && cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v
```

**Targeted regression checks:**

| Cut                             | What could break                                     | Check                                                                                                                                                                                            |
| ------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/api/agent` endpoint + rewrite | Hidden caller                                        | `grep -rn "'/api/agent'" src/ functions/` (exclude `/stream`, `/check`) must return no hits                                                                                                      |
| Constants removal               | Internal import path                                 | `grep -rn "SPECIALIST_KEYS\|TOOL_LABELS\|SPECIALIST_OUTPUT_KEYS\|PLACES_TOOL_LABELS" functions/ src/` must return no hits                                                                        |
| TTS import in ChatThread        | Used via dynamic path                                | `grep -n "tts\." src/lib/components/restaurants/ChatThread.svelte` must return no hits                                                                                                           |
| Mockup deletions                | A kept mockup accidentally deleted / dangling import | `npm run build` succeeds; `npm run check` clean                                                                                                                                                  |
| Gallery route deletion          | Inbound links                                        | `grep -rn "/mockups" src/ docs/` returns only the archived text, not active hrefs                                                                                                                |
| Docs archive                    | CLAUDE.md or README links into archived files        | `grep -rn "docs/agent-improvements-plan\|docs/agent-architecture\|docs/two-phase\|docs/shared-prompt\|docs/cross-session\|docs/browser-agent\|docs/data-acquisition" .` — update remaining links |

**Manual browser verification (Chrome DevTools MCP):**

1. `http://localhost:5199/` — platform-card grid shows all 7 retained mockups, no console errors.
2. `http://localhost:5199/agent/` — renders.
3. `http://localhost:5199/agent/chat/` — place search works, streaming agent query completes.
4. `http://localhost:5199/memo/` — still renders.
5. Light/dark toggle on `/` and `/agent/`.
6. Submit intake form at `/` → confirm email arrives (Resend).

Diff screenshots vs baseline — retained mockup cards must be pixel-identical.

### Rollback

Pure `git revert`. Every change is a deletion or `git mv`.

### Stop & verify gate

All suites green, manual checklist signed off, baseline screenshot diff shows zero regressions on retained mockup cards, manual live agent query on `/agent/chat/` matches baseline transcript in structure.

---

## 4. Phase 2 — Dedup extractions

**Single PR, 2 commits.** Introduce two new utility modules. No product behavior changes.

### Problem

Two pieces of logic are copy-pasted:

- **Google Places autocomplete** — identical implementation in `RestaurantHero.svelte:358-525` and `src/routes/agent/chat/+page.svelte:263-425`: same timezone-to-country map, same lazy Google Maps script loader, same debounce pattern, same suggestion-fetch + retry-without-type logic. ~150 LOC × 2.
- **Typewriter RAF pattern** — four nearly identical loops in `StreamingProgress.svelte` (`drainData` :54-64, `drainSearch` :100-107, `drainExcerpt` :137-147, `drainRead` :196-206), one in `ChatThread.svelte:55-89`, one in the agent chat page. Each maintains its own `targets`/`display`/`rafs` dictionaries and identical cleanup effects.

### Solution

#### 4.1. `src/lib/place-search.svelte.ts` — factory returning a reactive store

**Why factory, not singleton:** the two callsites (hero + chat page) can render concurrently during the hero→chat transition; each needs its own state.

```ts
// src/lib/place-search.svelte.ts
import { PUBLIC_GOOGLE_PLACES_KEY } from '$env/static/public';

export interface PlaceSuggestion {
  name: string;
  secondary: string;
  placeId: string;
}

export interface PlaceSearch {
  readonly query: string;
  readonly suggestions: PlaceSuggestion[];
  readonly loading: boolean;
  readonly selected: PlaceSuggestion | null;
  setQuery(value: string): void;
  select(suggestion: PlaceSuggestion): void;
  clear(): void;
}

interface Options {
  debounceMs?: number; // default 220
  minChars?: number;   // default 2
  types?: string[];    // default ['restaurant','cafe','bar','hotel','food']
}

export function createPlaceSearch(opts: Options = {}): PlaceSearch { ... }

// Module-level singletons (shared across instances):
let mapsPromise: Promise<void> | null = null;
let browserCountry = ''; // resolved once

function loadGoogleMaps(): Promise<void> { /* existing logic, lifted */ }
function resolveBrowserCountry(): string { /* existing tz map, lifted */ }
```

Internals use `$state` runes so callsites can bind getters. `setQuery` debounces with a single timer, aborts any in-flight fetch on next call. `select` sets `selected` and clears `suggestions`. `clear` resets all fields.

**The timezone→country map moves verbatim from `RestaurantHero.svelte:389-417` — single source of truth.**

#### 4.2. `src/lib/typewriter.ts` — pure utility, no Svelte

**Why not a rune-based module:** StreamingProgress needs per-ID state across dynamic sets of items; a plain callback-based API is simpler than trying to make the factory stateful.

```ts
// src/lib/typewriter.ts
export interface TypewriterController {
  setTarget(target: string): void;
  stop(): void;
  reset(): void;
}

interface Options {
  charsPerFrame?: number; // default 2 (matches current code)
  onUpdate: (current: string) => void;
  onDone?: () => void;
}

export function createTypewriter(opts: Options): TypewriterController { ... }

// For the dictionary-of-typewriters pattern used 3× in StreamingProgress:
export interface TypewriterGroup<K extends string = string> {
  setTarget(id: K, target: string, resetOnNew?: boolean): void;
  remove(id: K): void;
  prune(keepIds: Set<K>): void;
  stopAll(): void;
}

export function createTypewriterGroup(opts: Options): TypewriterGroup { ... }
```

`createTypewriter` owns one `requestAnimationFrame` cycle. `createTypewriterGroup` owns a map of them keyed by ID, plus `prune(keepIds)` to cancel RAFs for IDs no longer present — replacing the hand-written cleanup loops in StreamingProgress.

#### Callsite migrations

- `RestaurantHero.svelte:358-525` → delete inline Google Places code, replace with `const place = createPlaceSearch()` + bind in template. ~160 LOC deleted.
- `src/routes/agent/chat/+page.svelte:263-425` → same treatment. ~160 LOC deleted.
- `StreamingProgress.svelte`:
  - `drainData` + its effect (`:50-93`) → `const dataTypers = createTypewriterGroup({ onUpdate: (id, v) => dataDisplay[id] = v })`.
  - `drainSearch` (`:95-130`) → `const searchTyper = createTypewriter({ onUpdate: v => searchDisplay = v })`.
  - `drainExcerpt` (`:132-171`) → `createTypewriterGroup`.
  - `drainRead` (`:192-232`) → `createTypewriterGroup`.
- `ChatThread.svelte:55-89` → `createTypewriter` for message body.

Net: ~450 LOC removed from the three frontend files, ~180 LOC added in the two utilities. Net reduction ~270 LOC.

### Testing

**New unit specs:**

- `src/lib/place-search.spec.ts`
  - Debounce: rapid `setQuery` calls produce one fetch after `debounceMs`.
  - Abort: overlap `setQuery` before fetch resolves → earlier promise cancelled.
  - Timezone map: `Europe/Warsaw` → `pl`, `America/New_York` → `us`, unknown → language fallback.
  - Minimum characters: below `minChars` clears suggestions without fetch.
  - Fallback: when type-filtered fetch returns empty, second fetch without type fires.
  - `select` populates `selected` and clears `suggestions`.
  - `clear` resets everything.
- `src/lib/typewriter.spec.ts`
  - Single typewriter: drains target character-by-character, `onDone` fires exactly once.
  - Update target mid-drain: extended target continues without reset; divergent target resets.
  - `stop` cancels in-flight RAF.
  - Group: 3 concurrent typewriters for different IDs do not cross-contaminate.
  - `prune(keepIds)` cancels RAFs and removes state for non-present IDs.

**Automated:**

```bash
npm run test && npm run check && npm run build
```

Existing `sse-client.spec.ts` and `chat-state.spec.ts` must remain green (no dependency change).

**Manual (Chrome DevTools MCP):**

- Hero `/` and chat `/agent/chat/`: type "San Fran" → ≥3 suggestions → select → chip populates. Clear → restart.
- Rapid-type stress: hold down a letter then navigate away mid-fetch → no console errors, no unhandled promise rejections.
- Live agent query on `/agent/chat/`: 4-channel streaming typewriter cadence matches baseline recording by visual comparison. Attach performance trace if cadence looks off.

**Svelte MCP:** run `svelte-autofixer` on each modified `.svelte` file.

### Rollback

`git revert` the PR. Re-inlining six callsites is manual but the revert restores them.

### Stop & verify gate

New unit specs green, existing suites green, Svelte MCP clean, both place-search flows verified, live-stream visual diff passes.

---

## 5. Phase 3 — Test consolidation

**Single PR. Lowest-risk phase.** Only touches test files.

### Problem

`functions/utils.test.js` is 1429 LOC. Large fraction is "tool called → emit activity" asserted 10× for each specialist name with identical logic, plus three redundant code paths for the same search-activity behavior. The real testable logic (stream parser state machine, buffering, malformed-JSON resilience) is well-sized. The noise buries the signal.

`functions/index.test.js:310-377` was already removed in Phase 1 alongside the `agent()` endpoint.

### Solution

Parameterize repeated assertions:

- Collapse 10× "completion event emits for specialist X" into one `test.each([...SPECIALISTS])`.
- Collapse 3× "activity emitted from {functionCall, stateDelta, groundingMetadata}" into one `test.each` keyed by source with a shared assertion helper.
- Keep (do not collapse):
  - Final-report extraction (text + sources).
  - Router-response extraction path.
  - Malformed-JSON tolerance (`:549-556`).
  - Chunked-event buffering (`:558-565`).
  - Empty-stream handling (`:567-575`).
  - Synthesizer token emission + thought filtering (`:445-483`).
  - Source dedupe by URL.

Target: `utils.test.js` from 1429 → ~700 LOC with no branch coverage loss.

### Testing

**Coverage diff is the primary gate:**

```bash
cd functions && node --experimental-test-coverage --test utils.test.js index.test.js
```

Capture coverage report before the PR, again after consolidation. **Line coverage for `utils.js` must not decrease.** Post the before/after side-by-side in the PR description.

**Review checklist for each deleted test:**

- Does another remaining test exercise the same branch? If no, keep the test.
- Is the deletion covered by a new parameterized case? If no, reinstate.

No browser testing needed.

### Rollback

Pure `git revert`.

### Stop & verify gate

`cd functions && npm test` green, coverage unchanged or improved.

---

## 6. Phase 4 — Component splits

**Three sub-PRs on one phase branch for bisectability.** Consumes Phase 2 utilities.

### Phase 4.1 — Split `RestaurantHero.svelte` (1063 → ~250 + three siblings)

#### Problem

`RestaurantHero.svelte` mixes: hero headline + animating placeholder, prompt textarea + auto-resize + Enter submit, dictation integration, Google Places input (now extracted in Phase 2), topic pill pool (28 items + shuffle + responsive labels), keyboard handling, submit-transition state. The file resists change because edits to any concern risk the others.

#### Solution

Extract three sibling components into `src/lib/components/restaurants/`:

**`InputPrompt.svelte`** — textarea + animating placeholder + dictation button:

```svelte
<script lang="ts">
	let {
		value = $bindable(''),
		placeholder, // full animated text, parent controls rotation
		onSubmit, // called on Enter (no Shift)
		onMic, // called when mic clicked
		dictating = false,
		disabled = false
	}: {
		value?: string;
		placeholder: string;
		onSubmit: () => void;
		onMic: () => void;
		dictating?: boolean;
		disabled?: boolean;
	} = $props();
</script>
```

Owns: textarea auto-resize `$effect`, `handleKeydown` (Enter/Shift-Enter), focus-on-mount ref, mic button rendering. Does **not** own: the animating-placeholder state (too tied to hero idle logic — stays in parent).

**`PlaceSearchWidget.svelte`** — consumes Phase 2 `createPlaceSearch`:

```svelte
<script lang="ts">
	import type { PlaceSearch } from '$lib/place-search.svelte';
	let {
		search,
		nudge = false, // highlights input when parent wants attention
		expanded = $bindable(false),
		placeholder = 'Which restaurant?'
	}: {
		search: PlaceSearch;
		nudge?: boolean;
		expanded?: boolean;
		placeholder?: string;
	} = $props();
</script>
```

Owns: input field, suggestion dropdown, selected-place chip, expand/collapse transition. Parent passes in the `PlaceSearch` instance — widget is stateless beyond presentation.

**`TopicPills.svelte`** — pill pool self-contained:

```svelte
<script lang="ts">
	let {
		onPick, // (query: string) => void
		isMobile = false
	}: {
		onPick: (query: string) => void;
		isMobile?: boolean;
	} = $props();

	const PILL_POOL = [
		/* 28 items from RestaurantHero.svelte:126-280 */
	];
	const VISIBLE_COUNT = 6;
	// shuffle + pickPills + reshufflePills all move here
	// reshuffleSeed is a $state counter; keying the template on it re-runs entrance animations
</script>
```

Owns: the 28-item pool (moved verbatim), shuffle algorithm, short/long interleave, `pillGen` counter for animation re-trigger, entrance animation CSS.

**`RestaurantHero.svelte` after split** — thin composition + remaining concerns:

- Hero headline + subheadline.
- The animating placeholder loop (still stays here — driven by hero idle state).
- `userQuery` + `selectedPlace` state.
- `handleExplore` (validation + `onleave` dispatch + leaving transition).
- Composition: `<InputPrompt>`, `<PlaceSearchWidget>`, `<TopicPills>`.

Target: ~250 LOC.

#### Testing

**Automated:**

```bash
npm run test && npm run check && npm run build
```

No new unit specs required — components are presentational. Prop contracts are type-checked by `svelte-check`.

**Svelte MCP `svelte-autofixer`** on all four components.

**Manual regression checks (Chrome DevTools MCP):**

| Behavior                                            | Verification                                                                                     |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Textarea auto-focus on mount                        | `evaluate_script`: `document.activeElement.tagName === 'TEXTAREA'`                               |
| Enter submits (no Shift)                            | `type_text` with regular Enter → navigation to `/agent/chat` observed in `list_network_requests` |
| Shift+Enter inserts newline                         | `type_text` with `\r\n` → textarea value contains newline, no navigation                         |
| Animating placeholder stops when user types         | Type any char → `display` freezes (visual check)                                                 |
| Animating placeholder resumes when textarea cleared | Clear textarea → animation restarts                                                              |
| Pill click fills textarea                           | Click a pill → textarea value matches pill's `query`                                             |
| Pill reshuffle                                      | Trigger reshuffle (reload) → visible pills differ from previous load                             |
| Dictation mic toggle                                | Click mic → button state changes (not granting mic in headless — observe UI only)                |
| Place search                                        | Already covered in Phase 2 manual — re-run                                                       |
| Submit transition                                   | Type prompt + select place + Enter → hero leaves-animation plays, redirect to chat fires         |
| No console errors through full flow                 | Open console, walk full flow, expect zero errors                                                 |

**Diff screenshots** of hero vs baseline — idle, typing, with-place, nudge state.

### Phase 4.2 — Refactor `StreamingProgress.svelte` (508 → ~280 LOC)

#### Problem

Four nearly identical RAF typewriter loops, each with its own targets/display/rafs dictionaries and cleanup. Now that Phase 2 shipped `createTypewriterGroup` / `createTypewriter`, this component should be a thin consumer.

#### Solution

Replace each of the four RAF blocks with one call to `createTypewriterGroup` or `createTypewriter`:

- `drainData` + effect (`:50-93`) → `const dataTypers = createTypewriterGroup({ onUpdate: (id, v) => dataDisplay[id] = v })`; the `$effect` becomes: iterate `dataItems`, call `dataTypers.setTarget(item.id, item.detail, resetOnNew)`, then `dataTypers.prune(new Set(dataItems.map(i => i.id)))`.
- `drainSearch` (`:95-130`) → `const searchTyper = createTypewriter({ onUpdate: v => searchDisplay = v })`.
- `drainExcerpt` (`:132-171`) → `createTypewriterGroup`.
- `drainRead` (`:192-232`) → `createTypewriterGroup`.

Leave section-state derivations (`isSectionDone`, category filters, `readRevealedCount` stagger) untouched — they are not what makes the file oversized.

If the file is still >350 LOC after typewriter swap, extract section derivations to `src/lib/streaming-sections.ts` (pure helpers taking `ActivityItem[]` and returning grouped + derived state). Otherwise leave alone.

#### Testing

**Automated:**

```bash
npm run test && npm run check && npm run build
```

**Svelte MCP `svelte-autofixer`.**

**Manual regression (Chrome DevTools MCP):**

| Behavior                                              | Verification                                                                                                  |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| 4-channel streaming rendering                         | Live agent query; visual side-by-side with baseline                                                           |
| Section transitions (one ends before next shows Done) | Same live query; observe ordering                                                                             |
| Stagger reveal in read section (200ms cadence)        | Live query with ≥3 read items; observe staggered fade-in                                                      |
| Cleanup on navigation                                 | Start stream, navigate away mid-stream, check Chrome DevTools performance monitor for lingering RAF callbacks |

**Diff baseline:** record video of a streaming query, frame-compare cadence.

### Phase 4.3 — Split `chat-state.svelte.ts` (611 → ~400 + three modules)

**Highest-risk phase.** The file owns SSE lifecycle, Firestore recovery, iOS visibility handling, localStorage migration, conversation CRUD. Existing `chat-state.spec.ts` (770 LOC) must pass unchanged.

#### Problem

Four concerns in one file:

- **One-shot localStorage migration** (`:88-165`): merges legacy `sessionId` field into `id`, migrates `OLD_STORAGE_KEY` → `STORAGE_KEY`. Runs once per client lifetime on first mount after the code lands. After first run, this code is dead weight until a future schema change.
- **Recovery polling** (`:420-489`): polls `agentCheck` endpoint up to 60× at 3s intervals. Independent of SSE.
- **iOS visibility handler** (`:491-541`): complicated hand-rolled polling + timeout for iOS Safari WebContent suspension. Coupled to `loading` + `abortController` internals.
- **Core**: `send`, `switchTo`, `start`, `reset`, `deleteConversation`, `buildHistory`, `persist`, conversation CRUD.

#### Solution

Extract three modules with explicit dependency injection (no hidden globals):

**`src/lib/chat-migration.ts`** — pure function, no reactivity:

```ts
export interface MigratedStorage {
	activeId: string | null;
	conversations: Conversation[];
}

/**
 * Runs once on first read after this code ships. Idempotent.
 * - Merges legacy `sessionId` field into `id` (first-claim wins).
 * - Migrates OLD_STORAGE_KEY shape to STORAGE_KEY if STORAGE_KEY missing.
 * - Writes migrated shape back to localStorage.
 * Returns the post-migration snapshot, or null if no storage.
 */
export function runChatMigration(storage: Storage = localStorage): MigratedStorage | null;
```

Called once from `chat-state.svelte.ts` module init. Pulls the migration block (`:88-165`) verbatim; only the state assignments move back to the caller.

**`src/lib/chat-recovery.ts`** — Firestore polling with explicit context:

```ts
export interface RecoveryContext {
	getSessionId(): string | null; // current conversation id
	isCurrentSession(sid: string): boolean; // to guard against session switch during polling
	onReply(reply: string, sources?: ChatSource[]): void;
	onError(message: string): void;
	onComplete(): void;
	checkUrl(sessionId: string): string; // allows dev/prod URL swap
}

export async function recoverStream(
	ctx: RecoveryContext,
	opts?: {
		maxAttempts?: number; // default 60
		intervalMs?: number; // default 3000
	}
): Promise<boolean>;
```

Pulls `:420-489` verbatim. Caller supplies `onReply` (which pushes to `messages`), `onError` (sets `error`), `onComplete` (clears `loading` + `recovering`).

**`src/lib/ios-sse-workaround.ts`** — visibility resume handler:

```ts
export interface IosVisibilityContext {
	isLoading(): boolean;
	setLoading(v: boolean): void;
	abortStream(): void;
	recover(): Promise<unknown>;
	hasPendingUserMessage(): boolean;
}

export function handleReturnFromHidden(ctx: IosVisibilityContext, hiddenMs: number): void;
```

Pulls `:491-541` verbatim. Encapsulates the 30s threshold, the abort → poll → recover pattern, and the 2s safety timeout. Caller wires `document.addEventListener('visibilitychange', ...)` and calls this with `hiddenMs` tracked at the caller.

**`chat-state.svelte.ts` after split** — owns core only:

- Module state: `messages`, `loading`, `recovering`, `error`, `streamingText`, `streamingProgress`, `streamingActivities`, `conversations`, `currentId`, `placeContext`, `abortController`, `pageHidden`.
- Functions: `send`, `buildHistory`, `generateTitle`, `loadConversation`, `syncCurrentToList`, `persist`, `appendToConversation`, `start`, `reset`, `switchTo`, `deleteConversation`.
- One-shot init calls `runChatMigration()`; `recover()` delegates to `recoverStream({...})`; `handleReturn()` delegates to `handleReturnFromHidden({...})`.

Target: ~400 LOC.

#### Testing

**Non-negotiable:** existing `chat-state.spec.ts` (770 LOC) must pass unchanged.

**New unit specs:**

- `src/lib/chat-migration.spec.ts`
  - Feed a legacy single-conversation shape under `OLD_STORAGE_KEY` → migrated shape under `STORAGE_KEY`; `OLD_STORAGE_KEY` cleared.
  - Feed legacy shape with separate `sessionId` field → merged into `id` (first claim wins on duplicates).
  - Feed already-migrated shape → no-op.
  - Feed empty storage → returns `null`.
  - Corrupt JSON → catches and returns `null` (matches current silent-fail).

- `src/lib/chat-recovery.spec.ts` (fake timers, mock fetch)
  - Success on first poll (`ok: true, reply: "..."`) → `onReply` called once, `onComplete` called.
  - `session_not_found` → `onError("Session not found...")` called, no further polls.
  - `agent_unavailable`, `timed_out` → same pattern.
  - Still processing → polls interval until reply or `MAX_ATTEMPTS`.
  - Session switch mid-poll (`isCurrentSession` returns false) → terminates cleanly.
  - Fetch throws → break loop (matches current behavior).

- `src/lib/ios-sse-workaround.spec.ts` (fake timers)
  - `hiddenMs < 30_000` with loading → no-op.
  - `hiddenMs ≥ 30_000` with loading → `abortStream` + polling `setLoading(false)` cycle → `recover` fired.
  - Safety timeout at 2s forces `loading=false` + recover.
  - No pending user message → no-op.

**Automated:**

```bash
npm run test && npm run check && npm run build
```

**Manual (Chrome DevTools MCP):**

- Full live agent query on `/agent/chat/` — streams correctly, final message saved, reload restores.
- Backend-recovery path: start a query, kill the SSE connection mid-stream (close DevTools network → offline) → reload → recovery polling delivers final message.
- iOS backgrounding: emulate via Chrome DevTools `emulate` or manual test on real iOS if available — background tab for 45s during stream → return → `handleReturnFromHidden` fires, recovery delivers reply.
- Legacy storage migration: manually write a legacy shape to `localStorage` before page load, reload → migration runs, conversation still usable. (Do this once post-split to verify the migration code path still fires.)

#### Rollback

Per-PR `git revert` is clean. Partial landing (4.1 merged, 4.3 in review) is safe — files are disjoint.

### Stop & verify gate (end of Phase 4)

- `npm run test` green.
- `npm run check` clean.
- `npm run build` succeeds.
- Svelte MCP clean on all modified components.
- Chrome MCP manual checklists for 4.1, 4.2, 4.3 all signed off.
- End-to-end live agent query on `/agent/chat/` produces a synthesized report matching baseline in structure (section headers, citation count within ±10%).

---

## 7. Phase 5 — Agent instruction consolidation (requires live evals)

**Single PR. Markdown-only plus a tiny loader change.**

### Problem

Two overlapping canonical sources explain "how specialists should answer":

- `agent/superextra_agent/instructions/AUTHORING.md` — for humans writing instructions.
- `agent/superextra_agent/instructions/specialist_base.md` — read by the template loader at runtime and injected into every specialist.

Both describe source-citation rules, brief-alignment requirements, answer structure. Edits to either drift out of sync. Additionally, `research_orchestrator.md` fails to clearly separate `review_analyst` vs `guest_intelligence` ownership — both touch reviews, the orchestrator routes ambiguously.

**Important constraint (from the user's pushback):** only extract content that is **byte-identical or near-identical** across both files. Paraphrased-but-similar content stays — rewriting it means changing the LLM prompt, which is a behavior change, not a refactor.

### Solution

**Step 0 — pre-check (before any edit):**

1. Diff `AUTHORING.md` against `specialist_base.md` with `diff --word-diff`. Identify exact phrases that appear verbatim or near-verbatim in both.
2. If <30% overlap: **abort Phase 5** and report. The earlier review overstated duplication.
3. If ≥30% overlap: proceed.

**Step 1 — extract shared block** into `agent/superextra_agent/instructions/_shared_guidance.md`. Only move verbatim-shared content. `AUTHORING.md` (human-facing) ends with a `See _shared_guidance.md` link. `specialist_base.md` uses an include (the template loader in `specialists.py:_make_instruction` around `:134-172` reads and interpolates).

**Step 2 — if `specialists.py:_make_instruction` currently prefixes each specialist file with a date string:** hoist that prefix out of each per-specialist file into the loader. Verify by reading `_make_instruction` and each of the 9 specialist files to confirm the prefix is indeed identical per-file before hoisting.

**Step 3 — clarify ownership** in `research_orchestrator.md` (the section that lists specialists and what they own). Add explicit boundary:

> - `review_analyst` owns structured API review analysis: rating distributions, owner-response rate, platform ranking. Calls TripAdvisor/Google Places APIs directly.
> - `guest_intelligence` owns cross-platform qualitative sentiment: complaint/praise themes, trend analysis across review text. Uses google_search only, no structured APIs.
> - If a brief touches both (e.g. "why does Google rate them higher than TripAdvisor"), assign to `guest_intelligence` for the qualitative why, `review_analyst` for the structural breakdown.

This is the only content edit; the earlier recommendation to "merge agents" is NOT done.

**Do not touch** other specialist instruction files. Do not touch synthesizer or router.

### Testing

**Pytest (must pass):**

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v
```

Critical:

- `tests/test_instruction_providers.py` — catches template loader path / include breakage.
- `tests/test_specialist_callbacks.py`, `tests/test_append_sources.py`, `tests/test_error_callbacks.py` — specialist behavior unchanged.
- `tests/test_router_evals.py` — router decisions unchanged (runs offline fixtures).

**Live evals — requires explicit approval before each run (cost):**

Pre-Phase-5 baseline:

1. Pick 10 fixed prompts covering: 1 per specialist (8), 1 follow-up, 1 synthesizer-only.
2. Run on `main` via `npm run test:evals` or direct agent invocation. Capture router decisions + synthesized reports.

Post-change:

3. Re-run same 10 prompts on branch.
4. Diff: router must pick the same specialist subset. Synthesized reports must match in: section structure, citation count (±15%), length (±15%).
5. Any larger drift → investigate or revert.

### Rollback

`git revert`. Markdown-only changes.

### Stop & verify gate

Pytest green, eval diff within tolerance, three synthesized reports side-by-side match baseline in structure.

---

## 8. Phase 6 — dropped

### Why

Original draft had two items:

- **`_skip_enricher_if_cached` simplification** — dropped per user (caching behavior is out of scope).
- **`_embed_chart_images` callback removal** — this is a deliberate ADK workaround with an explanatory comment at `agent.py:108-114`. Removing it requires verifying the current ADK version embeds images natively via `BuiltInCodeExecutor`. If still stripped (likely — the workaround is recent), there is nothing to simplify. If fixed in a new ADK release, the cost of one callback vs the risk of breaking chart rendering in production tips toward keeping the callback.

**Decision:** leave the callback as-is. If there's future appetite to remove it, run a time-boxed investigation first (~1 day): test `BuiltInCodeExecutor` on current ADK, inspect whether inline_data images survive to the synthesizer's response. If they do, remove the workaround in its own small PR. Until then, no change.

---

## 9. End-to-end verification (post-Phase 5)

Run the full battery:

```bash
npm run lint \
  && npm run check \
  && npm run build \
  && npm run test \
  && cd functions && npm test && cd .. \
  && cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v
```

Chrome DevTools MCP end-to-end session on `http://localhost:5199/`:

1. Land on `/`, verify 7 platform cards render, dark-mode toggle works, intake form submits.
2. On `/` hero: fill prompt + select place + submit → redirect to `/agent/chat/` with state preserved.
3. On `/agent/chat/`: confirm live agent query streams through `StreamingProgress` + lands in `ChatThread` with typewriter cadence matching baseline.
4. Background the tab for 45s during streaming (DevTools → `emulate` throttling or real device) → return → recovery fires, reply arrives.
5. Issue a follow-up query referencing the first → `final_report` state retained, router dispatches to `follow_up`.
6. Submit intake form at `/` → email arrives via Resend.

Diff screenshots + synthesized report against pre-Phase-1 baseline. Structural parity required; pixel-level parity on retained mockup cards.

---

## 10. Critical files index

| Phase | Files                                                                                                                                                                                                                                                                                                                                                                                     |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | `firebase.json`, `functions/index.js`, `functions/index.test.js`, `functions/utils.js`, `functions/utils.test.js`, `src/lib/components/restaurants/ChatThread.svelte`, `src/lib/components/mockups/*` (14 deletions), `src/routes/mockups/+page.svelte` (delete), `docs/*.md` (archive 8, annotate+archive `agent-improvements-plan.md`), `CLAUDE.md` (remove any links to archived docs) |
| 2     | NEW: `src/lib/place-search.svelte.ts`, `src/lib/place-search.spec.ts`, `src/lib/typewriter.ts`, `src/lib/typewriter.spec.ts`. MODIFIED: `src/lib/components/restaurants/RestaurantHero.svelte`, `src/routes/agent/chat/+page.svelte`, `src/lib/components/restaurants/StreamingProgress.svelte`, `src/lib/components/restaurants/ChatThread.svelte`                                       |
| 3     | `functions/utils.test.js`                                                                                                                                                                                                                                                                                                                                                                 |
| 4.1   | NEW: `src/lib/components/restaurants/InputPrompt.svelte`, `PlaceSearchWidget.svelte`, `TopicPills.svelte`. MODIFIED: `RestaurantHero.svelte`                                                                                                                                                                                                                                              |
| 4.2   | `src/lib/components/restaurants/StreamingProgress.svelte`; possibly new `src/lib/streaming-sections.ts`                                                                                                                                                                                                                                                                                   |
| 4.3   | NEW: `src/lib/chat-migration.ts` (+ `.spec.ts`), `src/lib/chat-recovery.ts` (+ `.spec.ts`), `src/lib/ios-sse-workaround.ts` (+ `.spec.ts`). MODIFIED: `src/lib/chat-state.svelte.ts`                                                                                                                                                                                                      |
| 5     | NEW: `agent/superextra_agent/instructions/_shared_guidance.md`. MODIFIED: `specialist_base.md`, `AUTHORING.md`, `research_orchestrator.md`, `agent/superextra_agent/specialists.py` (loader only if hoisting date prefix)                                                                                                                                                                 |

---

## 11. Open questions for reviewer

1. **Branch strategy** for Phase 4 — three separate PRs on one branch (stacked), or three commits on one PR? Stacked PRs are more bisectable; one-PR is lower overhead.
2. **Live eval cost for Phase 5** — budget for two full eval runs (baseline + post-change). Approve per-run or upfront?
3. **Phase 2 `createTypewriterGroup` API** — is the `prune(keepIds)` pattern acceptable, or prefer explicit `remove(id)` only? (The prune pattern matches the existing `$effect` cleanup shape closely.)
4. **Legacy localStorage migration** (Phase 4.3) — keep forever as `runChatMigration()`? Or add a `deprecated_after: 2026-10` marker for eventual deletion?
5. **Phase 5 "abort if overlap <30%"** — is 30% the right threshold, or should we proceed regardless and extract what we can?
