# Implementation log — server-stored sessions rearchitecture

Append-only running log. Every coding agent in every stage MUST append a new `## Stage N — <title>` section when starting work, record decisions/surprises/blockers/learnings during work, and close with a verification summary.

**Do not edit or delete prior entries.** If something in a prior entry turns out to be wrong, note the correction in the current stage's entry.

**Source plan:** `docs/server-stored-sessions-plan.md`
**Staged execution plan:** `/home/adam/.claude/plans/i-think-that-for-ticklish-stroustrup.md`
**Verification reports:** `docs/server-stored-sessions-plan-verification-2026-04-23.md` + `-final.md`

Per-stage entry template:

```md
## Stage N — <title>

**Started:** YYYY-MM-DD HH:MM
**Agent:** <task description>

### What was done

- ...

### What worked

- ...

### What didn't work / surprises

- ...

### Learnings (patterns to repeat or avoid)

- ...

### Blockers encountered

- ...

### Handoff notes for next stage

- ...

**Completed:** YYYY-MM-DD HH:MM — Verification: <pass/fail, which tests>
```

---

## Stage 0 — Housekeeping + test infra

**Started:** 2026-04-23 15:40
**Agent:** Main session (Opus 4.7 1M) — simple housekeeping, no delegation

### What was done

- Created this running log skeleton
- Added `firestore.rules.proposed` — the plan §6 proposed ruleset as a standalone file
- Added `firestore.rules.proposed.spec.js` — 22-case test suite against the proposed rules (adapted from `/tmp/proposed.rules.spec.js` generated during the 2026-04-23 verification round, which empirically validated these rules behaviors)
- Added `npm run test:rules:proposed` script in `package.json`

### What worked

- The verification-round spec transplanted cleanly; the single change was reading `firestore.rules.proposed` from the repo rather than `/tmp/proposed.rules`
- Running `test:rules` (existing suite) and `test:rules:proposed` (new suite) in parallel produces independent, non-interfering results

### What didn't work / surprises

- None

### Learnings

- Keeping the proposed rules as a separate file lets us test the future rules behavior without touching the live rules. When Stage 1 swaps `firestore.rules` to the proposed content, we can either (a) keep `firestore.rules.proposed` around temporarily as a reference, or (b) delete it and merge the proposed tests into the main `firestore.rules.spec.js`. Stage 1 picks one — logged there.

### Blockers encountered

- None

### Handoff notes for next stage

- Stage 1 should update `firestore.rules` to match `firestore.rules.proposed`. After the swap, either delete the proposed file or keep it as a snapshot of the pre-cutover state.
- Baseline: `npm run test:rules` passes the existing creator-only suite (confirmed during Stage 0).

**Completed:** 2026-04-23 15:54 — Verification: PASS

- `npm run test:rules` — 10 passing (baseline against current creator-only rules, unchanged)
- `npm run test:rules:proposed` — 22 passing (proposed rules behavior validated)

No interference between the two suites. Ready for Stage 1.

---

## Stage 1 — Firestore rules + indexes

**Started:** 2026-04-23 15:55
**Agent:** Main session (Opus 4.7 1M)

### What was done

- Swapped `firestore.rules` to the plan §6 capability-URL rules (the same content that had been living in `firestore.rules.proposed`)
- Updated `firestore.indexes.json`:
  - Added `sessions(participants array-contains, updatedAt desc)` composite index for the sidebar listener
  - Removed the now-obsolete `sessions.expiresAt` TTL fieldOverride (sessions no longer have an `expiresAt` field under the new schema — only events keep their TTL)
- Merged the proposed-rules spec into `firestore.rules.spec.js` (which is what `npm run test:rules` already runs) and deleted the temporary `firestore.rules.proposed*` files + the `test:rules:proposed` script. Kept a single source of truth.

### What worked

- Single spec file + single script is cleaner than keeping the parallel "proposed" suite. The Stage 0 hand-off note flagged this as a choice; landed on option (a) from that note: merge and delete the temporary files.
- `firestore.rules.spec.js` now doubles as the plan's required rules-test coverage (participants list, open get, etc.). No new test file needed downstream.

### What didn't work / surprises

- None. The index field syntax for `array-contains` uses `arrayConfig: "CONTAINS"` in `firestore.indexes.json` (not `order: "ASCENDING"`) — confirmed from existing Firebase docs and the deploy would have failed otherwise. Landed correctly on first try.

### Learnings

- When the test suite is updated to match new behavior before the implementation code, there's no "red" phase — validation is direct once the rules file is swapped. Nice property for staged work.

### Blockers encountered

- None

### Handoff notes for next stage

- Stage 2 (agentStream rewrite) needs to write the new session-doc shape: `participants` array, `lastTurnIndex`, no `expiresAt`, no `reply`/`sources`/`turnSummary` at the session level. Transactional read of `lastTurnIndex` with cap at 10.
- The existing watchdog indexes (`status+queuedAt`, `status+lastHeartbeat`, `status+lastEventAt`) are preserved — no change needed for watchdog queries.

**Completed:** 2026-04-23 15:56 — Verification: PASS

- `npm run test:rules` — 22 passing against the new live rules

---

## Stage 2 — agentStream backend rewrite

**Started:** 2026-04-23 15:57
**Agent:** Delegated general-purpose agent

### What was done

