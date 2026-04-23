# Superextra Chat — Server-stored Sessions Rearchitecture

A rearchitecture of how chat conversations are stored, transported, and accessed, with the goals of:

- making chats portable across devices via their URL
- letting any URL-holder read and continue a chat
- collapsing the current split between browser local storage and the cloud into a single source of truth
- removing the reconnect / retry / recovery machinery that exists only because chat state is split across multiple stores

This document is the implementation plan. It reflects the decisions that will actually be built. There are no alternative branches left open in this version.

---

## 1. Context

### Today's situation

Superextra is a restaurant-intelligence chat product. A user types a research question, the agent runs a multi-step research pipeline for 1–6 minutes, streams a play-by-play of its activity, then returns a structured answer with sources.

The current chat data lives in three places that do not fully agree with each other:

- The browser's local storage holds the conversation list and the full multi-turn transcript.
- Firestore holds the operational metadata and the latest turn's terminal output.
- Vertex AI Agent Engine sessions hold the agent's internal memory.

That split is the source of most of the accidental complexity in the current system:

- Chat URLs are device-bound because the browser-local transcript is the real history.
- Refreshing mid-research still needs special recovery handling.
- There is extra code for read fallbacks, runId deduplication, visibility handling, and local-storage synchronization that exists only because there is no single durable chat store.

### What we want

A single product story:

> Every chat has a URL. The URL is the chat. Anyone with the URL can read or continue. Chats live in the cloud and last until deleted. They work the same on every device.

The implementation should match that story directly.

The only part of that story still gated by targeted verification is the cold-cache restrictive-network case in §15 and §20. Everything else in this plan implements it directly.

### What we're betting on

The simplifying bet behind this rearchitecture is:

> the cleanest chat model is capability-URL access with one cloud source of truth

That means:

- no owner-vs-visitor UI split
- no share tokens
- no read-only sharing mode
- no local-storage truth layer

Operational guard rails stay in place:

- per-IP rate limiting
- per-UID rate limiting
- one in-flight turn per chat
- 10 turns per chat total
- worker fencing, heartbeats, and watchdog sweeps

### Out of scope

- Real user accounts / sign-in
- Cross-device portability for the same human's sidebar without the URL
- Explicit Share button
- Share-link revocation, expiry, password protection, or private/public toggle
- Pre-launch data migration
- Soft-delete or undo for deletion

---

## 2. Goals and objectives

### User-experience goals

1. **Smooth, always-there behavior.** Open a chat URL, refresh it, switch away and back, and the chat is still there without visible reconnect controls in normal use.
2. **Cross-device URL portability.** Start on one device, continue on another, with the full multi-turn history available.
3. **Sharing by URL alone.** Anyone with the URL can read and continue.
4. **Uneventful reloads during research.** Refreshing mid-query should reconnect to the current turn and live activity feed without manual intervention.
5. **Permanent retention.** Chats persist until deleted.

### Engineering goals

1. **One source of truth: Firestore.** Browser storage becomes cache only, not a durable chat store.
2. **Delete the connection-lifecycle machinery.** No polling recovery module, no reply dedup layer, no manual visibility/reconnect flow.
3. **One rendering path.** The same route, same components, same data model for creator and visitor.
4. **Single decisive implementation.** No standing compatibility write layer by default, no long compatibility window, and no deleted modules kept around in reduced form.

### Constraints

- Preserve the live activity-timeline UX.
- Preserve the current worker reliability scaffolding: takeover, fencing, heartbeats, watchdog.
- Keep anonymous Firebase Auth for v1.

### Success criteria

- The "Reconnecting…", "Try again", and "Could not reach the server" surfaces are removed from normal chat use.
- Opening a chat URL on any device shows the full conversation history stored in Firestore on standard networks. The restrictive-network case is resolved by the decision gate in §20 before ship.
- Refreshing during a running query resumes into the live activity feed and eventual answer.
- All four current test suites pass after the rewrite, with tests rewritten for the new model.
- The frontend chat/recovery layer shrinks materially overall, even after adding the new Firestore listeners and load-state handling.

---

## 3. Product story

### What changes for the user

Almost nothing changes visually. The chat still looks and behaves like Superextra. The difference is at the edges:

- **A URL is now genuinely a chat.** Bookmark it, open it on another device, or send it to a colleague.
- **Refreshing during research is fine.** The page reconnects to the current session and activity feed.
- **Switching tabs and coming back is fine.** There is no manual reconnect UI.
- **The sidebar shows every chat this browser has contributed to.** Started here or replied here, it shows up here.
- **Chats stay until deleted.**

One important behavior is explicit in this version:

- **If a browser only views a shared chat and never contributes, that chat does not appear in that browser's sidebar.** Bookmark the URL or send one reply to pin it to the sidebar.

### What stays the same

- The agent pipeline
- The activity timeline
- The markdown answer rendering
- Source pills
- The post-completion "Worked for X" summary
- The overall look and mobile behavior

### What this version does not add

- No real sign-in
- No explicit Share button
- No private/public toggle
- No read-only share mode

---

## 4. Architecture overview

### High level

