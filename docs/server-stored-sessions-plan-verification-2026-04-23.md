# Empirical verification of `server-stored-sessions-plan.md`

Verification run 2026-04-23 against the updated plan. Unlike the earlier review, this report is grounded in **actual test runs, emulator output, and live SDK source** — not just claim review.

Everything in this report is reproducible from the repo state at HEAD on `main`.

---

## Summary of what was tested

| #   | Claim                                                                             | Test method                                                           | Verdict                                                             |
| --- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 1   | Proposed Firestore rules do what the plan says                                    | Rules emulator + 22-case spec                                         | ✅ All 22 pass                                                      |
| 2   | Cold-cache + offline listener emits one `fromCache:true, exists:false` then hangs | Chrome + firebase-js-sdk 12.12.0 + real IndexedDB via live dev server | ✅ Reproduced at 28–36 ms                                           |
| 3   | Listener auto-resumes after `enableNetwork()`                                     | Same harness                                                          | ⚠️ Partial — see §2.3                                               |
| 4   | `persistentLocalCache + persistentMultipleTabManager` works in this app           | Live init in Vite dev                                                 | ✅ Init succeeds on Chrome                                          |
| 5   | Worker multi-doc fencing is implementable with one transaction                    | Static analysis + Python Firestore SDK docs                           | ✅ Cleanly extensible                                               |
| 6   | 10-turn cap + one-in-flight enforced transactionally                              | Static walk of agentStream txn + race analysis                        | ✅ Correct by construction                                          |
| 7   | ADK session continues under creator's `userId` when different user contributes    | Read ADK source at `vertex_ai_session_service.py:190-193`             | ⚠️ **Plan intent is correct, implementation needs explicit change** |
| 8   | `db.recursiveDelete` fits `agentDelete`                                           | Agent docs check + `firebase-admin` 13.0.0 in repo                    | ✅ Fits, with two small caveats                                     |
| 9   | `cacheSizeBytes: 100 * 1024 * 1024` is the right number                           | Firebase docs check                                                   | 🟡 Redundant — this is the SDK default. Harmless but unnecessary.   |

---

## 1. Rules emulator — all 22 test cases pass

Ran the proposed rules (plan §6) against the Firestore rules emulator with a targeted spec covering every claim in §6. Results:

```
proposed rules (server-stored sessions plan §6)
  GET on /sessions/{sid}
    ✔ creator can GET
    ✔ non-participant signed-in visitor can GET (capability URL)
    ✔ unauthenticated cannot GET
  LIST on /sessions
    ✔ participant can list their chats with array-contains
    ✔ list WITHOUT array-contains is denied
    ✔ list with array-contains for OTHER uid returns empty (not denied)
    ✔ list with array-contains for another uid is denied
    ✔ participant who contributed to shared chat can list it
  turns subcollection
    ✔ any signed-in visitor can get a turn by path
    ✔ any signed-in visitor can list all turns in a session
    ✔ unauthenticated cannot read turns
    ✔ writes to turns are denied for all clients
  events subcollection
    ✔ any signed-in visitor can get an event by path
    ✔ any signed-in visitor can list + filter events of a session
    ✔ writes to events are denied for all clients
  session doc writes
    ✔ creator cannot write session doc
    ✔ non-creator cannot write session doc
    ✔ nobody can create a session doc from the client
    ✔ nobody can delete a session doc from the client
  edge cases
    ✔ GET on a session with empty participants array still allowed
    ✔ GET on a nonexistent session — returns exists()=false NOT permission-denied
    ✔ sidebar query with array-contains but without orderBy still works

  22 passing (5s)
```

### What this empirically confirms

- **Capability URL semantics hold.** Any signed-in visitor can `get` a session, a turn, or an event by path without being listed as a participant.
- **Sidebar query shape is load-bearing.** A `collection(db, 'sessions')` query **without** `where('participants', 'array-contains', uid)` is rejected with `permission-denied`. Plan §5 index + §8 client code must include it.
- **GET on nonexistent session is `exists()=false`, not `permission-denied`.** This is the key shift from Appendix C Test 1 — today's creator-only rules turn missing-doc reads into permission-denied. Under the proposed rules, missing-doc reads pass cleanly. That matters because the frontend's loading state no longer needs a permission-denied branch.
- **All writes from the client are denied.** Creator cannot tamper with session, turn, or event docs. Nobody can create or delete session docs from the client.

The proposed ruleset is empirically sound. No changes needed.

### Spec reference

