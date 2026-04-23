# Final mechanics check on `server-stored-sessions-plan.md`

Review after the 2026-04-23 update that folded in the v2 verification findings. Scope: confirm the changes landed cleanly, walk the flows end-to-end, flag what still needs pinning before coding.

---

## 1. v2 findings — all folded in correctly

| Item from v2 verification                                                    | Status in updated plan                                                            |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| ADK `user_id` swap explicit at Runner and create_session                     | ✅ §8 worker "Explicitly:" block + §8 agentStream "Two UID roles"                 |
| `agentDelete` uses `recursiveDelete`, `timeoutSeconds: 120`, accepts orphans | ✅ §8 agentDelete "Operational posture" list                                      |
| SSR guardrail — `initializeFirestore` in lazy `getFirebase()`                | ✅ §7 "Implementation guardrail" + §9 firebase.ts                                 |
| Drop redundant `cacheSizeBytes: 100*1024*1024`                               | ✅ §7 config block no longer sets it                                              |
| Don't promise reconnect latency in UX                                        | ✅ Appendix C Test 4 reworded — "network-dependent and is not a product contract" |
| Name the smallest mitigation in §20 gates                                    | ✅ §20 row "narrow worker shim before a dual-write bridge"                        |

All six are in. Nothing went in that contradicts another part of the plan.

---

## 2. End-to-end mechanics walk — updated plan

### 2.1 New chat submit (first turn)

- agentStream transaction: no existing doc → `t.set(session, { userId: submitterUid, participants: [submitterUid], lastTurnIndex: 1, currentRunId, status: 'queued', updatedAt, createdAt, title: null, adkSessionId: null, ... })` and `t.set(turn('0001'), { turnIndex: 1, runId, userMessage, status: 'pending', createdAt })`.
- Cloud Task body: `{ sessionId, runId, turnIdx: 1, userId: session.userId, queryText, isFirstMessage: true, placeContext }`. On the first turn, `session.userId == submitterUid` — plan's wording "session's stored `userId`" covers this because the set runs in the same transaction.
- Worker takeover: reads session, verifies userId match (defense in depth), increments attempt, marks session `running`, marks turn `running`, both in one fenced transaction.
- Worker run: `_session_svc.create_session(user_id=session.userId)` on first turn; `_runner.run_async(user_id=session.userId, session_id=adk_session_id)` every turn.
- Worker terminal: fenced multi-doc write — session gets `{status, updatedAt, title}`, turn gets `{status, reply, sources, turnSummary, completedAt}`.

Clean. ✅

### 2.2 Follow-up turn from a different contributor (shared URL)

- agentStream transaction: `existing.userId = aliceUid` (creator), submitter is `bobUid`. No ownership rejection in new plan. One-in-flight check passes if prior turn terminal. Cap check: `existing.lastTurnIndex < 10`. Writes: `t.update(session, { currentRunId, status: 'queued', lastTurnIndex: N+1, updatedAt, participants: arrayUnion(bobUid), ... })` and `t.set(turn(N+1), { ..., userMessage: bob's message })`.
- Cloud Task body: `userId: aliceUid` (creator), not `bobUid`. This is the critical swap the v2 verification called out, now explicit in §8 change #9.
- Worker: `_runner.run_async(user_id=aliceUid)` — ADK's client-side `user_id` check passes because the session was created with `aliceUid`.

✅ The single most failure-prone path in the plan is correctly specified.

### 2.3 Refresh mid-run on shared device

- Cached session + turn + event data from IndexedDB paints immediately.
- Active session listener reattaches; turns listener delivers history; events listener attaches because `status ∈ {queued, running}`.
- Typewriter only animates turns whose `running → complete` transition is observed live in this browser.

✅ No recovery path, no polling, no visibility handler.

### 2.4 Watchdog flip on a stuck run

- Scan identifies stuck session by `queuedAt` / `lastHeartbeat` / `lastEventAt`.
- Race-safe transaction: re-reads session, verifies (status, currentRunId, thresholdField freshness), addresses turn doc via `session.lastTurnIndex`, updates both session + turn in the same transaction. Invariant holds: "turn at `lastTurnIndex` is the one for `currentRunId`" because agentStream atomically advances both together.

✅ Single-transaction flip is correct and implementable.

### 2.5 Creator delete

- agentDelete verifies `auth.uid === session.userId`, rejects with 403 otherwise.
- `db.recursiveDelete(db.doc('sessions/{sid}'))` reaps session + subcollections.
- Mid-run: worker's next `_fenced_update` fails with OwnershipLost (session doc gone → empty read → attempt/workerId mismatch). Worker logs + bails. A few event writes may land as orphans; reaped by 3-day events TTL.
- Function timeout 120 s is ~15× the worst-case workload. Safe.