The cloud becomes the only durable home for chats. The browser is a live view of Firestore, backed by the Firestore SDK's persistent local cache.

Each chat lives in three places in Firestore:

```text
sessions/{sid}                    ← lightweight metadata + operational state
  ├── turns/{turnIdx}             ← one document per user turn / agent answer
  └── events/{eventId}            ← live activity timeline, auto-cleaned
```

Each browser uses four live Firestore reads when a chat is active:

```text
sidebar listener         → chats this browser has contributed to
active session listener  → metadata and run state for chat X
active turns listener    → the full ordered turn history for chat X
active events listener   → live activity rows for chat X while the latest turn is in flight
```

The `participants` array has one purpose:

- add a UID on turn submit
- never add a UID on passive read

There is no server-side touch-on-open endpoint.

### What stays unchanged

- The agent pipeline in `agent/superextra_agent/`
- The Cloud Tasks → private Cloud Run worker topology
- Worker takeover, fencing, heartbeats, and watchdog
- The event schema for the live activity timeline

### What changes

- Firestore becomes the durable source of truth for the full multi-turn transcript.
- `agentStream` appends a turn record instead of only updating session-level terminal fields.
- The worker writes the terminal answer to the turn document instead of the session document.
- The frontend reads Firestore listeners directly instead of loading and syncing browser-local conversations.
- Access changes from "creator-only read + continue" to "any signed-in visitor with the URL can read and continue," while delete stays creator-only.

### What's deleted entirely

- The browser-local chat store and its migration/sync helpers
- The REST read fallback path (`chat-recovery.ts` and the read fallback Cloud Function)
- The runId-based reply deduplication layer
- `src/lib/ios-sse-workaround.ts`
- The reconnect banner
- The transient retry button path tied to reconnect/recovery logic
- First-snapshot timeout as a trigger for a separate read path

---

## 5. Data model

### `sessions/{sid}` — chat metadata

This document holds lightweight metadata and operational state only. User message text, replies, sources, and turn summaries live on per-turn documents.

| Field                                        | Type             | Purpose                                                                                                                                   |
| -------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `userId`                                     | string           | Anonymous-auth UID of the original creator. Preserved for Vertex Agent Engine session ownership. Not a read/write permission gate.        |
| `participants`                               | array of strings | Every anon-auth UID that has contributed at least one turn. Used by the sidebar query. No separate hard cap.                              |
| `title`                                      | string \| null   | Generated on the first turn.                                                                                                              |
| `placeContext`                               | object \| null   | Place context attached to the chat.                                                                                                       |
| `status`                                     | string           | `queued` \| `running` \| `complete` \| `error` — state of the latest run.                                                                 |
| `currentRunId`                               | string           | Run ID of the latest or in-flight turn.                                                                                                   |
| `currentAttempt`                             | number           | Cloud Tasks retry attempt for `currentRunId`.                                                                                             |
| `currentWorkerId`                            | string \| null   | Worker instance currently fencing writes for `currentRunId`.                                                                              |
| `lastTurnIndex`                              | number           | Highest appended turn index. Used to allocate the next turn and enforce the shared 10-turn cap.                                           |
| `adkSessionId`                               | string \| null   | Vertex Agent Engine session ID.                                                                                                           |
| `createdAt`                                  | timestamp        | When the chat was created.                                                                                                                |
| `updatedAt`                                  | timestamp        | Bumped on enqueue and on terminal writes (`complete` or `error`) so the sidebar orders by most recent touch, not only by completion time. |
| `queuedAt` / `lastHeartbeat` / `lastEventAt` | timestamps       | Watchdog liveness fields.                                                                                                                 |
| `error`                                      | string \| null   | Latest terminal error reason.                                                                                                             |
| `reply` / `sources` / `turnSummary`          | removed          | Terminal content moves to turn docs.                                                                                                      |
| `expiresAt`                                  | removed          | No automatic expiry on chats.                                                                                                             |

### `sessions/{sid}/turns/{turnIdx}` — one document per turn

Each turn document is keyed by a monotonically increasing zero-padded index (`0001`, `0002`, …) so lexical order matches chronological order.

| Field         | Type              | Purpose                                                         |
| ------------- | ----------------- | --------------------------------------------------------------- |
| `turnIndex`   | number            | Numeric mirror of the document ID.                              |
| `runId`       | string            | Run ID for this turn.                                           |
| `userMessage` | string            | Raw user question text. Not the server-prefixed pipeline input. |
| `status`      | string            | `pending` \| `running` \| `complete` \| `error`.                |
| `reply`       | string \| null    | Final answer text.                                              |
| `sources`     | array \| null     | Source pills for the turn.                                      |
| `turnSummary` | object \| null    | Post-completion "Worked for X" summary.                         |
| `createdAt`   | timestamp         | When the user submitted the turn.                               |
| `completedAt` | timestamp \| null | When the turn reached terminal success.                         |
| `error`       | string \| null    | Turn-specific terminal error.                                   |

### `sessions/{sid}/events/{eventId}` — live activity timeline

This stays structurally the same as today:

- one document per timeline event
- same `type` / `data.kind` / `data.family` shape
- written by the worker during a run