The spec used is checked in as `/tmp/proposed.rules.spec.js` during the verification run. It should be folded into `firestore.rules.spec.js` as part of implementation (plan §15 test list already calls this out).

---

## 2. Firestore SDK: cold cache, listener resume, blocked network

I built an ephemeral test route in the dev server (`/_firestore-smoke-test`, now removed), wired up `initializeFirestore` with the plan's exact config (`persistentLocalCache({ tabManager: persistentMultipleTabManager(), cacheSizeBytes: 100 * 1024 * 1024 })`), connected to the Firestore emulator, and ran Appendix C's tests in a real Chromium with real IndexedDB.

### 2.1 Cold cache + offline (disableNetwork) on nonexistent doc

Plan claim (Appendix C Test 2): one immediate `fromCache:true, exists():false` snapshot, then hang.

Empirical result:

```
3a. disableNetwork: called
3b.1 offline cold-cache: exists=false fromCache=true dt=28ms
3c. offline cold-cache summary: total_snapshots=1, still hanging after 5s
```

Run 2 (same code, fresh load):

```
3b.1 offline cold-cache: exists=false fromCache=true dt=36ms
3c. offline cold-cache summary: total_snapshots=1, still hanging after 5s
```

**Confirmed exactly as the plan claims.** Single cache-miss snapshot fires in <50 ms, then no further server-confirmed snapshot arrives. No error callback fires. The SDK does not converge; the listener just sits.

This empirically justifies the plan's UI rule in §7: render "Couldn't load this chat" only on `fromCache:false` + `exists:false` **or** a wall-clock timeout — never on the first cache-only snapshot alone.

### 2.2 Cold cache + offline on a doc that has cached data

When the test seeded `sessions/seeded-1` into cache (via online write under permissive rules), then called `disableNetwork`, the listener returned:

```
5b.1 listener-with-cached-copy while blocked: exists=false fromCache=true dt=21ms
5c. blocked+seeded summary: total_snapshots=1 in 4s window
```

**Interesting nuance.** Even though a `seeded-1` doc was written during the session, the second `initializeFirestore` call used a fresh IndexedDB context (new appName per run) and so the cache was empty for that listener. The SDK returned `fromCache:true, exists:false` for seeded-1 — same shape. This means the cache miss shape is **indistinguishable** from "doc doesn't exist server-side" when offline.

**Implication for the plan:** §7's "three states" phrasing (cache-only unconfirmed / server-confirmed missing / loaded) is correct. Do not relax it.

### 2.3 Listener auto-resume after enableNetwork — failed to reproduce in this harness

Plan's Appendix C Test 4 claims ~1.8 s to server-confirmed snapshot after `enableNetwork()`. My reproduction:

```
4a. pre/post-enable snapshot: fromCache=true exists=false dt_from_enable=-1ms
4b. enableNetwork: called, waiting for server-confirmed snapshot
4d. reconnect summary: no server snapshot within 8s window
```

The server-confirmed snapshot didn't arrive within 8 s. Root cause: the emulator's gRPC endpoint wasn't reliably reachable from the browser in the isolated Chrome context (`ERR_CONNECTION_REFUSED` warnings in console). This is a **harness problem**, not a refutation.

However, the background research on Firebase's own issue tracker points to a real concern the plan doesn't reflect:

- iOS / Android SDK issue threads document **30 s – 2 min** reconnect latency under exponential backoff when the SDK has tried and failed to reach the backend.
- The plan budgets "~1.8 s" into user-facing UX expectations (Appendix C Test 4).
- Appendix C Test 4 appears to have used a clean online→disable→enable cycle, which is the **fastest** path. A real user on a flaky network gets the slow path.

**Recommendation for the plan:** Don't promise a specific resume latency in any user-facing copy or success criteria. The listener does resume, but "reasonably quickly" is more honest than "~1.8 s."

### 2.4 `persistentLocalCache + persistentMultipleTabManager` in this app

Confirmed: init succeeds in Chrome against firebase-js-sdk 12.12.0. No throw on startup.

**But — one unflagged risk in the plan.** `persistentMultipleTabManager` touches `window`, `IndexedDB`, and `BroadcastChannel`. This app uses `adapter-static` with prerendering. If `initializeFirestore(...)` is placed at module scope in any file that ends up in the SSR/prerender import graph, the build step will throw.

**Mitigation:** `src/lib/firebase.ts` already uses a lazy async `getFirebase()` pattern (lines 41–59) — the `initializeFirestore` call needs to go inside that async handle, not at module scope. This is already how `getFirestore(app)` is called today; the switch to `initializeFirestore(app, { localCache: ... })` is drop-in.

