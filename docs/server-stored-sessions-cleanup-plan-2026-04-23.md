# Cleanup plan — implementation review findings (2026-04-23)

## Context

The server-stored-sessions rearchitecture shipped to production on 2026-04-23 (12 stages, logged in `docs/server-stored-sessions-impl-log.md`). The implementation review at `docs/server-stored-sessions-implementation-review-2026-04-23.md` identified four findings plus one simplify item.

I independently verified every claim against the codebase. All four findings are real and correctly scoped. One finding (Finding 1) has a sharper-than-described failure mode. The review's restraint on escalation features (no `agentRead`, no `sessions_private`, no bridge) is aligned with the plan's "no weird-case creep" rule.

Goal of this plan: execute all four fixes plus the `history` drop, in a single disciplined pass. Net outcome: **one real UX bug fixed, ~900 lines of dead code removed, one prerender warning silenced, zero new behavior added.**

## The five fixes

### Fix 1 (P1) — Surface send/delete failures at every call site

**Transport layer — reorder so state changes follow POST success:**

- `src/lib/chat-state.svelte.ts:530-546` — `startNewChat` currently calls `selectSession(sid)` BEFORE `await postAgentStream(...)`. Reorder: POST first, `selectSession` only on success. Otherwise a failed first send leaves the URL on an orphan sid and the user sees "Couldn't load this chat" 10 seconds later — the worst-case failure mode the review understates.
- `src/lib/chat-state.svelte.ts:548-559` — `sendFollowUp` already throws cleanly on failure; no change needed at the transport layer.
- `src/lib/chat-state.svelte.ts:574-597` — `deleteSession` same shape; no change at the transport layer.

All three methods keep their current "throws on failure" contract. No `lastError` added to the singleton — error UI stays local to each route component that invokes these methods, avoiding cross-talk between composer and delete-confirm error slots.

**Callers — every `chatState.startNewChat` / `sendFollowUp` / `deleteSession` invocation needs a real handler:**

- `src/routes/agent/chat/+page.svelte:180-198` — `handleSend` uses `void chatState.sendFollowUp(...)` / `void chatState.startNewChat(...)`, then clears `query = ''` synchronously. Make handler async; await; on rejection restore `query`, keep `selectedPlace`, and set a local `$state` `sendError: string | null` rendered next to the composer.
- `src/routes/agent/chat/+page.svelte:136-170` — the `?q=` bootstrap path runs `void chatState.startNewChat(q, placeContext)` then strips `q` / `placeName` / etc. from the URL synchronously. On rejection the prefilled query is lost AND the URL already shows `?sid=<orphan>`. Await the call; only strip the params on success; on rejection keep the prefilled params intact and surface the error via the same `sendError` state the composer uses.
- `src/routes/agent/+page.svelte:16-26` — `handleLeave` runs `void chatState.startNewChat(...)` then `setTimeout(() => goto('/agent/chat'), 250)`. If the POST rejects the user still navigates and lands on an orphan sid. Await the start; navigate only on success; surface failure with a local `$state` `leaveError: string | null` on the landing page.
- `src/routes/agent/chat/+page.svelte:477-488` — delete `onclick` handlers use `void chatState.deleteSession(...)` and dismiss the confirm affordance immediately. Make the handlers async; await; only dismiss on success; on rejection keep the confirm open and set a local `deleteError: string | null` rendered inside the confirm block.

**Tests (in `src/lib/chat-state.spec.ts`):**

- `startNewChat` rejection → `activeSid` stays null, no `selectSession` side effects ran
- `sendFollowUp` rejection → throws; no optimistic state change
- `deleteSession` rejection → throws; `activeSid` preserved

Route-level error rendering is small enough to be caught by manual smoke (Fix 1 failure-mode section below) rather than needing new component-level tests. The component state variables are only read by templates and don't warrant unit coverage.

### Fix 2 (P2) — Delete `agentCheck` end-to-end

**Files (pure deletion):**

- `functions/index.js:509-591` — delete the `agentCheck` export and its ~80-line handler body. Under the new schema this endpoint reads `data.reply`/`data.sources` off the session doc, which no longer has those fields; every call returns `{ok:true,status,reply:null}`. It's actively misleading.
- `functions/index.test.js:734-878` — delete the entire `describe('agentCheck', …)` block and the `agentCheck` import at line 112.
- `firebase.json:79-83` — remove the `/api/agent/check` rewrite from the `agent` hosting target.
- `vite.config.ts:38-42` — remove the `/api/agent/check` dev proxy.
- `src/lib/firebase.ts:103` — update the stale comment that names agentCheck as part of the transport model.

