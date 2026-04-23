# Server-stored Sessions Implementation Review — 2026-04-23

Scope: review the deployed server-stored-sessions implementation against [docs/server-stored-sessions-plan.md](./server-stored-sessions-plan.md), [docs/server-stored-sessions-impl-log.md](./server-stored-sessions-impl-log.md), and the current repo state.

## Verdict

The rearchitecture basically landed. The session/turn/events model is in place, the worker uses creator UID + `turnIdx` as planned, creator-only delete is implemented, watchdog propagates terminal error state to the turn doc transactionally, and the old local-storage / recovery / visibility-return machinery is gone.

The main remaining work is not architectural. It is cleanup and simplification around the edges. Four concrete findings remain, one of them user-facing.

## Findings

### 1. [P1] Send and delete failures are silently discarded

Files:

- `src/routes/agent/chat/+page.svelte:180-198`
- `src/routes/agent/chat/+page.svelte:477-487`
- `src/lib/chat-state.svelte.ts:511-590`

`startNewChat`, `sendFollowUp`, and `deleteSession` all reject on auth, network, and HTTP failures. The route calls them with `void`, clears local UI state immediately, and never surfaces the failure.

Effects:

- a failed first send can clear the composer and leave a phantom active session selected
- a failed follow-up can drop the typed message with no UI feedback
- a failed delete can close the confirmation affordance even though nothing was deleted
- the browser can accumulate unhandled promise rejections

Recommended fix:

- make the route handlers async
- await the `chatState` calls
- only clear the input or dismiss delete confirmation after success
- map request-layer failures into a user-visible error path

### 2. [P2] Remove the stale `agentCheck` fallback end-to-end

Files:

- `functions/index.js:509-591`
- `firebase.json:79-91`
- `vite.config.ts:38-42`
- `functions/index.test.js:734-878`
- `src/lib/firebase.ts:101-107`

The plan deleted the REST read fallback, but `agentCheck` is still present in the codebase, still routed, still proxied in dev, and still covered by tests.

This endpoint now reflects the wrong product and data model:

- it still enforces creator-only access
- it still reads `reply`, `sources`, and `turnSummary` from the session doc
- the new schema stores terminal content on turn docs, not the session doc

In practice this is dead code at best and misleading code at worst.

Recommended fix:

- delete `agentCheck`
- remove `/api/agent/check` from `firebase.json`
- remove the dev proxy from `vite.config.ts`
- delete the `agentCheck` tests
- remove stale comments that still describe it as part of the transport model

### 3. [P2] `firestore-stream.ts` has become an orphaned transport layer

Files:

- `src/lib/firestore-stream.ts:142-357`
- `src/lib/chat-state.svelte.ts:25`
- `src/lib/components/restaurants/ChatThread.svelte:7`
- `src/lib/components/restaurants/StreamingProgress.svelte:2`

Production runtime no longer uses the transport helpers in `src/lib/firestore-stream.ts`. `chat-state.svelte.ts` now owns its own Firestore listeners and POST path. Current non-test imports from `firestore-stream.ts` are type-only.

That leaves a second transport implementation in the tree:

- extra listener logic
- extra timeout / permission-denied handling
- extra tests for code the app no longer executes

Recommended fix:

- delete the runtime helpers from `firestore-stream.ts`
- move shared types (`ChatSource`, `TimelineEvent`, `TurnCounts`, `TurnSummary`) into a small dedicated types module
- trim or remove the spec surface that only exists to preserve the orphaned implementation

### 4. [P3] SSR still boots the sidebar listener

Files:

- `src/lib/chat-state.svelte.ts:206-219`
- `src/lib/chat-state.svelte.ts:645-647`
- `src/lib/firebase.ts:19-28`

Reading `chatState.sessionsList` during SSR triggers `attachSidebarListener()`, which then tries to fetch `/__/firebase/init.json` in Node.

The build succeeds only because the error is swallowed:

- `npm run build` logs `[chat-state] sidebar listener bootstrap failed: TypeError: Failed to parse URL from /__/firebase/init.json`
- the warning is emitted during prerender, not because the app actually needs Firebase on the server

This is not breaking production behavior, but it is the wrong boundary and needless noise.

Recommended fix:

- add a server guard before lazy-attaching the sidebar listener
- or guard at the top of `attachSidebarListener()`
- keep Firebase/bootstrap work client-only

## What matched the plan

- Firestore is now the durable multi-turn source of truth.
- Session docs no longer carry terminal reply data.
- Turn docs are created transactionally on enqueue and keyed as `0001`, `0002`, ...
- Worker task payload carries creator `userId` plus `turnIdx`.
- Worker creates or reuses the ADK session under the creator UID.
- Watchdog flips the session and latest turn doc together in one transaction.
- Delete is hard-delete and creator-only.
- `chat-recovery.ts` and `ios-sse-workaround.ts` are gone.
- The reconnect banner path is gone.
- The sidebar is participant-scoped, not passive-read scoped.

## Simplify next

These are the highest-value simplifications after the four findings above:

1. Remove the dead `history` payload path.
   - `functions/index.js:226`
   - `functions/index.js:371`
   - `agent/worker_main.py:164`
   - `src/lib/chat-state.svelte.ts:542`
   - `src/lib/chat-state.svelte.ts:557`

   The current worker path does not use `history`, but the request, validation, task body, and tests still carry it around.

2. Collapse transport ownership into one place.
   - `chat-state.svelte.ts` should be the only runtime client transport layer.
   - shared types should live in a tiny module, not inside an unused transport helper.

3. Clean the SSR boundary.
   - no Firebase bootstrap during prerender
   - no swallowed server-side listener startup errors

4. Keep escalation features out unless production evidence demands them.
   - no `agentRead`
   - no `sessions_private/{sid}`
   - no mixed-version bridge code

Nothing in this review justifies adding more machinery.

## Verification run

Executed during this review:

- `npm run test` — PASS
- `cd functions && npm test` — PASS
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q` — PASS (`165 passed, 17 skipped`)
- `npm run check` — PASS
- `npm run lint` — PASS with existing warnings only
- `npm run build` — PASS, but still logs the SSR sidebar-bootstrap warning described above

Not executed here:

- `npm run test:rules`

Reason:

- local environment is missing Java, so the Firestore emulator suite could not be started in this session

## Open note

The implementation log notes one production observation worth reproducing deliberately: a contributor's sidebar entry reportedly appeared only after reload, not live. That may be a real runtime issue, but it is not proven by static source review alone. Treat it as a follow-up investigation, not yet as a confirmed code finding.