The denormalized `userId` field on event docs becomes unused by rules after this change. It can stay in the event payload for now and be cleaned up later if desired.

### Index requirements

| Collection              | Fields                                               | Scope            | Used for               |
| ----------------------- | ---------------------------------------------------- | ---------------- | ---------------------- |
| `sessions`              | `participants` (array-contains), `updatedAt` (desc)  | COLLECTION       | Sidebar listener       |
| `sessions/{sid}/turns`  | `turnIndex`                                          | collection-local | Turn history listener  |
| `sessions/{sid}/events` | `runId` (asc), `attempt` (asc), `seqInAttempt` (asc) | collection-local | Live activity listener |

The existing collection-group `events(userId, runId, attempt, seqInAttempt)` index becomes unused after the client moves to per-session event queries. Remove it in a follow-up cleanup after the new path is verified live.

---

## 6. Security model

### Capability URL access

This formalizes the chat URL as a capability URL:

- possession of `sid` is the access credential
- `sid` remains `crypto.randomUUID()` — 122 bits of random entropy
- the realistic risk is URL leakage, not guessing

Mitigations:

- `Referrer-Policy: no-referrer` on the agent hosting target
- `X-Robots-Tag: noindex, nofollow`
- no third-party scripts on the chat route

### Firestore security rules

```text
match /sessions/{sid} {
  allow get: if request.auth != null;

  allow list: if request.auth != null
              && request.auth.uid in resource.data.participants;

  allow write: if false;

  match /turns/{turnId} {
    allow read: if request.auth != null;
    allow write: if false;
  }

  match /events/{eventId} {
    allow read: if request.auth != null;
    allow write: if false;
  }
}
```

Three important properties:

- `get` on a session, turn, or event path is open to any signed-in visitor.
- `list` on `sessions` is constrained to chats the current browser has contributed to.
- All writes stay server-only through Cloud Functions and the worker.

### Delete

Chats are hard-deleted, but only by the original creator.

`agentDelete` accepts a `sid`, requires a Firebase ID token, and deletes:

- `sessions/{sid}`
- `sessions/{sid}/turns/*`
- `sessions/{sid}/events/*`

It returns `403` unless `request.auth.uid === session.userId`.

There is no soft-delete or undo window in this version.

### Write authorization

`agentStream` no longer rejects non-creator follow-ups. Any signed-in visitor with the URL may submit a new turn.

The session's stored `userId` is still preserved because the worker uses it for Vertex Agent Engine session ownership. New contributors add their own UID to `participants`, but the worker continues the shared Agent Engine session under the chat creator's stored `userId`.

### Rate limiting and abuse bounds

Three guards stay in place:

1. **Per-IP rate limit** on `agentStream`
2. **10-turn hard cap per chat**, shared across all contributors
3. **One in-flight turn per chat**

There is no separate cap on the `participants` array.

---

## 7. Connection model and UX smoothness

### Firestore SDK configuration

The browser uses the Firestore Web SDK with persistent local cache enabled:

```ts
const db = initializeFirestore(app, {
	localCache: persistentLocalCache({
		tabManager: persistentMultipleTabManager()
	})
});
```

This enables:

- IndexedDB-backed cache for previously loaded chat data
- multi-tab coordination within the same browser profile
- automatic listener resumption after offline → online transitions

Listener resumption after reconnect is automatic. No manual re-subscribe flow is needed. This was verified in the 2026-04-23 smoke test in Appendix C.

Implementation guardrail:

- keep `initializeFirestore(...)` inside the lazy async `getFirebase()` path
- do not hoist it to module scope, because this app prerenders and `persistentMultipleTabManager()` depends on browser-only APIs such as `window` and IndexedDB

### Cold cache on a blocked network

One Firestore SDK behavior is load-bearing for the frontend state design:

> If the client cannot reach `firestore.googleapis.com` and has no cached copy of the requested document, `onSnapshot` can emit one immediate cached snapshot with `fromCache: true` and `exists(): false`, then hang indefinitely without a server-confirmed result.

That means a first cached miss is **not** enough to conclude "chat not found."

The chat load state must distinguish:

- **cache-only, not yet confirmed**
- **server-confirmed missing**
- **loaded**

The UI rule is:

- after 10 seconds with only cache-only snapshots and no server confirmation, leave the indefinite loading state and take the restrictive-network branch chosen in §20:
  - base implementation: render "Couldn't load this chat"
  - if the restrictive-network drill fails: trigger one minimal `agentRead(sid)` fetch instead of restoring polling recovery

This load-state split stays either way. Even if a minimal `agentRead` endpoint is added later, the client should not eagerly hit it on every cold open.

### What disappears from the UI

The following surfaces are removed:

| UI surface today                              | After   |
| --------------------------------------------- | ------- |
| Reconnecting banner                           | removed |
| Manual retry path for transient read failures | removed |
| Browser-local conversation restoration        | removed |
| Visibility-change reconnect handling          | removed |

### What the user sees instead