**Net impact:** ~150 lines removed. Zero runtime behavior change.

### Fix 3 (P2) — Collapse `firestore-stream.ts` into a types-only module

**Files:**

- Create `src/lib/chat-types.ts` — new file containing only the exported types currently in `firestore-stream.ts`: `ChatSource`, `TurnCounts`, `TurnSummary`, `TimelineEvent`, and any related type unions. Pure re-exports moved verbatim. Approx 60 lines.
- `src/lib/chat-state.svelte.ts:25` — update `import type { ... } from '$lib/firestore-stream'` → `from '$lib/chat-types'`.
- `src/lib/components/restaurants/ChatThread.svelte:7` — same import swap.
- `src/lib/components/restaurants/StreamingProgress.svelte:2` — same.
- `src/lib/firestore-stream.ts` — **DELETE**. The runtime helpers (`subscribeToSession`, the module-local `postAgentStream`, first-snapshot timeout, permission-denied observer) have zero non-test callers after Stage 6. `chat-state.svelte.ts` owns its own listeners and POST path now.
- `src/lib/firestore-stream.spec.ts` — **DELETE**. All 29 test cases exercise the orphaned runtime.

**Net impact:** ~350 lines of runtime + ~500 lines of spec removed. Three import lines updated. Zero runtime behavior change.

### Fix 4 (Simplify #1) — Drop `history` payload

**Files:**

- `functions/index.js:15, :226, :371` — drop the `validateHistory` import, the `validateHistory(req.body?.history)` call, and `history` from the Cloud Task body.
- `functions/utils.js:31` — drop the `validateHistory` helper. Grep confirms it's only used from `functions/index.js` and `functions/utils.test.js`.
- `functions/utils.test.js:10, :153, :186-194` — drop the `validateHistory` import, the comment header, and the whole `describe('validateHistory', …)` block. Without this, `cd functions && npm test` fails.
- `functions/index.test.js` — remove `history` from request-shape and task-body assertions.
- `agent/worker_main.py:164` — drop `history: list | None = None` from the `RunRequest` pydantic model.
- `agent/tests/test_worker_main.py` — remove `history` from any `RunRequest(...)` test constructions if present.
- `src/lib/chat-state.svelte.ts:542`, `:557` — drop `history: []` from both `postAgentStream` payloads.

**Net impact:** ~15 lines removed. Zero runtime behavior change (worker never reads it).

### Fix 5 (P3) — Server-side guard on the sidebar listener

**Files:**

- `src/lib/chat-state.svelte.ts:206-212` — at the top of `attachSidebarListener`, add `if (typeof window === 'undefined') return;`. Or cleaner: import `browser` from `$app/environment` and `if (!browser) return;`.
- `src/lib/chat-state.svelte.ts:645-648` — the `sessionsList` getter also calls `void attachSidebarListener()`. Either add the same guard there, or rely on the one inside the function (cleaner — single guard).

Belt-and-suspenders: consider guarding `loadConfig()` in `src/lib/firebase.ts:19-26` with the same check. Not strictly needed if callers all guard, but it's one-line defense for any future server-side call.

**Net impact:** 2 lines added (one guard + one `browser` import). Removes the `[chat-state] sidebar listener bootstrap failed: TypeError: Failed to parse URL from /__/firebase/init.json` warning during `npm run build`.

## What's explicitly OUT of scope

Per the review's "Simplify next" §4 ("Keep escalation features out unless production evidence demands them") and the plan's own "What's explicitly excluded":

- No `agentRead` endpoint
- No `sessions_private/{sid}` doc split
- No mixed-version bridge
- No retry wrapper / fallback orchestration
- No soft-delete
- No defensive listener re-attach on participant arrayUnion (the open note about sidebar-reload behavior stays an unreproduced observation, not a finding)

## Sequencing

Two commits on a single feature branch `fix/post-impl-cleanup`:

**Commit A — Fix 1 only** (behavior change, needs its own review):

- The three method edits + two handler edits + `lastError` surface
- Test additions

**Commit B — Fixes 2, 3, 4, 5** (dead code + polish, zero runtime behavior change):

- All deletions
- `chat-types.ts` creation
- Three import swaps
- `history` drops
- SSR guard

Splitting lets Fix 1's UX change land/revert independently of the cleanup churn.