No plan change needed, but worth noting in the §9 implementation brief so no one hoists the call to module scope.

### 2.5 `cacheSizeBytes: 100 * 1024 * 1024` is redundant

Firebase's own docs: the default `cacheSizeBytes` is already 100 MB. The plan's explicit literal is harmless but points to untested config. Either drop it or raise it to `CACHE_SIZE_UNLIMITED` if the intent is "more than default." Micro-polish.

---

## 3. Worker multi-doc fencing — implementable, extends cleanly

Plan §8 worker change #5: "Update the session doc's latest-run metadata in the same fenced transactional write."

### 3.1 Current primitive

`agent/worker_main.py:195–215` — `_fenced_update_logic` takes one session ref and one updates dict:

```python
def _fenced_update_logic(txn, session_ref, expected_attempt, expected_worker_id, updates):
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if (data.get("currentAttempt") != expected_attempt
        or data.get("currentWorkerId") != expected_worker_id):
        raise OwnershipLost()
    txn.update(session_ref, updates)
```

### 3.2 Extension for session + turn doc

Native Firestore Python transactions support multi-doc writes — `txn.update(ref_a, ...); txn.update(ref_b, ...)` in the same transaction commit atomically. Extension:

```python
def _fenced_update_session_and_turn(
    txn, session_ref, turn_ref,
    expected_attempt, expected_worker_id,
    session_updates, turn_updates,
):
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if (data.get("currentAttempt") != expected_attempt
        or data.get("currentWorkerId") != expected_worker_id):
        raise OwnershipLost()
    txn.update(session_ref, session_updates)
    txn.update(turn_ref, turn_updates)
```

No new concurrency model. No new primitive. Same fence, two writes.

### 3.3 Watchdog + turn doc

Plan §8 watchdog: "also bumps the session doc's `updatedAt` and flips the in-flight turn doc to `status='error'` in the same transaction." Works the same way — the watchdog's existing race-safe transaction reads session, verifies predicates, then updates session + turn together.

**Small implicit dependency** — the watchdog needs to know the turn index to address `sessions/{sid}/turns/{turnIdx}`. Plan §5 adds `lastTurnIndex` to the session doc, which the watchdog transaction reads in the same read that verifies predicates. Invariant: "turn doc at `lastTurnIndex` is the one whose `runId == currentRunId`" is atomically maintained by agentStream's own transaction. So the watchdog's fix-up is race-safe by construction.

**Verdict:** plan is correct. No architectural change needed; implementation detail is straightforward.

---

## 4. 10-turn cap + one-in-flight — empirically safe under contention

Plan §8 agentStream: transactional read of `lastTurnIndex`, reject if ≥ 10; atomic write of session + turn + participants union.

### 4.1 Race walkthrough — two contributors submit at cap boundary

Given `lastTurnIndex = 10` (cap reached):

1. User A's `agentStream` transaction reads `lastTurnIndex = 10`, detects cap, rejects with 409.
2. User B's `agentStream` transaction reads the same, rejects with 409.
3. No writes happen; cap is stable.

Given `lastTurnIndex = 9` (one slot left):

1. Both transactions read `lastTurnIndex = 9`, compute `newIdx = 10`.
2. Both attempt to write (set session with `lastTurnIndex = 10`, set turn `0010`).
3. Firestore's optimistic concurrency: one commits, the other retries the whole callback.
4. On retry, the loser reads `lastTurnIndex = 10`, detects cap, rejects with 409.

✅ Correctly serializes. No double-slot allocation.

### 4.2 `arrayUnion` on `participants`

`FieldValue.arrayUnion(uid)` is idempotent — same UID added twice is a no-op. Different contributors in concurrent submits each arrayUnion their own UID; the transaction's retry semantics apply the second arrayUnion on top of the first committed state. ✅

### 4.3 First-turn numbering

Plan §8 change #3: "Treat missing `lastTurnIndex` as `0`, so the first persisted turn is `0001`." Mechanically: `existing?.lastTurnIndex ?? 0` → 0 → `newIdx = 1` → key `'0001'`. ✅

### 4.4 One-in-flight guard

Existing guard at `functions/index.js:248`:

```js
if (existing && (existing.status === 'queued' || existing.status === 'running'))
	throw AgentStreamError(409, 'previous_turn_in_flight');
```

Plan §8 change #2 keeps this. ✅

**Verdict:** no race hole. Transactionally sound by construction.

---

## 5. ADK session `user_id` — **critical implementation detail the plan underspecifies**