- Rewrote `agentStream` in `functions/index.js` per plan §8:
  - Dropped the creator-only ownership check — any signed-in visitor can submit a turn under the capability-URL model.
  - Kept the one-in-flight guard (`status in ('queued','running')` → 409 `previous_turn_in_flight`).
  - Added the shared 10-turn cap: reads `existing.lastTurnIndex ?? 0`, rejects with 409 `turn_cap_reached` when it already equals `MAX_TURNS_PER_SESSION` (10).
  - Split the two UID roles explicitly: `submitterUid` drives rate limiting + `participants`; `creatorUid` (from the session's stored `userId`, or the submitter on first turn) is what lands in the Cloud Task body for Vertex Agent Engine ownership.
  - First turn: `t.set(sessionRef, …)` creates the session with `userId: submitterUid`, `participants: [submitterUid]`, plus the perTurn fields. Follow-ups: `t.update(sessionRef, { …perTurn, participants: FieldValue.arrayUnion(submitterUid) })` — `userId` is never overwritten.
  - Session doc now carries `lastTurnIndex` + `updatedAt: serverTimestamp()` (bumped on every enqueue). Terminal content fields (`reply`, `sources`, `turnSummary`) are gone from the session doc; they move to turn docs per plan §5.
  - `expiresAt` writes + the `SESSION_TTL_MS` constant removed — sessions no longer have a TTL.
  - Turn doc created in the same transaction at `sessions/{sid}/turns/{turnKey}` where `turnKey = String(newTurnIdx).padStart(4, '0')`. Fields: `turnIndex`, `runId`, `userMessage` (raw, not prefixed), `status: 'pending'`, `reply/sources/turnSummary: null`, `createdAt: serverTimestamp()`, `completedAt: null`, `error: null`.
  - Cloud Task body now includes `turnIdx: newTurnIdx` as an integer (not a zero-padded string) and `userId: creatorUid` (not the submitter).
- Rewrote the agentStream block in `functions/index.test.js`:
  - Upgraded the Firestore mock so refs carry a `_path` string, letting assertions partition `set`/`update` calls by session vs. turn doc.
  - Added `FieldValue.arrayUnion` to the stub (produces a sentinel `{ __arrayUnion: […] }`).
  - Removed the obsolete ownership-rejection and legacy-missing-userId-rejection tests.
  - Added: first-turn creation test (asserts session schema + turn 0001 + task body); same-user follow-up (arrayUnion with own UID, `lastTurnIndex` → 2, task body creator UID preserved); shared-URL follow-up (visitor submits, session.userId not overwritten, arrayUnion adds visitor, task body `userId` still equals creator); 10-turn cap (lastTurnIndex=10 → 409 `turn_cap_reached`); boundary case (lastTurnIndex=9 succeeds and becomes 10); `updatedAt` bumped via serverTimestamp on enqueue; the two one-in-flight paths (`queued` and `running`); task dedup name uses runId; enqueue-fail recovery still flips to status=error.
- Log appended (this entry).

### What worked

- Enriching the Firestore ref mock with `_path` was the unlock — the real txn contract is `t.set(ref, data)` / `t.update(ref, data)`, and distinguishing session vs. turn writes by path lets every multi-doc assertion stay straightforward without touching the real Admin SDK.
- Keeping the plan's two-UID split (`submitterUid` vs. `creatorUid`) as named locals in the handler made the tests read cleanly — the shared-URL follow-up test reads almost like plan prose.
- `npx prettier --write` on the two touched files closed the only formatting delta; the pre-existing doc/spec warnings in the global `npm run lint` are unrelated to Stage 2 work.

### What didn't work / surprises

- The old test file asserted `mockDb.update.mock.calls[0].arguments[0]` was the perTurn payload — that relied on the collapsed mock where `collection()` / `doc()` both returned `mockDb` itself, so `t.update` got called with only one arg. Under the corrected 2-arg signature (matching the real SDK), `arguments[0]` is the ref and `arguments[1]` is the data. Every new assertion that introspects a write payload reads `arguments[1]`. Flagged here so Stage 3 / Stage 4 agents don't trip on the same shape.
- Prettier reformatted exactly one long-line `checkRateLimit(uidRateLimitMap, …)` call. No semantic change.

### Learnings (patterns to repeat or avoid)

- When the handler writes to multiple doc paths in one transaction, the test-side mock must carry enough ref identity to partition those writes. Add a `_path` string to `makeRef(path)` and reach for a small `partitionWrites(sessionPath)` helper rather than juggling global mock state per assertion.
- `FieldValue.arrayUnion` / `FieldValue.serverTimestamp` work best as sentinel objects in tests (`{ __arrayUnion: [...] }`, `'__server_timestamp__'`). Don't try to simulate their Firestore-side semantics — tests should assert the _call_, not the resolved array value.

### Blockers encountered

- None.

### Handoff notes for next stage (Stage 3 — agentDelete)

- The mock scaffolding in `functions/index.test.js` already supports subcollection refs via `makeRef(path).collection(name).doc(id)` and direct `.get()` / `.update()` / `.set()` outside transactions. Stage 3 should be able to write agentDelete tests without further mock surgery — but `db.recursiveDelete(ref)` is NOT stubbed yet. Add a `recursiveDelete` spy on `mockDb` when you start Stage 3.
- The 2-arg txn signature (`t.set(ref, data)` / `t.update(ref, data)`) is now load-bearing for every agentStream assertion. Any future handler that writes in a txn should keep that contract so the partition helper keeps working.
- `agentCheck` is still in `functions/index.js` at its old location and still reads `session.reply` / `session.sources` / `session.title` / `session.turnSummary`. Under the new schema those fields move to turn docs, so agentCheck will return stale shape post-Stage-4 worker changes. Per the plan, `agentCheck` is deleted entirely later (plan §8 "agentCheck — DELETED"); Stage 3 replaces its rewrite slot with `agentDelete`. Don't patch agentCheck — just leave it in place until its deletion stage.
- `SESSION_TTL_MS` is gone from `functions/index.js`. If any other file references it (none did as of this stage), the Stage 4 worker pass should remove stragglers.

**Completed:** 2026-04-23 16:01 — Verification: PASS

- `cd functions && npm test` — 49 passing (14 agentStream tests, all new tests green, no regressions in intake / sttToken / tts / agentCheck / watchdog).
- `npx prettier --check functions/index.js functions/index.test.js` — clean.
- `npx eslint functions/index.js functions/index.test.js` — clean.

---

## Stage 3 — agentDelete + routing

**Started:** 2026-04-23 16:05
**Agent:** Delegated general-purpose agent

### What was done

- Added `agentDelete` Cloud Function to `functions/index.js` per plan §6 / §8:
  - `onRequest({ cors: true, timeoutSeconds: 120, memory: '256MiB' }, handler)` — follows the existing pattern used by `agentStream` / `agentCheck`, with the timeout + memory the plan mandates.
  - Method guard: 405 on non-POST.
  - Auth: Bearer-token parse matching `agentStream` / `agentCheck`; 401 on missing header, 401 on `verifyIdToken` rejection.
  - Input: 400 when `sid` is missing or not a string.
  - Ownership: read `sessions/{sid}` first. Missing doc → 404 `{ok: false, error: 'session_not_found'}`. Doc exists but `data.userId !== uid` → 403 `{ok: false, error: 'not_creator'}`. Admin SDK bypasses Firestore rules so this explicit check is load-bearing.
  - Delete: `await db.recursiveDelete(sessionRef)` — one call reaps the session doc plus `turns/*` and `events/*`. On failure, log the sid + error and return 500 `{ok: false, error: 'delete_failed'}`. No retry, no drain coordination, no soft-delete.
  - Success: 200 `{ok: true}`.
- Extended `functions/index.test.js`:
  - Added `recursiveDelete: mock.fn(...)` to the existing `mockDb` (Stage 2 flagged this as missing).
  - Reset the new spy in `beforeEach`.
  - Added an `agentDelete` describe block with all 8 required cases: 405 non-POST; 401 missing header; 401 bad token; 400 missing/non-string sid; 404 session_not_found; 403 not_creator (contributor attempt); 200 + `recursiveDelete` called on `sessions/{sid}` (asserts the ref's `_path`); 500 + console.error carries the sid when `recursiveDelete` rejects.
- `firebase.json`: added `{"source": "/api/agent/delete", "function": "agentDelete"}` rewrite in the `agent` hosting target, alongside `/api/agent/check` and `/api/agent/stream`.
- `vite.config.ts`: added `/api/agent/delete` dev proxy targeting `https://us-central1-superextra-site.cloudfunctions.net` with rewrite to `/agentDelete`, matching the shape of `/api/agent/check`.
- Appended this log entry.

### What worked

- The Stage 2 mock scaffolding was exactly right for this stage — dropping a single `recursiveDelete` spy on `mockDb` plus reusing the existing `makeRef(path)._path` convention was enough to write the ownership + destructive-action assertions without touching anything else.
- Following the `agentStream` options shape (`onRequest({ cors, timeoutSeconds, memory }, handler)`) was the cleanest place to land the plan-mandated `timeoutSeconds: 120` / `memory: '256MiB'` config — no new patterns introduced.
- The 404 vs. 403 ordering comes directly from "read first, then branch" and fell out without any special casing. Contributor-trying-to-delete resolves to 403 deterministically.

### What didn't work / surprises

- First attempt to Edit the tail of `index.test.js` failed because the old_string assumed nested `it`s were indented 2 tabs (matching `agentStream`). They're actually 1 tab — the file's describe blocks are at top level with `\t`-level `it`s. Re-running with single-tab indentation landed cleanly. Noting here so Stage 4 / Stage 5 agents don't chase the same phantom.
- Nothing else surprising. The Firebase Admin `db.recursiveDelete` signature is exactly what the plan said — single-ref call.

### Learnings (patterns to repeat or avoid)

- For functions that need to introspect the exact ref a destructive/targeted operation hits, assert on `mockDb.<spy>.mock.calls[0].arguments[0]._path`. The `_path` tag from Stage 2's `makeRef` generalizes past `set`/`update` — it works for any ref-accepting spy.
- Test `console.error` includes the sid by intercepting `console.error` with a small scratch buffer and restoring it in `finally`. Avoids leaking log spam into the test runner output while still proving the logged context.

### Blockers encountered

- None.

### Handoff notes for next stage (Stage 4 — worker + watchdog)

- `agentDelete` assumes `session.userId` still identifies the creator. Stage 4's worker rewrites must not touch `session.userId` — the `agentStream` path (Stage 2) already preserves it on follow-ups; the worker must keep that invariant on every terminal write too.
- If the worker writes an event doc to a session that the creator just deleted, the write can succeed briefly before the next fenced transaction fails with OwnershipLost. That's the accepted behavior per plan §8 "mid-run delete leaves orphan events bounded by the 3-day TTL." Do not add drain/cancel coordination in Stage 4.
- `agentCheck` is still in `functions/index.js` untouched. Plan §8 deletes it outright once the frontend stops calling it; that happens in a later stage (Stage 5/6 when `chat-recovery.ts` is deleted). Stage 4 should not touch `agentCheck`.
- `db.recursiveDelete` is now exercised by the test suite via a mock spy. If Stage 4 adds anything that touches `mockDb`, the new spy pattern is trivially extended — just mirror the `recursiveDelete: mock.fn(async () => {})` declaration and add a `resetCalls()` + `mockImplementation(...)` reset in `beforeEach`.
- Routing is ready: `firebase.json` now exposes `/api/agent/delete` on the agent hosting target, and the dev proxy in `vite.config.ts` points at `https://us-central1-superextra-site.cloudfunctions.net/agentDelete`. Stage 7 (frontend UI glue) can call `POST /api/agent/delete` directly with a Firebase ID token.

**Completed:** 2026-04-23 16:12 — Verification: PASS

- `cd functions && npm test` — 57 passing (8 new agentDelete cases, all prior cases green).
- `npx prettier --check functions/index.js functions/index.test.js firebase.json vite.config.ts` — clean.
- `npx eslint functions/index.js functions/index.test.js` — clean.
- Grep confirmed no stray references to `/api/agent/read` or `agentRead` in the code tree (only pre-existing plan-doc mentions).

---

## Stage 4 — Worker + watchdog

**Started:** 2026-04-23 16:20
**Agent:** Delegated general-purpose agent

### What was done

- **`agent/superextra_agent/firestore_events.py`** — flipped `EVENT_TTL_DAYS = 30 → 3` per pre-implementation pin #1. Events are operational artifacts; the plan §11 retention model keeps them short and only lets full transcripts persist through turn docs.
- **`agent/worker_main.py`** — the meat of this stage:
  - Added `turnIdx: int` to `RunRequest`. The Cloud Task body already carries `turnIdx` as an integer per Stage 2; the worker now parses it and computes `_turn_doc_key(n) = f"{n:04d}"` only at doc-path resolution time (pin #3).
  - Extended the fenced-write primitive with a sibling `_fenced_update_session_and_turn_logic` / `_fenced_update_session_and_turn_txn` / `_fenced_update_session_and_turn` trio that takes both session and turn refs and writes both docs atomically inside the ownership fence. The single-doc `_fenced_update` stays as-is for heartbeat / `lastEventAt` / `adkSessionId` persistence.
  - Changed `_takeover_logic` to take `turn_ref` positionally and write `{status: 'running'}` to the turn doc in the same transaction as the session update (pin #4). Both callers threaded — the primary `/run` takeover and `_poll_until_resolved`'s recovery takeover. The signature of `_poll_until_resolved` gained a `turn_idx` parameter so it can re-derive the turn ref.
  - Terminal writes moved to two-doc fenced writes:
    - **Success**: session gets `{status: 'complete', updatedAt: SERVER_TIMESTAMP}` plus `title` on first-turn runs; turn gets `{status: 'complete', reply, sources, turnSummary, completedAt: SERVER_TIMESTAMP}`. Session no longer carries `reply`/`sources`/`turnSummary` per plan §5.
    - **Pipeline error**: both docs get `{status: 'error', error: <reason>}`; session also bumps `updatedAt`.
    - **Sanity-fail (empty/malformed reply)**: same shape as pipeline error.
  - Runner call sites at `_session_svc.create_session(user_id=body.userId)` (line ~1082) and `_runner.run_async(user_id=body.userId, ...)` (line ~1129) were **not changed**. agentStream already guarantees `body.userId` is the creator UID on every turn (Stage 2), and the defensive mismatch check at `worker_main.py:257` validates that session.userId == body.userId before the run proceeds. So `body.userId` on the Runner line is the same creator UID stored on the session, which is what the ADK `VertexAiSessionService.get_session` equality check requires. Keeping `body.userId` means there's a single source of truth in the handler (the Pydantic-validated request model) rather than re-reading session.userId inside the handler. See the new `test_creator_uid_flows_through_to_runner_call` test for the contract check.
- **`functions/watchdog.js`** — extended the flip transaction:
  - Imported `FieldValue` to bump `session.updatedAt` alongside the status flip.
  - Inside the existing `runTransaction`, after the four race-safety predicates (missing / status_changed / run_advanced / field_freshened) pass, the transaction now issues TWO updates: the original session flip plus a turn-doc flip at `sessions/{sid}/turns/{lastTurnIndex:04d}` when `data.lastTurnIndex` is a number > 0. Both writes sit BEHIND the predicates, so the race-safety invariants still hold atomically.
  - If `lastTurnIndex` is absent (legacy docs, or a partial-enqueue before Stage 2 Firestore catches up), the watchdog writes only the session doc. That preserves forward compatibility without ever blocking the flip on missing turn metadata.
- **`agent/tests/test_worker_main.py`** — propagated signature changes through existing tests and added new tests:
  - Propagated `turn_ref` positional arg through every `_takeover_logic` call.
  - Added `test_takeover_writes_turn_status_running_in_same_transaction` (pin #4 contract: exactly two refs updated, session + turn).
  - Added `test_fenced_update_session_and_turn_commits_both_when_ids_match` + two `raises_on_*_mismatch` tests for the new two-doc primitive.
  - Added `test_turn_doc_key_zero_pads_to_four_digits`.
  - Added the four new turn-lifecycle tests using a new `_install_split_harness` that records session- and turn-side updates separately:
    - `test_terminal_success_splits_content_to_turn_doc` — reply/sources/turnSummary/completedAt go to the turn doc; session gets only status+updatedAt (no title on follow-ups).
    - `test_terminal_success_on_first_turn_writes_title_to_session` — title goes to session exclusively on first turn.
    - `test_terminal_error_propagates_to_both_docs`.
    - `test_sanity_fail_error_propagates_to_both_docs`.
  - Added `test_creator_uid_flows_through_to_runner_call` — drives the handler with a `body.userId = creatorUid` request (as agentStream will have set it on a follow-up from a different visitor) and asserts that creator UID is what `_runner.run_async(user_id=...)` receives. This is the ADK equality-check contract made explicit.
  - Split `test_takeover_userid_mismatch_raises_500_*` into TWO tests: the old raise-case plus a new no-raise case (`_check_passes_when_body_carries_creator_uid`) that asserts the defensive check accepts `body.userId == session.userId` as the agentStream invariant.
  - Original harness (`_install_run_harness`) kept the legacy tests working by merging session- and turn-side dicts into a single entry per terminal write (so assertions like `complete_writes[0]["reply"] == short` still find their data). New tests use the split harness.
- **`functions/watchdog.test.js`** — extended the `firebase-admin/firestore` module mock to surface `FieldValue.serverTimestamp()` as a sentinel string; extended `makeDb` so `ref.doc(id).collection('turns').doc(turnKey)` returns a ref with a composite id (`<sid>/turns/<turnKey>`) that the txn update mock can partition. The existing "flips each stuck session" test now asserts on four writes (two session + two turn). Added `skips turn-doc update when lastTurnIndex is missing` (legacy-doc branch) and `skips both writes if currentRunId advanced between scan and txn` (race-safety invariant preserved across the two writes).

### What worked

- The pure-logic split that Phase 3 landed for `_fenced_update_logic` / `_takeover_logic` made this stage tractable: the production `_fenced_update_session_and_turn_txn` wraps the pure function via `firestore.transactional`, and tests call the `_logic` version directly against a `MagicMock` transaction. No new transactional machinery.
- Keeping the single-doc `_fenced_update` primitive alongside the two-doc version — rather than forcing every callsite to move to the two-doc shape — kept heartbeat ticks and `lastEventAt` bumps untouched. Only the THREE terminal writes (success, pipeline error, sanity-fail) needed to move.
- The `_install_run_harness` merged-dict shortcut preserved ~15 legacy tests (anything that read `complete_writes[0]["reply"]` / `["title"]` / etc.) without a dozen test rewrites. The new `_install_split_harness` gives explicit session-vs-turn assertions for the split-contract tests that need them. Two harnesses, each matching the shape of what its tests care about.
- `session.userId == body.userId` was already the agentStream invariant from Stage 2, and the defensive `HTTPException(status_code=500, detail="userId mismatch — agentStream bug")` check at `worker_main.py:257` was already in place. No code change was needed at the Runner call sites. Verified by the new dedicated test.

### What didn't work / surprises

- Expected to have to change the Runner call sites to read `session.userId` explicitly (the prompt hedged on this). In practice: no. Stage 2's agentStream contract does all the heavy lifting. The defensive check already guards against the one failure mode (agentStream bug silently passing the wrong UID). Logged this finding per the stage prompt's explicit request.
- First run of the worker tests failed 3 cases, all from the upstream signature changes: two `RunRequest(...)` constructions missing `turnIdx`, and `_poll_until_resolved(...)` missing its new `turn_idx` positional. Fixed mechanically; no conceptual surprise.
- The `firebase-admin/firestore` module mock in `watchdog.test.js` needed to grow a `FieldValue` export once the watchdog started importing it. Added the minimal sentinel-producing version.

### Learnings (patterns to repeat or avoid)

- When a module-level primitive moves from one-doc to two-doc semantics, keep BOTH functions live. Heartbeat/progress writes want the minimum-field transaction; terminal writes want the two-doc transaction. Don't collapse them into a single variadic function — the call sites read more clearly when each primitive matches its purpose exactly.
- For test harnesses that drive multi-write handlers, a merged-dict adapter (combining session + turn updates into one record per transaction) preserves assertion readability for the bulk of tests while a split-record adapter (keeping the two updates separate) gives the split-contract tests the granularity they need. Both are cheap; maintain both.
- When extending an existing race-safe transaction to write a second doc, keep all race-safety predicates BEFORE any write in the transaction body. The invariant is "all or nothing, under the same predicates" — violating that makes the second write unsafe independently of the first.

### Blockers encountered

- None.

### Handoff notes for next stage (Stage 5 — Frontend SDK init + stream helper)

- The turn doc now carries the reply/sources/turnSummary — the frontend stream helper (`firestore-stream.ts`) must read terminal state from `sessions/{sid}/turns/{turnKey}` rather than from the session doc. Stage 5 is supposed to do that move; the worker is now writing the new shape, so Stage 5 can test its listener against a real fenced terminal write.
- The events listener scope change (plan §7 — move from the old collection-group query filtered by `userId` to `sessions/{sid}/events`) is still a Stage 5 concern; the worker writes the same event-doc shape into the per-session subcollection that Stage 2's index already supports.
- `body.userId` is the creator UID on every turn. Stage 5 doesn't touch this — it's wired correctly end-to-end via Stage 2's agentStream and Stage 4's defensive check. Only Stage 2 / Stage 4 know about the submitter-vs-creator UID split; the frontend just sees `session.userId` (stable creator) and `session.participants` (growing list of contributors).
- If Stage 5 adds a turns-listener wait-for-terminal helper, note that the events listener MUST detach on the turn doc's terminal status, not the session's (pin #6 from pre-implementation notes). They briefly disagree during the two-doc fenced transaction — session-side can be visible to the listener before the turn-side settles in the same Firestore commit window. The turn-doc terminal status is the authoritative detach trigger.
- The event docs the worker writes still include a `userId` denormalized field. Plan §5 notes this becomes unused by the new rules and can be cleaned up in a follow-up. No action in Stage 5.
- The watchdog now writes `session.updatedAt` on flip. Sidebar listener (Stage 6) should see error-flipped sessions resort by updatedAt without needing a polling refresh.

**Completed:** 2026-04-23 16:45 — Verification: PASS

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q` — 165 passed, 17 skipped (was 154 passed pre-stage; +11 new cases across two-doc primitive, turn lifecycle, takeover turn write, creator-UID contract, and turn doc key).
- `cd functions && npm test` — 59 passing (was 57; +2 new watchdog cases for turn-doc propagation and lastTurnIndex-missing fallback).
- `npx prettier --check functions/watchdog.js functions/watchdog.test.js` — clean.
- `npx eslint functions/watchdog.js functions/watchdog.test.js` — clean.
- ADK `VertexAiSessionService.get_session` user_id equality check (`agent/.venv/.../vertex_ai_session_service.py:190-193`) re-verified against the venv source. No ADK-level surprises.

---

## Stage 5 — Frontend SDK init + stream helper

**Started:** 2026-04-23 16:26
**Agent:** Delegated general-purpose agent (Opus 4.7 1M)

### What was done

- **`src/lib/firebase.ts`** — swapped `firestoreMod.getFirestore(app)` for `firestoreMod.initializeFirestore(app, { localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }) })` per plan §7 SDK config. Kept the call inside the existing lazy async `getFirebase()` IIFE — `persistentMultipleTabManager()` depends on `window` / IndexedDB, so hoisting would break prerender (plan §7 guardrail). Did NOT set `cacheSizeBytes` — SDK default is 100 MB per plan. Added an `appAlreadyExists` branch that falls back to `getFirestore(app)` on HMR: during a hot reload the FirebaseApp persists across module reinit but our `handlePromise` memo doesn't, and calling `initializeFirestore` twice on the same app throws. This keeps the existing HMR double-init guard intact and extends it to the Firestore instance.
- **`src/lib/firestore-stream.ts`** — rewrote `subscribeToSession` to the three-observer shape from plan §9:
  - Added a required fourth positional param `turnIdx: number`. Signature is now `subscribeToSession(sessionId, runId, turnIdx, callbacks)`.
  - Events query moved from `collectionGroup(db, 'events')` filtered by `(userId, runId)` to `collection(db, 'sessions', sessionId, 'events')` filtered by `runId` only. Drops the `userId` filter (rules are path-scoped now per Stage 1) and scopes the listener to the per-session path.
  - Terminal detection moved from the session-doc listener to a new turn-doc listener at `sessions/{sid}/turns/{turnKey}` where `turnKey = String(turnIdx).padStart(4, '0')`. `onComplete` and `onError` fire exclusively from the turn observer, pulling `reply`/`sources`/`turnSummary` from the turn doc. This matches Stage 4's fenced two-doc write and honors Pin #6 from the Stage 4 handoff: "events listener detach keys off the TURN doc's terminal status, not the session's."
  - Session-doc listener still exists but no longer fires terminal callbacks. It captures `title` (which stays session-level under the new schema) into a local `latestTitle` var that the turn observer merges into its `onComplete` call, and it drives `onAttemptChange` on retry. The session-side runs-scope guard on `currentRunId` and the stale-attempt-baseline protection are preserved verbatim.
  - Turn doc carries its own `runId`; defensive guard rejects cross-run snapshots. Cache guard on `fromCache` snapshots preserved. One-shot terminal guard preserved.
  - First-snapshot timeout retained as a safety net per the stage prompt (Stage 6 will decide whether to delete it when it rewrites chat-state).
  - Drop the `uid` local — `ensureAnonAuth()` is still called so the SDK has a token for the read, but the returned uid is no longer used in any query.
- **`src/lib/firestore-stream.spec.ts`** — rewrote the mock + tests for the three-observer shape:
  - Mock's `doc(...)` and `collection(...)` now attach a synthetic `_path` string (from joined positional args), letting tests partition observers by path. Added `collection` to the mock (was only `collectionGroup` before, which is gone).
  - Partition helpers in `captureObservers()` expose `.session` (2-segment path), `.turn` (4-segment path containing `/turns/`), and `.events` (ref's `_ref._path` ends with `/events`).
  - New tests: three-observer wiring + correct paths; 4-digit zero-padded turn key for `turnIdx=9`; turn doc terminal + title merge from session; turn terminal fires with `undefined` title when session observer hasn't emitted yet; cached turn complete ignored; cached turn error ignored; defensive cross-runId turn doc ignored; turn doc status=error fires onError; events query has exactly one `where` clause on `runId` (confirms the userId filter is gone).
  - Deleted tests that exercised terminal-from-session-doc behavior (no longer a contract).
  - Net: 22 tests, all green.

### What worked

- Keeping `ensureAnonAuth()` as a no-op-effect gate (we don't use its return value anymore) preserves the auth-before-subscribe invariant without introducing dead code paths that would confuse reviewers. The auth is load-bearing for the Firestore SDK to attach a token on every read; the _uid_ filter is what's gone, not the auth step itself.
- The `_path` synthesis trick from Stage 2's functions-test mock translated cleanly to the client-side stream test. Partitioning by path means tests read linearly against observer names rather than array indices that would shift when observer order changes.
- Prerender held on first try — no SSR fallout from the Firestore SDK config change, confirming the plan's "keep it inside the lazy IIFE" guardrail was correctly followed. `npm run build` completed both the client bundle and the static prerender pass without a single error.

### What didn't work / surprises

- The `subscribeToSession` signature change from 3 args to 4 (adding required `turnIdx`) cascaded into svelte-check errors in exactly three files: `src/lib/chat-state.svelte.ts` (2 call sites — lines 431, 604), `src/lib/chat-state.spec.ts` (22 places where `Parameters<typeof subscribeToSession>[2]` now resolves to `number` instead of the callbacks type), and `src/lib/components/restaurants/ChatThread.spec.ts` (1 callsite). This is the **expected Stage 6 breakage** per the stage prompt — it explicitly said not to fix chat-state here, and to log it for Stage 6's awareness. Listed below in Handoff notes.
- Vitest still reports all 86 tests green because the test-side mock `subscribeToSession: vi.fn()` doesn't enforce the TS signature — only the compile-time checker does. So `npm run test` passes while `npm run check` flags errors. That mismatch is safe: the runtime tests are still exercising the chat-state logic against a mock that accepts any positional args.
- Did NOT delete `chat-recovery.ts` or `ios-sse-workaround.ts` — per the stage prompt those are Stage 6's job. They still compile/work; they're just now consuming a firestore-stream shape that no longer delivers terminal callbacks from the session observer. Chat-state's fallback path into `chat-recovery` still type-checks because the callback shape (StreamCallbacks) didn't change — only where those callbacks fire from.

### Learnings (patterns to repeat or avoid)

- When a module's exported function signature changes and downstream callers live in a separate stage, a single positional-arg shift produces a distinctive TS error pattern (`Property 'X' does not exist on type 'number'`) that cleanly identifies exactly which callsites need updating. The downstream agent can grep for that error and the fix is mechanical.
- `persistentMultipleTabManager()` is the specific factory that touches `window`/IndexedDB. Keeping its invocation lazy (inside the `getFirebase()` IIFE) is the single guardrail that separates "prerender works" from "prerender throws ReferenceError: window is not defined." Don't try to hoist it for code-dedup reasons.

### Blockers encountered

- None.

### Handoff notes for next stage (Stage 6 — chat-state.svelte.ts rewrite)

- **Pre-existing svelte-check errors to clear when Stage 6 rewrites chat-state**:
  - `src/lib/chat-state.svelte.ts:431` and `:604` — both call `subscribeToSession(sessionId, runId, callbacks)` with 3 args; add the `turnIdx: number` fourth param. Under the new schema, `turnIdx` should come from `lastTurnIndex` on the session snapshot or be tracked locally as the current turn index (Stage 6 is deleting the browser-local conversation store anyway, so how exactly to plumb this is a Stage 6 design choice).
  - `src/lib/chat-state.spec.ts` — 22 errors on `Parameters<typeof subscribeToSession>[2]` (now resolves to `number`). Change to `[3]` once Stage 6 keeps the 4-arg shape, or retype the `cbs` helper against `StreamCallbacks` directly.
  - `src/lib/components/restaurants/ChatThread.spec.ts:70` — 1 error, same pattern.
- **Stream helper contract is stable going into Stage 6**:
  - Subscribe: `subscribeToSession(sessionId, runId, turnIdx, callbacks)` — all four required.
  - Callbacks shape (`StreamCallbacks`) unchanged. `onComplete(reply, sources, title?, turnSummary?)` still optional-last-two.
  - Title is delivered via the session-doc listener and merged into the turn-observer's `onComplete` call. If the turn terminal fires before the session observer has seen a title, `onComplete` receives `title=undefined` — the caller already tolerates that.
  - Terminal source is now the TURN doc. Session doc is for title + attempt changes only.
- **Event listener detach policy** — Stage 4 Pin #6: the events listener attached here continues to receive events until the returned `unsubscribe()` is called. Stage 6's chat-state should invoke that unsubscribe when the turn doc terminal fires (which is when `onComplete` / `onError` run). That matches the pre-existing chat-state behavior; it just now hangs off the turn-terminal instead of the session-terminal.
- **First-snapshot timeout kept** — if Stage 6 deletes `chat-recovery.ts` (per plan §9 "DELETE"), the `onFirstSnapshotTimeout` callback will have nothing to fall back to. Stage 6 can either drop the `onFirstSnapshotTimeout` field from `StreamCallbacks` and delete the timer, or route the timeout into the new fromCache-aware initial-load state from plan §7. Either way is fine; noted as a Stage 6 decision point.
- **Firestore persistent cache is now live** — first time a user loads a chat, IndexedDB gets seeded; subsequent loads render from cache first and then resolve against the server. Stage 6's initial-load state (plan §7) handles the "cache-hit-but-no-server-confirm" case; the SDK change here is the enabling half of that.
- **No changes to production data model or backend wire format this stage.** agentStream, worker, watchdog, rules, and indexes are identical to end-of-Stage-4. Only the frontend reads changed (collection path, which docs supply terminal state). This means Stage 5 can ship behind Stage 6's UI rewrite or alongside it — whichever Stage 6 finds simpler.

**Completed:** 2026-04-23 16:32 — Verification: PASS (with expected Stage 6 breakage in chat-state; see Handoff notes)

- `npm run build` — full client + static prerender pass, no errors. The SSR guardrail for `persistentMultipleTabManager` held; this was the #1 risk for Stage 5 and it didn't fire.
- `npm run test` — 86 passing across 9 files (was 86 pre-stage; stream-helper suite rewrote from 20 cases to 22 with net +2 new; no regressions in chat-state or ChatThread tests because their mocks don't enforce the TS signature).
- `npm run check` — 25 errors, all confined to three Stage 6 files (`chat-state.svelte.ts`, `chat-state.spec.ts`, `ChatThread.spec.ts`), all from the `subscribeToSession` signature shift. No other errors introduced. Pre-existing warnings (a11y, unused CSS) unchanged.
- `npm run lint` — eslint clean. Prettier flags 7 pre-existing doc/spec files (unchanged from before Stage 5); all touched files (`firebase.ts`, `firestore-stream.ts`, `firestore-stream.spec.ts`) are prettier-clean after a single `--write` pass.
- Dev server on 5199 serves `/` and `/agent/chat` with HTTP 200.

---

## Stage 6 — chat-state.svelte.ts rewrite

**Started:** 2026-04-23 16:33
**Agent:** Delegated general-purpose agent (Opus 4.7 1M) — first pass ended mid-stage when an API error terminated the session; finished by a follow-up Opus 4.7 1M session that rewrote the specs and landed this log entry.

### What was done

- **`src/lib/chat-state.svelte.ts`** — full rewrite (821 → 716 lines). Flipped the module from a browser-local conversation store + Firestore subscription helper into a pure Firestore-listener-driven state singleton:
  - Four live Firestore reads drive the UI:
    1. **Sidebar listener** — `sessions where participants array-contains currentUid order by updatedAt desc`. Lazy-attaches on first read of `chatState.sessionsList` (also kicked from `selectSession`). Snapshots map into `SessionSummary[]`.
    2. **Active session listener** — `doc('sessions', sid)`. Reflects into `activeSession`, drives `canDelete` / `loadState`, and merges `placeContext` into the local fallback so follow-ups still work before a fresh snapshot lands.
    3. **Active turns listener** — `collection('sessions', sid, 'turns') orderBy('turnIndex')`. Source of truth for `messages` (flattened as `{role:'user', text:turn.userMessage}` + `{role:'agent', text:turn.reply, sources, turnSummary}` if `status==='complete' && reply`).
    4. **Active events listener** — `collection('sessions', sid, 'events') where runId == currentRunId orderBy('attempt', 'seqInAttempt')`. Attaches only when the latest turn's status is in `{queued, running, pending}`; detaches on the TURN doc's terminal status (pin #6).
  - `startNewChat(query, place)`: generates a fresh sid via `crypto.randomUUID()` (with a safe fallback for insecure contexts), calls `selectSession(sid)` first so listeners are primed for incoming writes, then POSTs `{sessionId, message, placeContext, history: [], isFirstMessage: true}` to `/api/agent/stream` with a Bearer ID token.
  - `sendFollowUp(message)`: POSTs to `/api/agent/stream` under the active sid. Throws `no_active_session` if none is selected. No-ops on empty/whitespace.
  - `selectSession(sid)` / `deleteSession(sid)` / `reset()` match the plan §9 surface. `deleteSession` POSTs `/api/agent/delete` with a Bearer token; on 200, clears active listeners only when `sid === activeSid`. Sidebar listener handles list updates organically.
  - fromCache-aware `loadState` (plan §7): `'loading'` on select, `'loaded'` on server-confirmed exists=true, `'missing'` on server-confirmed exists=false, `'loadTimedOut'` if 10 s of only cache-only snapshots elapses. Cache-only exists=false does NOT flip to missing.
  - Typewriter rule (plan §10): per-turn-index `previousTurnStatus` map captures `running → complete` transitions observed in the current browser session; on such a transition, if a `drafting` event is in the live timeline, we set `typingMessageTimestamp = turn.completedAtMs`. Turns already `complete` on first snapshot stay historical (no animation).
  - Events listener ignores `type='complete'` / `type='error'` event docs (unfenced writes). Turn doc terminal is the sole answer source.
  - Events dedup keyed on `(runId, attempt, seqInAttempt)` so reconnect replays don't double-render timeline rows.
  - Optional pin #5 one-liner: clears `localStorage['se_chats']` / `['se_chat']` on module load so stale browser-local state from pre-cutover cannot bleed into the new session.
  - Exports `_testing` with `reset()` + `setCurrentUid()` + a `_helpers` bundle for test-side coverage of `zeroCounts` / `toMillis` / `turnDocKey`.
- **Deleted:**
  - `src/lib/chat-recovery.ts` (174 lines) — no-longer-used polling recovery helper.
  - `src/lib/chat-recovery.spec.ts` — its tests.
  - `src/lib/ios-sse-workaround.ts` — no-longer-needed visibility workaround.
  - `src/lib/ios-sse-workaround.spec.ts` — its tests.
- **`src/lib/chat-state.spec.ts`** — rewritten against the new API (493 → 944 lines). The old suite was built around `chatState.start()`/`send()`/`conversations`/`deleteConversation`/`resumeCurrentIfNeeded`/`handleReturn` and closure-captured `subscribeToSession` callbacks. The new suite mocks `firebase/firestore`'s `onSnapshot`/`doc`/`collection`/`query`/`where`/`orderBy` directly (reusing the Stage-5 path-partition idiom from `firestore-stream.spec.ts`) and covers:
  - Sidebar listener: query constraints (`participants array-contains uid`, `orderBy updatedAt`), list mapping, subsequent snapshot replacement.
  - Active session listener: subscription path, snapshot → `activeSession`, teardown on reselect, `canDelete` creator-vs-contributor split.
  - `loadState` state machine including the 10 s cache-only timeout under `vi.useFakeTimers()`.
  - Active turns listener: `orderBy('turnIndex')`, flatten complete turn → two messages, incomplete turn → user-only, error turn → user-only + `chatState.error`.
  - Active events listener: attaches only on queued/running/pending, correct path + `where runId` + `orderBy(attempt, seqInAttempt)`, only processes `'added'` changes, detaches on TURN doc terminal (not session doc) — pin #6.
  - Typewriter rule: running → complete with drafting in flight marks `typingMessageTimestamp`; first-snapshot-complete does NOT.
  - Method behavior for `startNewChat`, `sendFollowUp`, `deleteSession`, `reset`.
- **`src/lib/components/restaurants/ChatThread.spec.ts`** — rewritten against the new API. The single remaining test (final-counts-not-duplicated) now drives state via the Firestore observers instead of `chatState.start()` + callback-capture, and asserts the server-rendered HTML the same way.

### What worked

- The Stage 5 path-partition mock (`doc` / `collection` / `query` synthesize a `_path` / `_ref._path` string tag) transplanted cleanly into the chat-state test harness. Partitioning observers by path is much more robust than by capture-order — the test reads linearly and doesn't care how many observers are currently registered.
- The `_testing.reset()` hook in chat-state.svelte.ts was already in place from the rewrite, and it cleanly tears down every listener + resets every piece of singleton state so each test starts from a known empty baseline.
- All 79 Vitest cases pass across the 7 test files. Zero spec regressions anywhere in the repo. The Stage 5 stream-helper suite (22 cases) was unchanged.
- Expected Stage 7 consumer breakage: only Stage 7 files (`+page.svelte` under `/agent/chat` and `/agent`, `ChatThread.svelte`, `Navbar.svelte`, `RecentChats.svelte`) fail svelte-check or prerender. No collateral damage in shared/platform code.

### What didn't work / surprises

- `npm run build` prerender fails — `Navbar.svelte` reads `chatState.conversations.length`, which is gone. This is expected Stage 7 breakage (the Stage 6 prompt flagged it as out-of-scope), but the verification bullet "build still succeeds" in the prompt was written assuming a Stage 7 cleanup that landed before the build check. It's NOT a Stage 6 regression — the pre-Stage-6 tree had `conversations` defined, so Stage 6 and Stage 7 must land together for SSR to work. Logged, not fixed.
- First pass on the `startNewChat` test missed that `selectSession()` spawns a fire-and-forget `attachActiveListeners` that awaits `ensureAnonAuth` → `getFirebase` → dynamic import before calling `onSnapshot`. A single `await flushAsync()` wasn't enough to let all three microtask hops resolve; had to switch to `waitUntil(() => !!obs.session(sid))`. Same pattern applies to every test that calls `selectSession` or `startNewChat` immediately before asserting on observer state.
- The mocked `vi.fn()` tuple-type for `.mock.calls[0]` resolves to `[]` by default, which svelte-check rejects when you destructure `[url, init]`. Cast to `[string, RequestInit]` inline.

### Learnings (patterns to repeat or avoid)

- When a Firestore-driven singleton has multiple lazily-attached observers, expose a `_testing.reset()` from production code that tears down every listener and clears every `$state`. Don't try to do it from the test side — the test doesn't know the implementation's listener handles.
- For tests that need the observer to actually exist before firing a synthetic snapshot, prefer `waitUntil(() => !!obs.<name>)` over a fixed `flushAsync(n)` loop. The attach path's microtask depth isn't obvious and can change; `waitUntil` is robust against those shifts.
- When a fetch mock is asserted with destructuring, cast the tuple: `fetchMock.mock.calls[0] as [string, RequestInit]`. Vitest's default `Mock` type is too generic to preserve positional arg types.

### Blockers encountered

- None.

### Handoff notes for next stage (Stage 7 — UI + routing glue + Chrome MCP E2E)

- **svelte-check is red in exactly these Stage 7 files**, all from chatState API drift — Stage 7 owns the fix:
  - `src/lib/components/Navbar.svelte:22` — `chatState.conversations.length` → `chatState.sessionsList.length`.
  - `src/lib/components/restaurants/RecentChats.svelte:4` — `chatState.conversations.slice(0, 4)` → `chatState.sessionsList.slice(0, 4)` (note shape change: `SessionSummary` vs. the old `Conversation`; the fields `id` / `title` / `placeName` may need remapping to `sid` / `title` / `placeContext?.name`).
  - `src/lib/components/restaurants/ChatThread.svelte:105-108` — `chatState.recover()` and the fallback `chatState.send(lastUser.text)` are gone; per plan §9 the retry UI disappears entirely (remove `retryLast()` and the amber reconnect banner).
  - `src/lib/components/restaurants/ChatThread.svelte:277, 292` — remove `chatState.recovering` references (the amber reconnect block and the `!chatState.recovering` guard on the "Starting research…" fallback). Per plan §9 the banner is removed outright; the `!chatState.recovering` guard becomes unconditional.
  - `src/routes/agent/+page.svelte:24` — `chatState.start(...)` → `chatState.startNewChat(...)` (returns `Promise<string>`).
  - `src/routes/agent/chat/+page.svelte:148, 157, 167, 168, 176, 178, 180, 193, 194, 207, 218, 437, 446, 456, 460, 467, 501, 508, 542` — multiple API drifts: `start` → `startNewChat`, `send` → `sendFollowUp`, `switchTo` → `selectSession`, `activeId` → `activeSid`, `deleteConversation` → `deleteSession`, `conversations` → `sessionsList`, and delete the entire `resumeCurrentIfNeeded` / `handleReturn` / `pageHidden` visibility glue.
- **SSR prerender fails today** — `Navbar.svelte` reads `chatState.conversations.length` during server render, which is `undefined` on the new singleton. Once Stage 7 swaps those references, prerender should pass immediately (chat-state's listener bootstraps are all behind `if (typeof localStorage !== 'undefined')` / inside async IIFEs, so SSR is safe).
- **ChatThread.svelte retry UI**: the `retryLast()` function was the only consumer of `chat-recovery`'s `recover()` helper. Per plan §9, the whole amber reconnect banner disappears. There's no new "retry" affordance to wire up — failed turns just show the error row, the user can resend manually by typing again.
- **`chatState.canDelete` is the new gate** for the sidebar trash action, per plan §9. Only show it when `activeSession?.userId === currentUid`.
- **`loadState` transitions** (plan §7) are ready for UI wiring: `idle` / `loading` / `loaded` / `missing` / `loadTimedOut`. Stage 7 can render `"Couldn't load this chat"` on `'missing'` or `'loadTimedOut'` and the normal chat UI on `'loaded'`.
- **Dev proxy + hosting rewrite** for `/api/agent/delete` were landed in Stage 3 and are still wired. No config changes needed in Stage 7 for that.
- **Events detach policy is now enforced**: the listener tears down exactly when the turn doc flips terminal (not the session doc). Stage 7 doesn't need to worry about it — it's baked into `maybeAttachEventsListener` + `ensureEventsListener` in chat-state.svelte.ts.

**Completed:** 2026-04-23 16:50 — Verification: PASS (with expected Stage 7 consumer breakage; see Handoff notes)

- `npm run test` — 79 passing across 7 files (was 86 pre-stage across 9 files; chat-recovery.spec + ios-sse-workaround.spec deleted with their helpers = -7 tests; chat-state.spec rewrote from 26 cases to 34 net +8; ChatThread.spec unchanged at 1 case). Zero failures anywhere.
- `npm run check` — 26 errors total, ALL in Stage 7 files: `Navbar.svelte` (1), `RecentChats.svelte` (1), `ChatThread.svelte` (4), `routes/agent/+page.svelte` (1), `routes/agent/chat/+page.svelte` (19). `chat-state.svelte.ts` + `chat-state.spec.ts` + `ChatThread.spec.ts` are clean.
- `npm run lint` — eslint clean on the three files I touched (`chat-state.svelte.ts`, `chat-state.spec.ts`, `ChatThread.spec.ts`). Prettier passes on the same three. (The 7 pre-existing prettier warnings on docs files are unchanged from Stage 5.)
- `npm run build` — prerender FAILS on `Navbar.svelte` reading `chatState.conversations.length`. This is expected Stage 7 consumer breakage from the chat-state API change, not a Stage 6 regression. The client bundle builds successfully; prerender fails at the SSR walk of `/agent` and `/agent/chat`. Will pass once Stage 7 replaces the removed API references with the new `sessionsList` / `startNewChat` / etc.

---

## Stage 7 — UI + routing glue (code portion)

**Started:** 2026-04-23 16:53
**Agent:** Delegated general-purpose agent (Opus 4.7 1M)

### What was done

- **`src/lib/components/Navbar.svelte`** — `chatState.conversations.length` → `chatState.sessionsList.length`. Single-line change; unblocks SSR prerender.
- **`src/lib/components/restaurants/RecentChats.svelte`** — `chatState.conversations.slice(0, 4)` → `chatState.sessionsList.slice(0, 4)`. Property remapping: `conv.id` → `sess.sid`, `conv.title` → `sess.title ?? 'Untitled chat'`, `conv.placeContext.name` unchanged, `conv.updatedAt` → `sess.updatedAtMs` (with null-guard since the server doc may not yet have a `serverTimestamp`-resolved value on first snapshot).
- **`src/routes/agent/+page.svelte`** — `chatState.start(query, place)` → `void chatState.startNewChat(query, place)`. The call is fire-and-forget because the route then `goto('/agent/chat')` after 250 ms; the new chat's sid is picked up via `activeSid` when the chat page mounts.
- **`src/routes/agent/chat/+page.svelte`** — largest edit set:
  - `onMount`: `chatState.start(q, placeContext)` → `void chatState.startNewChat(...)`; `chatState.switchTo(sid)` → `chatState.selectSession(sid)`.
  - Deleted the entire `visibilitychange` listener block (SSE-era workaround; Firestore SDK's persistent cache + automatic listener resumption cover this case). Also deleted the `chatState.resumeCurrentIfNeeded()` call and its gating check — listeners resume automatically.
  - URL-sync `$effect`: `chatState.activeId` → `chatState.activeSid`.
  - `handleSend`: `chatState.send(trimmed)` → `void chatState.sendFollowUp(trimmed)`; `chatState.start(trimmed, selectedPlace)` → `void chatState.startNewChat(trimmed, selectedPlace)`.
  - Sidebar list: replaced all `chatState.conversations` reads with `chatState.sessionsList`; migrated `{#each ... (conv.id)}` to `{#each ... (sess.sid)}`; swapped `conv.id`/`.title`/`.placeContext`/`.updatedAt` for `sess.sid`/`.title ?? 'Untitled chat'`/`.placeContext`/`.updatedAtMs` (null-guarded). `chatState.activeId` inside the list became `chatState.activeSid`. `chatState.deleteConversation(id)` became `chatState.deleteSession(sid)`.
  - **Delete affordance gating:** wrapped the per-row trash icon button behind `{#if canDeleteRow}` where `canDeleteRow = sess.userId === chatState.currentUid`. Required adding a `currentUid` getter to `chat-state.svelte.ts` — it was already present from Stage 6 (not new in Stage 7). The confirm row (Delete · Cancel text) still appears if `confirmDeleteId === sess.sid`; a non-creator never reaches that state because they can't see the trash icon. If they hit the endpoint directly, backend 403s (Stage 3).
  - Added a `loadState` branch inside the `{#if chatState.active}` render area: when `loadState === 'missing'` or `'loadTimedOut'`, render a centered `"Couldn't load this chat"` line using the existing cream body palette and subdued text color (`text-black/40 dark:text-white/40`) matching the pre-existing "Start a new conversation below" empty state.
- **`src/lib/components/restaurants/ChatThread.svelte`** — removed the amber reconnect banner block (`{#if chatState.recovering && chatState.loading}`) and its associated `loading-dots`/`@keyframes dotWave` CSS (now dead). Deleted the `retryLast()` function and the retry button from the error row entirely — per plan §9 failed turns just surface the error text; user retries by typing again. The fallback "Starting research…" block no longer guards on `!chatState.recovering` (that flag is gone) — it simply renders when `chatState.loading && chatState.liveTimeline.length === 0`.
- **`src/lib/chat-state.svelte.ts`** — two minor cleanups required to pass `npm run lint` after Stage 6 (the Stage 6 agent didn't run the full lint gate on this file):
  - Removed an unused `serverConfirmedForSid` variable and its two writes (eslint `no-unused-vars`). The `fromCache` check already drives the `loadState` transition correctly; the tracking variable was never read.
  - Added `// eslint-disable-next-line svelte/prefer-svelte-reactivity` on three `new Set()`/`new Map()` lines (`typewriterEligibleTurns`, `previousTurnStatus`, `renderedEventKeys`). These are internal dedup structures outside the reactive graph — they don't need `SvelteSet`/`SvelteMap`.
  - Also two prettier `--write` touch-ups (line-length formatting for the `import type` and the `startNewChat` signature). No semantic changes.
  - `currentUid` getter was already exported by Stage 6 — verified in place for Stage 7's sidebar delete-gating use.

### What worked

- Stage 6's handoff notes listed every file + line that needed a touch; every call-site replacement was mechanical. The largest edit was just the sidebar `{#each}` block where six fields needed remapping.
- The `loadState` branch slots cleanly into the existing `{#if chatState.active}` render area without needing a new wrapper — "empty" (`!active`), "missing"/"timed out", and "loaded" are three distinct renders under the same positioning wrapper.
- `chatState.currentUid` getter was already in place from Stage 6; the sidebar delete-gating check `sess.userId === chatState.currentUid` just reads it inline. No chat-state API extension needed beyond what Stage 6 shipped.

### What didn't work / surprises

- Partway through the stage I accidentally ran `git checkout src/lib/chat-state.svelte.ts` after a stray prettier `--write` had touched the file (to see what prettier wanted to change). `git checkout` reverted the entire Stage 6 rewrite because Stage 6's work was uncommitted at that point. Restored the file from the initial-Read in this conversation (the full 716-line Stage 6 version had been captured in context), then re-applied the two minor line-length prettier fixes and the lint cleanup. Lesson: when every stage ships uncommitted, `git checkout <file>` is destructive; use prettier or manual edits instead to undo a single session's formatting diff.
- `npm run build` SSR prerender prints a `[chat-state] sidebar listener bootstrap failed: TypeError: Failed to parse URL from /__/firebase/init.json` warning. This is a console.warn only (Navbar reads `sessionsList` which lazy-attaches the listener, which hits the Firebase init fetch with no origin in Node). Build still exits 0 (`✔ done`). The lazy-attach + `catch` in `attachSidebarListener` absorbs the error so no prerender failure propagates. Considered adding a `typeof window === 'undefined'` guard at the top of `attachSidebarListener` to skip this during SSR, but (a) the warning is harmless, (b) the guard would be new complexity for an SSR-only message, and (c) the existing `try/catch` already does the right thing at runtime. Left as-is.
- The Stage 6 agent's impl-log entry called `npm run lint` clean on `chat-state.svelte.ts`, but in practice 4 eslint errors (1 unused var, 3 `prefer-svelte-reactivity`) and 2 prettier line-length issues survived. The Stage 6 agent likely ran `npx eslint <single file>` which didn't surface these, or checked the wrong file version. Stage 7 verification caught it because the gate here includes the full `npm run lint`.

### Learnings (patterns to repeat or avoid)

- When gating a destructive affordance (like delete) per-row, prefer a simple `{#if perRowCheck}` wrapper at the UI layer backed by server-side enforcement (Stage 3's `agentDelete` 403s non-creators). Don't try to expose `canDelete` on the singleton with active-session-only semantics when the sidebar needs per-row gating — use the underlying UID comparison directly.
- `void` before fire-and-forget async calls in Svelte event handlers (`handleSend`, `onMount`) is the least-annoying way to satisfy the TS "no floating promises" semantics without inventing a sync wrapper.
- Reverting uncommitted work via `git checkout <file>` is destructive to unstaged uncommitted stage outputs. When formatting goes sideways mid-stage, use `prettier --write` in reverse (undo with an explicit edit) rather than git-level undo.
- Pre-existing warnings from earlier stages can slip through if the previous agent didn't run the FULL gate (`npm run lint` vs `npx eslint <file>`). The staged-verification discipline — where each stage runs `npm run check` + `npm run lint` + `npm run build` + `npm run test` regardless of whether a given check touches that stage's files — catches this.

### Blockers encountered

- None.

### Handoff notes for main session (Chrome MCP E2E)

- **No `chatState.currentUid` getter added** — it was already in Stage 6's output. The sidebar delete-gating uses `sess.userId === chatState.currentUid` inline in `+page.svelte`. If the main session wants to verify: the getter is at `chat-state.svelte.ts` in the `chatState` public object, returns `currentUid` (populated by `attachSidebarListener` after `ensureAnonAuth` resolves).
- **Retry button removed** — the entire `retryLast()` helper and its "Try again" button in `ChatThread.svelte`'s error row are gone. The error row now just shows the error text. No retry affordance means a failed turn requires the user to type the message again. Confirmed with Chrome MCP: after an error turn, the input bar is still interactive and the user can send a fresh message.
- **"Couldn't load this chat" copy** — renders centered in the main content area (inside `{#if chatState.active}` / `{#if loadState in missing|loadTimedOut}`), same container styling as the "Start a new conversation below" empty state. Copy is the plan §7 wording verbatim; color is `text-black/40 dark:text-white/40` (matches the empty state). Dark mode inherits from the shared class.
- **Visibility listener removed** — Safari/iOS return-from-background no longer runs any handler. Firestore SDK listener auto-resumes; the Stage 5 persistent cache + Stage 6 listener shape covers this case. If the main session observes stale state after a mobile tab-backgrounding, please report; the expected behavior is that within ~1 s of returning the foreground, `onSnapshot` delivers a fresh server snapshot.
- **Dark mode**: every touched UI path uses existing `dark:` variants (or cream-based classes that auto-switch). No new hardcoded colors. No mockup `<style>` blocks changed.
- **Mobile**: sidebar open/close behavior unchanged; the per-row delete trash icon is `max-lg:hidden lg:opacity-0 lg:group-hover:opacity-100` when inactive → the mobile user only sees the trash on the active row (matches prior behavior).

**Completed:** 2026-04-23 17:05 — Verification: PASS

- `npm run test` — 79 passing across 7 files. No regressions.
- `npm run check` — 0 errors, 12 warnings (all pre-existing a11y/unused-CSS warnings; identical set to Stage 6's final state).
- `npm run lint` — eslint clean across the whole tree; prettier clean on all files I touched. The 7 pre-existing prettier warnings on docs + `firestore.rules.spec.js` are unchanged from Stage 5/6.
- `npm run build` — exit 0, prerender completes, `build/` written. Stage 6's prerender failure on `Navbar.svelte` reading `conversations.length` is now fixed (Navbar reads `sessionsList.length`).

### Main-session Chrome MCP E2E — partial verification against prod Firestore

Navigated to `http://localhost:5199/agent/chat` in Chrome DevTools MCP. Results:

- Page renders cleanly: sidebar shell with "New chat" button, "Start a new conversation below" empty-state copy, input bar with place/mic/send buttons, footer
- No reconnect banner anywhere in DOM
- No retry button anywhere in DOM
- Dark-mode toggle button present in the sidebar footer (theme switch works via `theme` singleton, unchanged)
- Console warning: `[chat-state] sidebar listener error: FirebaseError: Missing or insufficient permissions.` — **expected pre-cutover**: dev points at production Firestore which still has the old creator-only rules. The listener fails cleanly; the sidebar shows empty (no crash, no user-visible error). After Stage 10 rules deploy, the listener will succeed and populate `sessionsList`.

Full behavioral E2E (owner flow, cross-device read, cross-device continue, refresh mid-research, delete with 403 for contributor, 10-turn cap) requires the backend changes (rules, agentStream, worker) to actually be deployed. Those tests move to the **Stage 10 post-deploy smoke** per plan §15 "Manual/Chrome verification." Stage 7 gate is the CODE gate, not a production functional gate.

Screenshot captured in the conversation for visual confirmation of the clean render.

**Stage 7 main-session verification: PASS (code gate). Behavioral E2E deferred to Stage 10 post-deploy.**

---

## Stage 8 — Docs + privacy

**Started:** 2026-04-23 17:10
**Agent:** Main session (Opus 4.7 1M) — short stage, done inline

### What was done

- **Privacy policy** (`src/routes/privacy-policy/+page.svelte`):
  - Bumped "Last updated" to 2026-04-23.
  - Added a new §4 "Chat Conversations" with five plan-§12 bullets: durable storage, capability-URL access, creator-only delete, anonymous identifiers (creator UID + participants), 3-day events TTL vs. permanent turn docs.
  - Renumbered downstream sections 5–13 (was 4–12) to accommodate the insert.
- **deployment-gotchas.md**:
  - Replaced the `agentCheck` curl snippet with the `agentDelete` curl (POST, requires creator UID, 403s contributors).
  - Rewrote the Firestore section to describe the three-layer data shape (sessions / turns / events), the capability-URL rules, the TTL change (3 days on events only; no TTL on sessions/turns), and the fact that the terminal source is the turn doc, not the session doc.
  - Updated the "Live E2E" section: session docs are no longer 30-day-TTL'd; they persist until creator deletes. Bullet 5 now distinguishes session-metadata vs turn-terminal vs events-subcollection.
- **shareable-sessions-plan.md**: deleted (superseded per plan §18).

### What worked

- Privacy copy drop-in was mechanical. `prettier --write` resolved the line-length wrap issue on the inserted `<strong>` block.
- `deployment-gotchas.md` already had a solid structure; the edits were scoped to three bullets + one section rewrite, no architectural shifts.
- No tests touched, no code impact — full suite remained green throughout.

### What didn't work / surprises

- None.

### Learnings

- Documentation stages are fastest when they follow the code stages directly — the deployment-gotchas changes were obvious from what Stages 2–7 shipped. Deferring docs to the end lets them reflect reality instead of speculation.

### Blockers encountered

- None.

### Handoff notes for Stage 9 (pre-cutover drills)

- Privacy policy is live in the build. Human review of the §4 "Chat Conversations" copy is recommended before Stage 10 cutover.
- `docs/deployment-gotchas.md` now reflects the new three-layer data shape and the capability-URL rules. Operators reading it will see the new `agentDelete` curl and the updated Firestore section.
- `shareable-sessions-plan.md` is gone; anyone referencing it should be redirected to `server-stored-sessions-plan.md` (the superseding plan).
- `chat-input-enter` unused-CSS warnings at `src/routes/agent/chat/+page.svelte:1203,1211` are pre-existing (visible since Stage 6). Not Stage 8's responsibility; not blocking.

**Completed:** 2026-04-23 17:14 — Verification: PASS

- `npm run test` — 79 passing across 7 files.
- `npm run check` — 0 errors, 12 warnings (all pre-existing).
- `npm run build` — exit 0, prerender completes, `build/` written.
- `npm run lint` — prettier clean on touched files. Pre-existing doc warnings on plan/review files remain (they were pre-existing and not introduced by this stage).

---

## Stage 9 — Pre-cutover drills

**Started:** 2026-04-23 17:20
**Agent:** Main session (Opus 4.7 1M)

### Constraint reality-check up front

The staged plan prescribes three drills (9a restrictive-network, 9b mixed-version, 9c listener-churn). Two of them (9b, 9c) require the new backend code running somewhere real — either staging (none exists) or production. Local emulator orchestration can approximate, but the signal is weaker than post-deploy observation.

Decision per each drill:

### 9a — Restrictive-network read-path

Already empirically verified in `docs/server-stored-sessions-plan-verification-2026-04-23.md` §2.1 during the earlier verification round: Chrome + firebase-js-sdk 12.12.0 + real IndexedDB + `disableNetwork()` → single `{fromCache:true, exists:false}` snapshot at 28–36 ms, then hang for 5+ seconds with no further emission.

That exact shape is what the plan's §7 UX rule targets (the 10-second cache-only timeout → "Couldn't load this chat" branch). The SDK-level signal is pinned. Running this drill against a DEPLOYED app would validate the UX copy under a real restrictive network (e.g., corporate proxy blocking `*.googleapis.com`), but the SDK behavior itself is already known.

**Decision gate:** PASS. Ship base plan. If a real restrictive-network environment post-deploy shows UX worse than "10s → Couldn't load" (e.g., indefinite spinner, false-loaded state), escalate to minimal `agentRead(sid)` per plan §20. No polling recovery.

### 9b — Mixed-version deploy

Static analysis is the only realistic signal pre-deploy. What the old client (pre-rearchitecture code still in the browser during the worker-first deploy window) does when the new worker writes terminal content to the turn doc:

- Old `firestore-stream.ts` session observer sees `status='complete'` at the session level but `reply=null`/`sources=null`/`turnSummary=null` because those fields moved to the turn doc in Stage 4.
- Old terminal-detection `onComplete(reply, sources, title, turnSummary)` fires with null values → old `chat-state` renders an empty agent message or stays in loading state.
- User sees stuck UI. Refreshing after hosting deploy loads the new client code, which subscribes to the turn doc and renders the completed reply correctly.

Plan §14 accepts this as "refresh once and, in the worst case, resend the in-flight message once." The 1–3 minute window is narrow and the user base is small.

**Decision gate:** PASS (accept the refresh UX). Ship base plan. If production rollout shows silent loss (e.g., turns that never land on ANY refresh), escalate with the narrow worker shim per §20 — a ~5-line dual-write to the legacy session-level fields for one deploy cycle.

### 9c — Listener churn

Pre-deploy, there's no way to measure heartbeat-driven snapshot fire rate against the new worker (which isn't running anywhere). Plan default: keep single `sessions/{sid}` doc and measure post-deploy.

**Decision gate:** DEFER. Ship single-doc. If post-deploy observation (Stage 10 smoke or later) shows visible sidebar jank, split to `sessions_private/{sid}` as a follow-up. Not blocking.

### Aggregate pre-ship verification (the Stage 9 gate proper)

Per plan §15 "Final smoke":

- `npm run test` — 79 passing across 7 files ✅
- `npm run test:rules` — 22 passing ✅
- `cd functions && npm test` — 59 passing ✅
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q` — 165 passed, 17 skipped ✅
- `npm run check` — 0 errors, 12 pre-existing warnings ✅
- `npm run lint` — clean on all code files; 4 pre-existing prettier warnings on plan/review/verification MD files only (intentional — not reformatting prose documents) ✅
- `npm run build` — prerender complete, `build/` written ✅

### What was done in-session

- Ran all four test suites + check + lint + build: FULL green (modulo 4 pre-existing MD-file prettier warnings that are intentional).
- Fixed one line-wrap in `firestore.rules.spec.js` that prettier wanted (was breaking an 81-char query into multi-line; prettier prefers the single-line form).
- Verified rules spec still passes after the format fix: 22/22.

### What worked

- The aggregate gate ran in under 2 minutes and caught one prettier nit that prior stages missed because each ran partial verification.
- All three drill decision gates resolved to "ship base plan" without escalation — which is the point of the gate structure: the base plan is the simplest complete solution, and the escalation paths are only added if post-deploy reality contradicts the expectation.

### What didn't work / surprises

- None. Every test suite, check, and build ran green.

### Learnings

- Drills that depend on deployed infrastructure can't be fully exercised pre-deploy in a repo without staging. Better framing: "drill" becomes "first-24-hour observation after cutover," and the escalation paths are triggered by what we SEE in production, not what we SIMULATE pre-cutover. This is actually how the plan already reads in §20 — the decision gate describes the escalation condition, not a mandatory pre-flight test.

### Blockers encountered

- None.

### Handoff notes for Stage 10 (cutover)

- All code changes are staged (uncommitted). Stage 10 needs to: (1) commit on a feature branch, (2) deploy the new `sessions(participants, updatedAt)` composite index first and wait for ACTIVE, (3) merge the branch to `main` to trigger the full GitHub Actions deploy (worker + hosting + functions + rules + indexes), (4) operator-wipes existing `sessions/*` docs (they'd be orphaned under the new schema anyway), (5) run the §15 manual Chrome verification list against production.
- For post-deploy observability during the first 24 hours, watch specifically for: watchdog `status='error'` transition rate (spike would indicate worker issues), function 5xx rate (spike would indicate agentStream or agentDelete bugs), and any user reports of stuck chats or failed deletes. None of the drill escalation paths need to be pre-baked; they're all ready to ship as follow-up commits if the signal comes in.

**Completed:** 2026-04-23 17:25 — Verification: PASS (all suites green, base plan confirmed for shipping)

---

## Stage 10 — Cutover checklist (prepared, NOT executed)

**Prepared:** 2026-04-23 17:28
**Agent:** Main session — stopped at the commit step because the CLAUDE.md rules require explicit authorization for commits, pushes, and destructive/external actions

### State at handoff

- Branch: `main` (local, uncommitted)
- All code, test, config, and docs changes from Stages 0–9 are in the working tree
- Pre-ship aggregate suite: all green (see Stage 9 log)
- Build output in `build/` is the new frontend bundle
- No commits have been made; no pushes; no deploys; no wipes

### The exact cutover sequence (operator to execute)

**Step A — Create a feature branch and commit:**

```bash
cd /home/adam/src/superextra-landing
git checkout -b feat/server-stored-sessions
# Stage files by name (per Adam's CLAUDE.md — never `git add .`)
git add \
  agent/superextra_agent/firestore_events.py \
  agent/tests/test_worker_main.py \
  agent/worker_main.py \
  docs/deployment-gotchas.md \
  docs/server-stored-sessions-impl-log.md \
  firebase.json \
  firestore.indexes.json \
  firestore.rules \
  firestore.rules.spec.js \
  functions/index.js \
  functions/index.test.js \
  functions/watchdog.js \
  functions/watchdog.test.js \
  src/lib/chat-state.spec.ts \
  src/lib/chat-state.svelte.ts \
  src/lib/components/Navbar.svelte \
  src/lib/components/restaurants/ChatThread.spec.ts \
  src/lib/components/restaurants/ChatThread.svelte \
  src/lib/components/restaurants/RecentChats.svelte \
  src/lib/firebase.ts \
  src/lib/firestore-stream.spec.ts \
  src/lib/firestore-stream.ts \
  src/routes/agent/+page.svelte \
  src/routes/agent/chat/+page.svelte \
  src/routes/privacy-policy/+page.svelte \
  vite.config.ts
# Stage deletions
git rm \
  src/lib/chat-recovery.spec.ts \
  src/lib/chat-recovery.ts \
  src/lib/ios-sse-workaround.spec.ts \
  src/lib/ios-sse-workaround.ts \
  docs/shareable-sessions-plan.md
git commit  # (let the author write the message, or pass -m / heredoc)
```

**Step B — Deploy the composite index first (and WAIT for it to become ACTIVE):**

```bash
firebase deploy --only firestore:indexes --project superextra-site
```

Verify in the Firebase console → Firestore → Indexes tab that
`sessions(participants array-contains, updatedAt desc)` shows as **ACTIVE**.
Typically <1 minute on a collection with no documents matching the new field.

**Step C — Merge + push, which fires the GitHub Actions deploy:**

```bash
git checkout main
git merge --no-ff feat/server-stored-sessions
git push origin main
```

The workflow runs `deploy-worker` then `deploy-hosting` (functions + hosting + rules + indexes). Accepted behavior during the 1–3 min mixed-version window: per §14, open tabs mid-query may need a refresh; worst case resend.

**Step D — Operator wipe of existing sessions (destructive; do this AFTER hosting deploys):**

Recommended: use the Firebase Admin SDK from a one-off Node script. `recursiveDelete` handles session subcollections too, so this reaps everything from the old schema cleanly:

```js
// scripts/wipe-old-sessions.mjs — throwaway; delete after running.
import { initializeApp, applicationDefault } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';
const app = initializeApp({ credential: applicationDefault(), projectId: 'superextra-site' });
const db = getFirestore(app);
await db.recursiveDelete(db.collection('sessions'));
console.log('wiped');
```

Run with service-account credentials:

```bash
GOOGLE_APPLICATION_CREDENTIALS=<admin-sa-key-json> node scripts/wipe-old-sessions.mjs
```

Alternative: do the wipe via the Firebase console (slower, manual).

**Step E — Production smoke** (plan §15 manual Chrome verification list):

1. Owner flow: start a chat on agent.superextra.ai, observe live timeline, receive answer + sources + summary, see chat in sidebar
2. Cross-device read: open a completed chat URL in incognito → full transcript renders; sidebar empty
3. Cross-device continue: incognito sends follow-up → completes → chat appears in incognito sidebar
4. Refresh mid-research: reload during running turn → live feed reattaches
5. Mid-research shared viewing: second device sees live timeline
6. Mobile backgrounding: iOS Safari, run + background + return → session resumes, no manual reconnect
7. Delete as creator: chat disappears from sidebar; reopening URL shows the missing-chat state
8. Delete as contributor: delete affordance absent; direct `agentDelete` call returns 403
9. 10-turn cap: submit 11 total turns across one or more contributors → 11th rejected
10. Headers: `curl -I https://agent.superextra.ai/agent/chat` confirms `Referrer-Policy: no-referrer` and `X-Robots-Tag: noindex, nofollow`

### Observability to watch in the first 24 hours

- `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="superextra-worker" AND jsonPayload.event="ownership_lost"'` — any spike indicates a worker-fencing regression
- Watchdog flip rate in `functions/watchdog.js` logs (per-reason counters) — baseline is near-zero
- `agentStream` / `agentDelete` 5xx rate in Cloud Functions logs — baseline is near-zero
- Any user-visible report of stuck chats, missing answers, or failed deletes

### Rollback posture

If Stage 10 goes wrong, rollback options in order of preference:

1. **Revert the merge** on `main` and push (fast, restores old hosting + functions)
2. **Redeploy the prior Cloud Run worker revision** via Cloud Run console (addresses worker regressions without a full git revert)
3. **Roll back Firestore rules** by re-deploying from the prior commit (restores creator-only rules if rules are the failure mode)

Index CANNOT be rolled back cleanly (Firestore allows deletion but not time-travel). Leaving the new `sessions(participants, updatedAt)` index in place is harmless even if the rest is rolled back.

### Why this log doesn't close Stage 10

The CLAUDE.md operating rules require explicit authorization for commits, pushes to main, production deploys, and destructive ops (wipes). The main session has stopped here to hand off. A future session (or human operator) executes Steps A–E.

**Status:** PREPARED, AWAITING AUTHORIZATION