Alternative: one commit if the reviewer prefers a single cutover. Default is the split.

## Verification

Run before each commit:

- `npm run test` — vitest. New tests for Fix 1; Fix 3 removes 29 cases; rest unchanged.
- `cd functions && npm test` — Node test runner. Fix 2 removes ~8 cases; Fix 4 trims `history` assertions.
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q` — pytest. Fix 4's pydantic model change may surface.
- `npm run test:rules` — unchanged (no rules edits).
- `npm run check` — 0 errors expected.
- `npm run lint` — clean on touched files.
- `npm run build` — prerender completes AND no longer emits the sidebar-bootstrap warning (Fix 5 verification).

After both commits merged to main and GitHub Actions completes deploy:

- **Real production smoke** — start one chat at https://agent.superextra.ai/chat, complete one turn, confirm live timeline renders (events listener index is live, no `FAILED_PRECONDITION`). Submit one follow-up. Delete. Confirm the sidebar listener warning is gone from browser console.
- **Failure-mode smoke for Fix 1** — temporarily block `/api/agent/stream` in DevTools network panel, then verify all four first-turn entry points:
  1. `/agent/chat` composer → type + Enter → typed text preserved, `sendError` visible, `?sid=` stays off the URL
  2. `/agent/chat?q=…` bootstrap → reload with the prefilled params → prefilled query stays in the composer, error visible, URL params NOT stripped
  3. `/agent` landing → pick a place + type → `handleLeave` → stay on `/agent` with `leaveError` visible, no navigation
  4. Delete a chat with network blocked → confirm stays open, `deleteError` visible, chat still in sidebar. Unblock → retry from the same confirm → succeeds.

## Reuse / existing utilities

- `$app/environment`'s `browser` flag — idiomatic SvelteKit SSR guard
- Existing Svelte 5 `$state` primitive in each route component — hold error strings locally per page; no singleton state needed
- Existing vitest mocks in `src/lib/chat-state.spec.ts` already cover the fetch mocking pattern — reuse for the new rejection-path tests

## Critical files (quick reference)

**Deletions (full-file):**

- `src/lib/firestore-stream.ts`
- `src/lib/firestore-stream.spec.ts`

**Creations:**

- `src/lib/chat-types.ts` — types only, no runtime

**Edits:**

- `src/lib/chat-state.svelte.ts` — Fix 1 `startNewChat` reorder; Fix 3 import; Fix 4 payload drop; Fix 5 SSR guard
- `src/lib/chat-state.spec.ts` — Fix 1 transport-level rejection tests
- `src/routes/agent/chat/+page.svelte` — Fix 1 async handlers at three sites: `handleSend`, `?q=` bootstrap, delete onclick. Local `sendError` / `deleteError` `$state` vars.
- `src/routes/agent/+page.svelte` — Fix 1 async `handleLeave` with local `leaveError` `$state`
- `src/lib/components/restaurants/ChatThread.svelte` — Fix 3 import
- `src/lib/components/restaurants/StreamingProgress.svelte` — Fix 3 import
- `src/lib/firebase.ts` — Fix 2 comment, (maybe) Fix 5 guard
- `functions/index.js` — Fix 2 handler deletion; Fix 4 `validateHistory` import + call + task-body history drop
- `functions/index.test.js` — Fix 2 `agentCheck` tests deletion; Fix 4 history assertions
- `functions/utils.js` — Fix 4 `validateHistory` helper deletion
- `functions/utils.test.js` — Fix 4 `describe('validateHistory')` block deletion (NOT optional — `cd functions && npm test` fails without this)
- `firebase.json` — Fix 2 rewrite removal
- `vite.config.ts` — Fix 2 proxy removal
- `agent/worker_main.py` — Fix 4 pydantic field drop
- `agent/tests/test_worker_main.py` — Fix 4 history cleanup (if present)

## Estimated effort

~2 hours end-to-end including verification.

Line count expectation: **net ~-900 lines** across the repo (dead code + tests). Fix 1 adds maybe ~30 lines (error field + 3 test cases + minor handler logic).

## Not in this plan (will NOT be done)

- The "sidebar-update-after-contribute-without-reload" open-note behavior. Reviewer correctly flagged it as "not proven by static source review alone." Needs a reproducible test before any fix is planned.
- The missing-index class of bug (Stage 12 hotfix): the process gap — "diff plan §5 index table against firestore.indexes.json as an explicit exit criterion" — is a note for future implementation reviews, not a code change here.