✅ Simplest complete solution. Accepts the one bounded edge (orphan events) rather than adding cancel/drain machinery.

### 2.6 Cold-cache restrictive network

- Base: fromCache-aware load state. 10 s cache-only timeout → "Couldn't load this chat."
- Drill decides if minimal `agentRead(sid)` is needed. Plan is explicit that polling recovery does NOT come back.

✅ Correctly gated.

---

## 3. Minor items worth pinning before coding

None of these block implementation, but all are cheap clarifications that will save a review cycle.

### 3.1 `firestore_events.py` TTL value change

§11 says "3-day events TTL." Current constant at `agent/superextra_agent/firestore_events.py:14` is `EVENT_TTL_DAYS = 30`. §18 file inventory says `firestore_events.py` is "unchanged — event schema stays the same." The schema is unchanged, but the constant value is.

**Fix:** change §18 row to "modify — `EVENT_TTL_DAYS` → 3", or call it out explicitly in §11.

### 3.2 `firestore.indexes.json` TTL override on sessions.expiresAt

§5 says `expiresAt` is removed from sessions. The existing TTL policy in `firestore.indexes.json:38–44` (`fieldOverrides.sessions.expiresAt: ttl: true`) must be removed in the same deploy or the policy becomes an orphan rule. §18 lists `firestore.indexes.json` as "modify — add `sessions(participants, updatedAt)` composite" but doesn't mention the TTL override removal.

**Fix:** add to §18 row: "remove obsolete `sessions.expiresAt` TTL fieldOverride."

### 3.3 `turnIdx` wire format

Cloud Task body `turnIdx`: integer (1, 2, …) or zero-padded string (`"0001"`, `"0002"`, …). The Firestore doc key is zero-padded for lexical ordering. The `turnIndex` field on the turn doc is numeric. Two places, two types.

**Fix:** spell out once in §8: `turnIdx` travels as a plain integer in the task body and in the numeric `turnIndex` field; the worker formats it to `f"{n:04d}"` only when computing the doc path.

### 3.4 Turn `running` mark — inside takeover transaction or after?

§8 worker #3 says "Mark the active turn doc `status='running'` once takeover succeeds." Ambiguous between (a) inside the same takeover transaction as the session update, (b) in a separate fenced write after takeover.

(a) is atomic and never leaves turn at `pending` while session is `running`. (b) self-heals via Cloud Tasks retry if the worker crashes between them, but briefly shows inconsistent state to clients.

**Fix:** pick (a). One sentence: "Takeover is a two-doc fenced transaction: session gets the status/attempt/heartbeat update, turn gets `status='running'`."

### 3.5 Old localStorage cleanup (optional)

After the rewrite, `se_chats` and `se_chat` keys in localStorage are dead. Not a correctness bug — just ~tens of kB of user-browser disk per client indefinitely.

**Fix (optional, 5 lines):** on first run of the new `chat-state.svelte.ts`, best-effort `localStorage.removeItem('se_chats'); localStorage.removeItem('se_chat')`. Deletable a month after cutover.

Skip if the plan's "no deploy-window compatibility code" principle extends to this. Either is defensible.

### 3.6 Agent events listener detach condition

§10 says the events listener "only attaches while the latest turn is `queued` or `running`." Client needs to flip off the events listener on transition to terminal to avoid keeping the connection open past the run. That flip should key off the **turn** doc's status (terminal source per §9), not the session doc, since session and turn can be briefly inconsistent during the worker's terminal transaction.

**Fix:** clarify in §10 — events listener detaches when the turn doc for `currentRunId` reaches `complete` or `error`.

---

## 4. Weird-case creep check — nothing added

The user's concern: "right coverage without going into supporting weird cases."

Scan of the plan for defensive / weird-case handling that shouldn't be in v1:

- ✅ No client-side retry wrapper around listener.
- ✅ No fallback orchestration between listener and `agentRead`.
- ✅ No soft-delete, no trash view, no undo.
- ✅ No "touch on open" server endpoint.
- ✅ No dual-write bridge in the base plan.
- ✅ No mid-run cancel/drain protocol for delete.
- ✅ No participants cap.
- ✅ No ADK session cleanup on delete (accepted leak, cheap).
- ✅ No SDK re-subscribe on visibility change.

The plan is disciplined about not adding defensive layers. Every "weird case" in §16 is either mitigated by an existing scaffold (fencing, watchdog, TTL) or explicitly accepted.

---

## 5. Bottom line

The updated plan is implementation-ready. The six v2 findings are integrated correctly, the mechanics hold up under end-to-end walk, and nothing weird has crept in.

The six items in §3 above are cheap clarifications — fold them in during the implementation commit, not as separate plan revisions. None changes architecture or scope.

Green to start.