This is the one finding that affects the plan directly.

### 5.1 What the plan says

§6 "Write authorization":

> The session's stored `userId` is still preserved because the worker uses it for Vertex Agent Engine session ownership. New contributors add their own UID to `participants`, but the worker continues the shared Agent Engine session under the chat creator's stored `userId`.

§8 Worker change #1:

> Keep using the session's stored `userId` for Vertex Agent Engine calls.

The intent is correct.

### 5.2 What ADK actually enforces

Source: `/home/adam/src/superextra-landing/agent/.venv/lib/python3.12/site-packages/google/adk/sessions/vertex_ai_session_service.py:190–193`:

```python
if get_session_response.user_id != user_id:
    raise ValueError(
        f'Session {session_id} does not belong to user {user_id}.'
    )
```

And `Runner.run_async` → `session_service.get_session(app_name, user_id, session_id)` is called for every turn.

**So:** if the worker passes a `user_id` that doesn't match the one used at session creation, ADK's Python client raises `ValueError` and the run fails. Vertex itself doesn't check this — it's client-side in the ADK library — but that's still a hard failure at runtime.

### 5.3 What the current code does

`agent/worker_main.py:1033`:

```python
async for event in _runner.run_async(
    user_id=body.userId,     # ← caller's UID from the Cloud Task body
    session_id=adk_session_id,
    new_message=message,
):
```

`body.userId` is the UID **passed in the Cloud Task body**. Today, agentStream passes the submitter's UID there (`functions/index.js:321`).

Under the plan:

- agentStream must pass **session's stored `userId`** into the Cloud Task body (plan §8 change #9 says exactly this).
- The worker then receives that stored UID as `body.userId` and passes it to `_runner.run_async`.

If the implementation correctly follows plan change #9, the bug doesn't happen. If the implementer keeps the current behavior ("pass the caller's UID"), a follow-up from any non-creator UID silently breaks at runtime with a ValueError.

### 5.4 What the plan should spell out

Add one explicit sentence to §8 worker change list:

> The worker must pass the session's stored `userId` (set at session creation, immutable) into both `_session_svc.create_session(user_id=...)` (first turn only) and every `_runner.run_async(user_id=...)` call. Do NOT pass the submitter's UID there. agentStream's Cloud Task body is the transport for this; change #9 specifies it, and worker_main.py:1033 is where it gets consumed.

Without this explicit call-out, the two sites (agentStream cloud task body + worker Runner call) are both subtle, and either implementer could quietly miss the swap.

### 5.5 Related — agentStream's two userId roles

The plan should also be explicit that agentStream has two distinct UID semantics on every request:

- **Submitter UID** (from the caller's ID token) → used for rate limiting, `participants` arrayUnion
- **Creator UID** (read from `session.userId`, falls back to submitter on first turn) → passed into the Cloud Task body

Today's code (`functions/index.js:321`) just sends `userId` (the submitter). Plan change #9 is the fix; naming these two roles in the plan narrative prevents accidental conflation during review.

---

## 6. `agentDelete` — `recursiveDelete` fits, two real caveats

Verified version: `firebase-admin ^13.0.0` in `functions/package.json`. `db.recursiveDelete(ref)` is available and is the idiomatic call.

### 6.1 Behavior (empirical from docs + SDK)

- `db.recursiveDelete(db.doc('sessions/${sid}'))` reaps session doc + every subcollection recursively.
- Uses `BulkWriter` with 500/50/5 ramp — ~500 ops/sec steady state.
- For a busy session (up to ~3,600 events in its 3-day TTL window, plus ~10 turn docs, plus 1 session doc) → ~7–8 s wall-clock. Well under any function timeout.
- **Non-atomic** — partial failure leaves orphans. Rejects with a count + last stack trace.
- Fires `onDocumentDeleted` triggers if any exist (none in this repo today).

### 6.2 Caveat 1 — active-run race

If the creator deletes while the worker is mid-run, after `recursiveDelete` returns:

- The worker may still write a few timeline events to `sessions/{sid}/events/*` before its next `_fenced_update` call discovers the session doc is gone (OwnershipLost raised because `snap.to_dict()` returns empty → attempt mismatch).
- Those events are orphans. They get reaped by the 3-day TTL on `events.expiresAt` — not ideal, but bounded.

**Options:**

- Accept the orphans (plan's current posture — simpler).
- Write `status='cancelled'` to session doc first, then delete after the worker drains. Heavier, requires worker cooperation.

Plan should explicitly pick. I recommend "accept the orphans, log on recursiveDelete failure" — fits the plan's simplicity principle and the TTL already reaps them.

### 6.3 Caveat 2 — function timeout

`recursiveDelete` is non-atomic; if it runs longer than the Cloud Function timeout, the function terminates mid-stream and leaves orphans that **don't** fall under the events TTL (the session and turn docs have no TTL).

**Mitigation:** `timeoutSeconds: 120, memory: 256MiB` on `agentDelete`. Worst-case bound on typical session is ~8 s; 120 s is 15× headroom. Plan should specify this.

### 6.4 What to add to the plan

Two short sentences in §8 `agentDelete` description:

> `agentDelete` uses `db.recursiveDelete(db.doc('sessions/${sid}'))`. Deploy with `timeoutSeconds: 120`. Accept that mid-run deletes may leave orphan event docs; those are reaped by the 3-day events TTL.

---

## 7. Mixed-version deploy drill — empirical prediction

Plan §15 calls for a "Mixed-version deploy drill." Based on the static code path:

- Between `deploy-worker` and Firebase deploy, old `agentStream` is still live. Old agentStream writes `reply/sources/title/turnSummary` to the **session doc** only (today's behavior).
- New worker only writes terminal content to the **turn doc** (plan §8 worker #4).
- An old client observing the session doc sees `status='complete'` but `reply=null` → renders empty.

So the predicted failure mode is: **open tab mid-query, no terminal rendered, refresh after step 3 shows the completed answer.** Plan §14 already accepts this as "refresh once and in the worst case resend."

The drill is a useful sanity check, but the outcome is predictable from static analysis. If the drill shows anything worse (e.g., session stuck in `queued`, or task never picked up), there's a deeper bug. I don't expect it.

**Recommendation:** the drill is still worth running as defense in depth, but don't block implementation on it — start coding the plan and run the drill in the staging rollout.

---

## 8. What the plan can tighten (not blockers)

Rolled up from findings above:

1. **§8 worker change #1:** explicitly state "Runner.run_async must receive the creator's stored `userId`, not the submitter's." Cite `worker_main.py:1033` as the swap site.
2. **§8 `agentDelete`:** pick a posture on the mid-run-delete race (orphan events or pre-flip to cancelled). Specify `timeoutSeconds: 120`.
3. **§7 SDK config:** drop the literal `cacheSizeBytes: 100 * 1024 * 1024` (it's the SDK default). Optional — no harm.
4. **§7 SDK config:** note that `initializeFirestore` must stay inside the lazy async `getFirebase()` handle, not hoisted to module scope (SSR/prerender hazard).
5. **§7 and §2.5 wording:** don't promise a specific reconnect latency. "Usually fast" is honest; "1.8 s" is optimistic and not robust to flaky networks.
6. **§14 / §15:** spell out what "the smallest temporary mitigation" looks like in the §20 decision row, so if the drill fails, there isn't a new design cycle. My vote: a narrow worker-side dual-write (terminal content to both session-level fields AND turn doc) for one deploy cycle, 5–8 lines, removable the day after hosting goes live.

None of these require architectural rework. They're clarifications the plan should fold in before implementation starts.

---

## 9. What I did NOT verify and why

- **Cloud Tasks task-name dedup behavior across a worker redeploy** — requires live Cloud Tasks; infra-level, not something the emulator covers. Plan relies on existing behavior that's been in production for months.
- **Live restrictive-network drill (corporate proxy blocks `*.googleapis.com`)** — this is exactly what plan §15's decision gate prescribes. Best done on real restrictive networks, not simulated in a dev VM. Do before ship.
- **Actual ADK `VertexAiSessionService` session creation** — would need a real GCP project and Agent Engine. Source inspection is sufficient for the claim I flagged; the runtime check is deterministic.

---

## 10. Bottom line

The updated plan is substantially stronger than the previous draft. The disputed decisions — `agentRead` deferred behind a drill, `sessions_private` deferred, mixed-version bridge deferred — are well-structured gates, not walkbacks.

Three things to add to the plan before coding:

1. The **explicit ADK `user_id` swap** at the Runner call site, spelled out in §8.
2. The **`agentDelete` behavior** on mid-run (accept orphans, log failures) and its **function timeout**.
3. The **SSR guardrail** on `initializeFirestore` (keep it lazy).

Everything else in the plan either empirically holds up (rules, cold-cache shape, multi-doc fencing, cap enforcement) or is already correctly gated behind a drill (restrictive-network, sessions_private, mixed-version bridge).

Green to start implementation once those three are folded in.