- Previously loaded chats paint from cache immediately.
- Live listeners catch up from the server in the background.
- Refreshing during a run reattaches to the same session and current turn.
- Shared URLs behave the same as creator URLs.

### Refresh during research

The refresh path becomes:

1. Browser reloads.
2. Cached session/turn/event data renders immediately if present.
3. Live listeners reconnect.
4. Any missing activity rows or the final answer flow in.

No separate recovery path exists.

### iOS / mobile backgrounding

The old manual visibility workaround is removed.

The Firestore listener itself survives the offline → online transition without manual re-subscribe. Appendix C includes the smoke test that verified this behavior before locking that decision.

---

## 8. Backend changes

### `agentStream` Cloud Function (`functions/index.js`)

Changes:

1. Remove the creator-only ownership check.
2. Keep the one-in-flight guard per chat.
3. Treat a missing `lastTurnIndex` as `0`, so the first persisted turn is `0001`.
4. Read `lastTurnIndex` and reject if the next turn would exceed the shared 10-turn cap.
5. Add the submitting UID to `participants` with `FieldValue.arrayUnion(...)`.
6. Create `sessions/{sid}/turns/{turnIdx}` in the same transaction that updates the session doc.
7. Increment `lastTurnIndex`.
8. Set `updatedAt: serverTimestamp()` in that same transaction so the sidebar reflects submit-time recency.
9. Pass both `turnIdx` and the session's stored `userId` into the Cloud Task body, not the request-time UID.

Two UID roles are now explicit:

- the **submitter UID** from the request token is used for rate limiting and `participants`
- the **creator UID** stored on `session.userId` is what gets passed to the worker for Vertex Agent Engine session ownership

The new submit path writes the new schema directly.

### `agentCheck` Cloud Function — DELETED

The old polling recovery endpoint is removed.

The new client uses:

- Firestore listeners
- persistent local cache
- the fromCache-aware load state described in §7

Base implementation has no replacement read endpoint.

If the restrictive-network validation in §15 fails, the only allowed addition is a minimal one-shot `agentRead(sid)` endpoint that returns the session doc plus persisted turns. Do not reintroduce polling recovery.

### `agentDelete` Cloud Function — NEW

Small new endpoint:

- `POST { sid }`
- requires a Firebase ID token
- verifies `request.auth.uid === session.userId`
- uses `db.recursiveDelete(db.doc('sessions/{sid}'))`
- hard-deletes the session doc and both subcollections
- returns `200` on success, `403` for non-creators, and `404` if the chat does not exist

Operational posture:

- deploy with `timeoutSeconds: 120`
- accept that a creator deleting mid-run may leave orphan event docs briefly if the worker is still writing
- those orphan event docs are bounded by the 3-day events TTL
- log `recursiveDelete` failures; do not add cancel / drain coordination in v1

### Worker (`agent/worker_main.py`)

Changes:

1. Keep using the session's stored `userId` for Vertex Agent Engine calls.
2. Expect `turnIdx` in the task body and address the turn doc directly by that index.
3. Mark the active turn doc `status='running'` once takeover succeeds.
4. On success, write `reply`, `sources`, `turnSummary`, `completedAt`, and `status='complete'` to the turn doc.
5. Update the session doc's latest-run metadata in the same fenced transactional write: `status`, `updatedAt`, and `title` on the first turn.
6. On terminal error, write the error to both the session doc and the in-flight turn doc, and bump the session doc's `updatedAt`.

Explicitly:

- on the first turn, `_session_svc.create_session(user_id=...)` receives the creator UID
- on every turn, `_runner.run_async(user_id=...)` receives that same creator UID, never the follow-up submitter UID
- the Cloud Task body is the transport for that creator UID from `agentStream` into the worker

There is no session-level terminal-content compatibility write and no deploy-window compatibility shim in the base implementation. The mixed-version drill in §15 decides whether any temporary mitigation is needed before cutover.

### Watchdog (`functions/watchdog.js`)

The watchdog logic stays the same structurally:

- `queuedAt`
- `lastHeartbeat`
- `lastEventAt`

When it flips a stuck run to `status='error'`, it also bumps the session doc's `updatedAt` and flips the in-flight turn doc to `status='error'` in the same transaction. The watchdog should re-verify the same race-safety predicates before writing either document.

---

## 9. Frontend changes

### `src/lib/firebase.ts`

Modify to initialize Firestore with `persistentLocalCache(...)`.

Keep that initialization inside the existing lazy async `getFirebase()` helper. Do not move it to module scope.

### `src/lib/firestore-stream.ts`

Simplify the stream helper:

- drop the `userId` filter
- scope events to `sessions/{sid}/events`
- move terminal detection from the session-doc listener to the turns listener

The turns listener becomes the terminal source for answer rendering.

### `src/lib/chat-state.svelte.ts`

Major rewrite.

Delete:

- the browser-local conversation store
- `persist()` / `syncCurrentToList()`
- `loadConversation()`
- `resumeIfInFlight()`
- the read fallback path
- runId-based reply dedup scaffolding
- manual visibility / return handling
- the `Conversation` interface and storage constants

Add:

- sidebar listener state: `sessionsList`
- active session listener
- active turns listener
- active events listener for the in-flight run
- `startNewChat(query, place)`
- `sendFollowUp(message)`
- `deleteSession(sid)`
- `canDelete` derived from `session.userId === currentUid`
- the fromCache-aware initial load state described in §7

Net effect:

- less code overall
- one Firestore-driven state model
- no browser-local truth layer

### `src/lib/chat-recovery.ts` — DELETE

Delete outright.

### `src/lib/ios-sse-workaround.ts` — DELETE

Delete outright.

### `src/routes/agent/chat/+page.svelte`

Modify:

- simplify the `?sid` path to `chatState.selectSession(sid)`
- delete the visibility-change listener from `onMount`
- delete the `chatState.handleReturn(...)` call path
- read the sidebar from `chatState.sessionsList`
- only show the delete action when `chatState.canDelete` is true
- call `chatState.deleteSession(...)` from the delete UI

### `src/lib/components/restaurants/ChatThread.svelte`

Modify:

- remove the amber reconnect banner block

### `src/lib/components/Navbar.svelte`

Modify:

- change the minimal-navbar chat count from `chatState.conversations.length` to `chatState.sessionsList.length`

This is required because `/agent` uses the minimal navbar and still displays a chat badge.

### `firebase.json`

Modify:

- add the agent-target rewrite for `/api/agent/delete`
- remove the obsolete read-fallback rewrite

### `vite.config.ts`

Modify:

- add the dev proxy for `/api/agent/delete`
- remove the obsolete read-fallback proxy

### Summary of frontend/config changes

| File                                               | Action                                                                  |
| -------------------------------------------------- | ----------------------------------------------------------------------- |
| `src/lib/firebase.ts`                              | modify — persistent local cache config                                  |
| `src/lib/firestore-stream.ts`                      | modify — scoped events + turns terminal source                          |
| `src/lib/chat-state.svelte.ts`                     | major rewrite — Firestore-driven state                                  |
| `src/lib/chat-recovery.ts`                         | delete                                                                  |
| `src/lib/ios-sse-workaround.ts`                    | delete                                                                  |
| `src/routes/agent/chat/+page.svelte`               | modify — simpler mount flow, sidebar source, and creator-only delete UI |
| `src/lib/components/restaurants/ChatThread.svelte` | modify — remove reconnect banner                                        |
| `src/lib/components/Navbar.svelte`                 | modify — use `sessionsList.length`                                      |
| `firebase.json`                                    | modify — add delete rewrite, remove obsolete read rewrite               |
| `vite.config.ts`                                   | modify — add delete proxy, remove obsolete read proxy                   |

Measured net change is expected to land around **-350 to -450 lines** overall across the frontend chat/recovery layer and route/config glue.

---

## 10. Activity timeline

The activity timeline stays conceptually the same.

What changes:

- the event listener becomes `sessions/{sid}/events`
- it only attaches while the latest turn is `queued` or `running`
- shared visitors see the same live timeline as the creator

What does not change:

- the event schema
- the timeline rendering
- the drafting → typewriter handoff for turns observed live in the current browser

One small rendering rule becomes explicit:

- turns that are already `complete` on initial load render immediately as historical text
- the typewriter animation only runs for `running → complete` transitions observed by the current browser

---

## 11. Lifecycle and retention

Chats persist until deleted.

There is no automatic expiry on:

- session docs
- turn docs

The exception is the events subcollection:

- keep a 3-day Firestore TTL
- events are operational artifacts, not permanent transcript data

Failed chats are not auto-cleaned. Users delete them manually if needed.

---

## 12. Privacy implications

The privacy posture changes in one important way:

- the full multi-turn transcript is now durably stored in Firestore

The privacy policy update must state:

- every question and every reply is stored until deletion
- anyone with the chat URL can read and continue
- chat URLs should be treated like sensitive document links
- anonymous Firebase identifiers are stored alongside chats:
  - the original creator UID (`userId`)
  - every contributor UID (`participants`)

These identifiers are not personally identifying on their own, but they are readable by anyone with the chat URL.

This copy lands in the same release as the rules change.

---

## 13. Migration / cutover

Per product decision:

- clean slate
- existing Firestore sessions are wiped before launch
- existing browser-local conversation state becomes inert

Orphaned Vertex Agent Engine sessions can be left alone initially. They are cheap and can be cleaned later if needed.

---

## 14. Rollout sequence

The actual deploy topology is:

1. **Add the new Firestore composite index** for `sessions(participants array-contains, updatedAt desc)` and wait for it to become ACTIVE.
2. **`deploy-worker` runs first** in GitHub Actions and pushes the new Cloud Run worker.
3. **Firebase deploy runs next in the same workflow step** for `hosting,functions,firestore:rules,firestore:indexes`. That updates the frontend, Cloud Functions, rules, and indexes together.
4. **Operator step:** wipe existing Firestore sessions.

Between steps 2 and 3 there is a short mixed-version window, typically about 1–3 minutes, where:

- the new worker is live
- the old submit path may still be serving
- the old client JavaScript may still be running in open tabs

Accepted behavior in that window:

- a user who is already mid-query may see the old client stay in loading state
- after step 3, that user may need to refresh once and, in the worst case, resend the in-flight message once

This mixed window is accepted as-is for the base implementation. There is no compatibility write layer in the base plan. Before cutover, run the mixed-version drill in §15; only add a temporary mitigation if that drill shows a worse failure mode than the accepted refresh / resend behavior above.

---

## 15. Testing

### Automated suites

| Suite                      | Scope                                                                                                                                                                                                                                                                                   |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run test`             | Rewrite `chat-state.spec.ts` around the new listener model. Simplify `firestore-stream.spec.ts`. Delete `chat-recovery.spec.ts`. Add a Vitest case for the fromCache-aware loading state.                                                                                               |
| `cd functions && npm test` | Add tests for turn-doc creation, `turnIdx` propagation, submitter-vs-creator UID handling in the Cloud Task body, participants updates, `updatedAt` bump on enqueue, shared 10-turn cap, creator-only `agentDelete`, and one-in-flight enforcement. Remove the old read-fallback tests. |
| `npm run test:rules`       | Add cases for open `get`, participant-scoped session list queries, rejected `list` without `participants` membership, open signed-in reads on turns/events by path, and server-only writes.                                                                                             |
| `cd agent && pytest`       | Add worker tests for `turnIdx`-targeted writes, creator-UID ADK calls on shared follow-ups, turn lifecycle writes, and watchdog turn-error propagation inside the same transaction.                                                                                                     |

### Targeted validation before final cutover

These checks exist specifically to avoid shipping extra complexity unless the UX requires it.

1. **Restrictive-network read-path drill**
   - Use a fresh browser profile or cleared IndexedDB so the session is truly cold-cache.
   - Block `firestore.googleapis.com` while keeping `agent.superextra.ai` reachable.
   - Open a completed shared chat URL and a running shared chat URL.
   - If representative restrictive-network environments make completed shared chats unreadable, add one minimal `agentRead(sid)` endpoint that returns session + persisted turns once. Do not restore the old polling recovery loop.
2. **Mixed-version deploy drill**
   - Simulate the real deploy order: new worker first, old hosting/client still serving, then new hosting.
   - Exercise an in-flight turn started before hosting updates.
   - Keep the base no-compatibility plan only if the observed failure mode is limited to an already-open tab needing refresh and, at worst, one resend. If turns are silently lost in a way that exceeds that trade-off, add the smallest temporary mitigation from §20.
3. **Session-doc split drill**
   - Instrument snapshot callback counts and visible sidebar re-renders while 1, 5, and 10 chats are running with heartbeats enabled.
   - Keep operational fields on `sessions/{sid}` unless this produces visible resorting, jank, or clearly wasteful listener churn. Only then consider `sessions_private/{sid}` as a follow-up.

### Manual / Chrome verification

1. **Owner flow**: start a chat, observe the live activity feed, receive the answer, sources, and summary, and see the chat in the sidebar.
2. **Cross-device read**: open a completed chat URL in a fresh incognito window. The full transcript renders. The sidebar stays empty because this browser has not contributed yet.
3. **Cross-device continue**: send a follow-up from the incognito window. The new turn completes, and the chat now appears in that browser's sidebar.
4. **Refresh mid-research**: refresh a running chat and verify the page reconnects to the current run and live activity feed.
5. **Mid-research shared viewing**: open the URL on a second device while a run is in progress and verify the second device sees the live timeline.
6. **Mobile backgrounding**: on iOS Safari, start a run, background the tab, return, and verify the session resumes without a manual reconnect flow.
7. **Delete as creator**: delete a chat, verify it disappears from the sidebar, and verify reopening the URL shows the missing-chat state.
8. **Delete as contributor**: open the same shared chat from a second browser identity, verify the delete affordance is absent there, and verify a direct `agentDelete` call returns `403`.
9. **10-turn cap**: submit 11 total turns across one or more contributors and verify the 11th is rejected.
10. **Headers**: `curl -I` verifies `Referrer-Policy: no-referrer` and `X-Robots-Tag: noindex, nofollow`.

### Final smoke

Before ship:

- `npm run test`
- `npm run test:rules`
- `cd functions && npm test`
- `cd agent && pytest`
- `npm run lint`
- `npm run check`

---

## 16. Risks and known concerns

### Real risks

1. **Worker multi-document fencing.** Session and turn writes must stay transactionally consistent.
2. **Sidebar listener cost.** Users with many contributed chats will keep a live `sessions` listener ordered by `updatedAt`.
3. **Anonymous-auth boundary remains visible.** The URL carries the cross-device handle; the sidebar does not follow the human across browsers.
4. **Creator-only delete depends on anon-auth continuity.** The safer delete model means creators who lose their original anonymous UID lose delete access from that browser.

### Smaller concerns

5. **Cold cache on a blocked network.** The smoke test in Appendix C showed the exact problematic shape: one immediate cached snapshot with `fromCache: true` and `exists(): false`, then an indefinite hang. The fromCache-aware loading state is required either way. The restrictive-network drill in §15 decides whether that timeout branch can stay UI-only or needs a minimal `agentRead`.
6. **Mixed-version deploy window remains intentionally thin.** The base plan accepts a refresh / resend trade-off during the worker-first deploy window. The drill in §15 decides whether even that small amount of compatibility code is justified.
7. **Mid-run delete is not fully coordinated.** A creator deleting an actively running chat may leave orphan event docs briefly before TTL reaps them.
8. **The 10-turn cap may be limiting for heavy collaborative threads.** If usage proves otherwise, raise it later.

### Deliberately not mitigated in v1

- Per-IP rate limiting remains in-memory across Cloud Function instances.
- There is no cap on the `participants` array.
- Vertex Agent Engine sessions are not cleaned up on delete.
- Mid-run delete does not try to cancel or drain the worker before `recursiveDelete`.
- There is no soft-delete / undo path for hard deletes.

---

## 17. What's deferred

- Real user accounts and sign-in
- Cross-device sidebar portability for the same human without the URL
- Explicit Share button
- Share-link revocation, expiry, or private/public controls
- Distinct read-only sharing
- Splitting `sessions/{sid}` into public and private documents unless the listener-churn drill justifies it
- Stamping turns with writer identity for provenance UI
- Soft-delete / undo window for deletion
- Pre-launch data migration

---

## 18. Files affected

### Frontend

| File                                               | Action                                                                                                  |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `src/lib/firebase.ts`                              | modify — add persistent cache config inside lazy `getFirebase()`                                        |
| `src/lib/firestore-stream.ts`                      | modify — move to per-session events and turns terminal source                                           |
| `src/lib/chat-state.svelte.ts`                     | major rewrite — Firestore-driven session/turn state                                                     |
| `src/lib/chat-recovery.ts`                         | delete                                                                                                  |
| `src/lib/ios-sse-workaround.ts`                    | delete                                                                                                  |
| `src/routes/agent/chat/+page.svelte`               | modify — simpler route boot, no visibility handler, sidebar from `sessionsList`, creator-only delete UI |
| `src/lib/components/restaurants/ChatThread.svelte` | modify — remove reconnect banner                                                                        |
| `src/lib/components/Navbar.svelte`                 | modify — use `sessionsList.length`                                                                      |

### Backend

| File                                         | Action                                                                                                  |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `functions/index.js`                         | modify — new session/turn write path, creator-UID task payload, and `agentDelete` via `recursiveDelete` |
| `functions/watchdog.js`                      | modify — propagate stuck-run errors to the in-flight turn doc in the same transaction                   |
| `agent/worker_main.py`                       | modify — turn-doc lifecycle, `turnIdx` targeting, session+turn terminal writes                          |
| `agent/superextra_agent/firestore_events.py` | unchanged — event schema stays the same                                                                 |
| `firestore.rules`                            | modify — open signed-in gets plus participant-scoped session list                                       |
| `firestore.indexes.json`                     | modify — add `sessions(participants, updatedAt)` composite                                              |

### Config / routing

| File             | Action                                                       |
| ---------------- | ------------------------------------------------------------ |
| `firebase.json`  | modify — add delete rewrite and remove obsolete read rewrite |
| `vite.config.ts` | modify — add delete proxy and remove obsolete read proxy     |

### Tests

| File                               | Action                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `src/lib/chat-state.spec.ts`       | major rewrite                                                                                                 |
| `src/lib/firestore-stream.spec.ts` | simplify                                                                                                      |
| `src/lib/chat-recovery.spec.ts`    | delete                                                                                                        |
| `functions/index.test.js`          | update for turn creation, `turnIdx`, `updatedAt`, creator-only delete, and removal of old read-fallback tests |
| `agent/tests/test_worker_main.py`  | extend for turn lifecycle, `turnIdx` writes, and watchdog turn-doc fencing                                    |
| Firestore rules emulator tests     | add session/turn/event read cases                                                                             |

### Documentation

| File                                     | Action                                                                 |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| `src/routes/privacy-policy/+page.svelte` | modify — disclose durable transcript storage and anonymous identifiers |
| `docs/deployment-gotchas.md`             | modify — remove stale local-storage/read-fallback assumptions          |
| `docs/shareable-sessions-plan.md`        | superseded by this plan; can be deleted in the implementation commit   |

---

## 19. Existing utilities to reuse

- `crypto.randomUUID()` for chat IDs and run IDs
- `ensureAnonAuth()` and `getFirebase()` in `src/lib/firebase.ts`
- `marked`, `splitChartSegments`, and `ChartBlock` for reply rendering
- `checkRateLimit(...)` in `functions/utils.js`
- the existing worker fencing / takeover transaction patterns
- `_strip_query_prefixes(...)` in `agent/worker_main.py` for title generation
- `FieldValue.arrayUnion`, server timestamps, and Firestore transactions

---

## 20. Locked-in decisions

| Question                             | Decision                                               | Rationale                                                                                                                   |
| ------------------------------------ | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Sidebar scope                        | contributed to, not merely opened                      | No touch-on-open endpoint in this version                                                                                   |
| Delete model                         | hard delete, creator-only                              | Removes the only destructive action from non-creators while keeping read + continue shared                                  |
| Turn cap                             | 10 turns total per chat, shared across contributors    | Bounds abuse on leaked URLs                                                                                                 |
| Participants cap                     | none                                                   | No separate cap beyond the shared 10-turn chat cap                                                                          |
| `updatedAt` semantics                | bump on enqueue and terminal write                     | Sidebar should reflect recent touch immediately                                                                             |
| Multi-turn durability                | yes, every turn persists to `turns/`                   | Cross-device continuation and durable transcript                                                                            |
| Chats expiry                         | none                                                   | Product wants permanent chat retention                                                                                      |
| Events expiry                        | 3 days                                                 | Operational artifacts only                                                                                                  |
| Existing data migration              | no                                                     | Clean slate on cutover                                                                                                      |
| Cold-cache blocked-network rendering | fromCache-aware load state with 10s cache-only timeout | Appendix C smoke test showed immediate cached miss + hang, and the UI must not treat the first cached miss as authoritative |
| iOS visibility workaround            | deleted                                                | Listener resumption after reconnect is automatic                                                                            |
| Operational fields location          | keep on `sessions/{sid}` in v1                         | Avoid a public/private doc split unless measured listener churn justifies it                                                |
| Mixed-version compatibility code     | none in the base implementation                        | Keep deploy-only complexity out unless the drill shows it is necessary                                                      |

### Decision gates before final cutover

| Question                        | Base plan                                                                  | Verification                                                                             | Escalation only if it fails                                                                                                       |
| ------------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Restrictive-network read path   | Firestore listeners + fromCache-aware timeout branch only                  | Cold-cache drill with Firestore blocked and app host reachable                           | Add one minimal `agentRead(sid)` fetch that returns session + persisted turns; do not restore polling `chat-recovery`             |
| Public/private session split    | Keep a single client-readable `sessions/{sid}` doc                         | Measure heartbeat/event listener churn and visible sidebar movement during running chats | Split to `sessions_private/{sid}` only if the churn is clearly user-visible or operationally wasteful                             |
| Mixed-version deploy mitigation | No bridge and no worker-side compatibility shim in the base implementation | Worker-first / hosting-second drill that exercises an in-flight turn                     | Add the smallest temporary mitigation that fixes the observed failure, preferring a narrow worker shim before a dual-write bridge |

---

## Appendix A — Why Firestore

Firestore is the right fit because it provides:

- browser-direct reads with Firebase Auth
- real-time listeners
- persistent local cache
- document/subcollection security rules
- TTL for the events collection

The project already depends on Firestore for the activity timeline. This refactor expands that role instead of introducing a new data system.

References:

- [Vertex AI Agent Engine sessions overview](https://cloud.google.com/agent-builder/agent-engine/sessions/overview)
- [Manage Agent Engine sessions via API](https://cloud.google.com/agent-builder/agent-engine/sessions/manage-sessions-api)
- [Firestore offline data](https://firebase.google.com/docs/firestore/manage-data/enable-offline)
- [W3C TAG capability URLs](https://www.w3.org/2001/tag/doc/capability-urls/)

---

## Appendix B — Estimated effort

Rough estimate for one senior engineer already familiar with the codebase:

- Backend: 3–4 days
- Firestore rules + indexes + privacy copy: 0.5 day
- Frontend rewrite: 4–5 days
- Test rewrites: 2–3 days
- E2E verification and polish: 2–3 days

Total: **12–15 working days**

---

## Appendix C — 2026-04-23 Firestore smoke tests

These smoke tests were run against production Firestore behavior before the plan was locked. They justify deleting the manual visibility/reconnect handler and they define the blocked-network behavior that the final read-path decision must handle.

### Test 1 — online listener, current rules, nonexistent doc

Finding:

- A listener on a nonexistent session doc under the current creator-only rules returned `permission-denied` in roughly 1.4 seconds.

Why it matters:

- Under the relaxed rules in this plan, that path becomes a normal missing-doc read instead of a permission-denied read.

### Test 2 — offline listener, cold cache, nonexistent doc

Finding:

- With a cold cache and the backend unreachable, the listener emitted one immediate cached snapshot with `fromCache: true` and `exists(): false` at about 18 ms, then hung indefinitely with no error and no server confirmation.

Why it matters:

- This exact behavior drives the fromCache-aware loading state in §7 and the cold-cache risk in §16.

### Test 3 — online permission-denied control path

Finding:

- Re-running the online denied-read path produced a clean error again in roughly 1.4 seconds.

Why it matters:

- It distinguishes the clean online error path from the offline cache-only hang in Test 2. The problematic behavior is specifically the cold-cache + unreachable-backend case, not a generic missing-doc case.

### Test 4 — listener created while offline, then network restored

Finding:

- A listener created while offline first emitted a cached snapshot almost immediately, then delivered a server-confirmed snapshot after reconnect without any manual re-subscribe.

Why it matters:

- This confirms the Firestore SDK resumes listeners automatically after reconnect, so the manual visibility / return workaround is not needed in the new architecture. Exact reconnect latency is network-dependent and is not a product contract in this plan.
