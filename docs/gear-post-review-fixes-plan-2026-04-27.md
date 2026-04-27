# Plan: post-review fixes + remaining steps for the GEAR migration

## Context

The gear-migration branch has 10 commits ahead of main and all four test suites green. Two reviewers (R1 and R2) inspected the branch and found no P0/P1 architecture blockers — they agree the migration is sound — but surfaced a focused set of fixes that should land before Phase 8 staging deploy.

The reviewers disagreed on two items:

- **Probe Cloud Functions cleanup.** R1: P1, before main PR. R2: defer to Phase 9. → R1 wins. The `probeHandoffAbort` and `probeHandoffLeaveOpen` exports in `functions/index.js:773-784` have no `verifyIdToken` check (verified vs. `agentStream:215` which does), reference a hardcoded probe Reasoning Engine resource, and `probeHandoffLeaveOpen` is documented as undefined behavior per Firebase docs. Leaving public unauthenticated billable endpoints alive through a 30-day Phase 9 window is the wrong trade.
- **finalize() crash handling.** R1: P2, fix now. R2: defer (watchdog catches). → R1 wins. `firestore_progress.py:435-441` returns without a terminal write on finalize crash; watchdog catches the stuck `running` at 5 min via `pipeline_wedged`. UX cost of deferring is a 5-minute "researching..." hang on a turn whose answer is already in process memory. Fix is ~10 LOC.

Plus eight smaller items where both reviewers agreed (or only one raised them):

- agentStream gear-branch is fully untested at integration level (R1 P2 + R2 must-fix #2).
- `chooseInitialTransport` and the v3.9 P1 legacy-session preservation have zero coverage.
- The shared AbortController's deadline-fires-abort path is partially uncovered (only signal identity is asserted under happy path).
- Chat-state spec has a documented gap on the post-Firestore-failure branch (vi.mock dynamic-import resolution issue).
- `gear_run_state.py:301` swallows `asyncio.CancelledError` (R2 must-fix #4) — blocks asyncio shutdown propagation.
- `places_tools.py:57-59` logs a misleading import-time "GOOGLE_PLACES_API_KEY not set" warning under GEAR (env unset, Secret Manager has it).
- Plan §"Cross-cutting" called for a 3s rollback timer; the actual code uses the existing 10s `LOAD_TIMEOUT_MS`. The deviation is correct (3s would false-positive against gearHandoff's 75s first-NDJSON-line deadline) but isn't documented.
- CLAUDE.md mandates a browser smoke for UI changes; vitest can't observe the visual flicker that Phase 6 fixes.

The plan organises the work into three logical commits, then a Chrome DevTools MCP smoke, then hand-off to Adam for Phase 1 cloud commands and Phase 8 staging deploy.

### Round-2 review feedback integrated (2026-04-27)

Two further reviewers (F1, F2) approved the plan directionally and added these tightenings — all rolled into the sections below:

- **Commit 3 grew two items.** Narrow `ALREADY_EXISTS` to `r.status === 409 && body.includes('ALREADY_EXISTS')` (F1 + F2 — guards the theoretical case of a quota-error body containing the substring). Drop the `__post_init__` `RuntimeError("requires fs")` defensive raise in `gear_run_state.py` (F1 + F2 — no verified failure mode; lean covenant says remove). Both fit the spirit of "post-review reliability + UX hygiene".
- **finalize_failed write wraps `_retry_critical`** (F2 P2). The plan's direct call would skip the existing transient-retry semantics that every other terminal write uses. No new abstraction.
- **`test_finalize_propagates_cancellation` is mandatory** (F2 P3). One-line code change but subtle behavior; existing GearRunState test fixtures make the test cheap.
- **Test seams hardened** (F2 P1 × 2). `mock.module('./gear-handoff.js', ...)` MUST sit at file scope before `await import('./index.js')` — putting it inside `describe('agentStream')` is too late because index.js already captured the real import. And `chooseInitialTransport` becomes `chooseInitialTransport(uid, allowlist = GEAR_ALLOWLIST, defaultTransport = GEAR_DEFAULT)` so Test 5 covers the `GEAR_DEFAULT`-flipped scenario via parameters rather than mutable module state.
- **Deadline seam: explicit parameter, not env var** (F2 P2 vs. F1 minor). `gearHandoff({ ..., deadlineMs = HANDOFF_DEADLINE_MS })`. Avoids the hidden production knob + import-cache complexity an env-var override would create. F1's "matches `GEAR_REASONING_ENGINE_RESOURCE` pattern" is overweighted — that env var is genuine deploy-time config; the deadline override is purely a test seam.
- **`resetGearAllowlist()` exported helper** (F1 minor). Avoids cross-test pollution if any case forgets to `.clear()`.
- **Test 8 fallback hardened** (F1 minor). If `vi.mocked` still doesn't propagate to chat-state's dynamic import, switch to a manual Chrome MCP recipe (force offline mid-POST) instead of skipping. The v3.9 P2 catch branch is real regression surface.
- **Commit 1 grep tightened** (F1 minor). Verification scope is `functions/`; `agent/probe/run_r32.py` retains URL references (expected, slated for Phase 9 archival).

## Commit 1 — `chore(gear): remove R3.2 probe diagnostic Cloud Functions`

**Files**:

- `functions/index.js` — delete the entire R3.2 diagnostic block at lines 644-787:
  - Block-level comment header (`// R3.2 — DIAGNOSTIC FUNCTIONS — TEMPORARY`).
  - Module-level constants `LIFECYCLE_RESOURCE`, `STREAM_LOCATION`.
  - Helper functions `_streamQueryToken`, `_readFirstNdjsonLine`, `_writeCfReturnedAtMarker`, `_runHandoff`.
  - Exported handlers `probeHandoffAbort`, `probeHandoffLeaveOpen`.
  - Bottom-of-file `import { GoogleAuth } from 'google-auth-library'` line at 581 — `gear-handoff.js` already imports it independently; the bare top-of-file import in `index.js` is unused after deletion. Remove that line too.

**Reuse**: nothing — pure deletion.

**Adam-driven cleanup of deployed instances** (after the source-side commit lands, before Phase 8):

```bash
firebase functions:delete probeHandoffAbort probeHandoffLeaveOpen \
  --region us-central1 --project=superextra-site --force
```

Per R3 setup gotcha already in `docs/deployment-gotchas.md`: removing source from `index.js` does NOT auto-delete deployed Gen 2 functions. The explicit delete is required to take down the URLs.

**Verification** (scope is `functions/` only — `agent/probe/run_r32.py` retains URL references, expected, slated for Phase 9 archival):

```bash
grep -rn "probeHandoff" functions/        # zero matches
grep -rn "LIFECYCLE_RESOURCE" functions/  # zero matches
cd functions && npm test                  # 64 passed (probe handlers had no tests)
```

## Commit 2 — `test(gear): cover gear-branch + transport stickiness + deadline-abort + chat-state edges`

### `functions/index.test.js` — five new cases inside `describe('agentStream')`

Reuse the existing `mockReq`, `mockRes`, `mockDb`, `partitionWrites`, `decodeTaskBody`, and `authedReq` helpers (already in the file). The mocked `firebase-admin/firestore` and `firebase-admin/auth` modules at the top of the file already work for the gear branch — the agentStream txn writes `transport` into the session doc the same way it writes other fields.

**Mock placement (load-bearing — F2 P1).** The `mock.module('./gear-handoff.js', ...)` call MUST sit at file scope BEFORE `await import('./index.js')` at line 113. Putting it inside `describe('agentStream')` is too late because `index.js` already captured the real `gearHandoff`/`gearHandoffCleanup` imports by then. Concretely:

```javascript
// near other mock.module calls, before the import:
const gearHandoffMock = mock.fn(async () => ({ ok: true }));
const gearHandoffCleanupMock = mock.fn(async () => {});
mock.module('./gear-handoff.js', {
	namedExports: { gearHandoff: gearHandoffMock, gearHandoffCleanup: gearHandoffCleanupMock }
});

// THEN:
const { intake, agentStream, ..., chooseInitialTransport, GEAR_ALLOWLIST, resetGearAllowlist } = await import('./index.js');
```

Reset call counts and allowlist state in `beforeEach`:

```javascript
beforeEach(() => {
	// ... existing resets ...
	gearHandoffMock.mock.resetCalls();
	gearHandoffCleanupMock.mock.resetCalls();
	resetGearAllowlist();
});
```

This needs `--experimental-test-module-mocks`, already in `package.json:test`.

**Transport seam refactor (F2 P1).** The current `chooseInitialTransport(submitterUid)` reads two module-level constants (`GEAR_ALLOWLIST` Set and `GEAR_DEFAULT` string). Test 5 wants to verify both the allowlist and a flipped default — but `GEAR_DEFAULT` is a `const` string and reassigning it module-wide for one test is hostile cross-test pollution. Refactor to default-parameters:

```javascript
// In functions/index.js
export const GEAR_ALLOWLIST = new Set([]);
export const GEAR_DEFAULT = 'cloudrun'; // flip to 'gear' for Stage B

export function chooseInitialTransport(
	submitterUid,
	allowlist = GEAR_ALLOWLIST,
	defaultTransport = GEAR_DEFAULT
) {
	if (allowlist.has(submitterUid)) return 'gear';
	return defaultTransport;
}

export function resetGearAllowlist() {
	GEAR_ALLOWLIST.clear();
}
```

Test 5 then exercises the function purely via parameters; Tests 1–4 mutate `GEAR_ALLOWLIST.add(...)` for their setup and rely on the autouse `resetGearAllowlist()` in `beforeEach`.

**Test 1 — gear allowlist hit routes to gearHandoff, no Cloud Task.**
First-turn POST. Submitter UID added to `GEAR_ALLOWLIST` for this test. `mockDb.get` returns `exists: false`. Assert `tasksClient.createTask.mock.callCount() === 0`; `gearHandoffMock.mock.callCount() === 1`; the call's first arg matches `{ sid: 'sess-1', runId: <uuid>, turnIdx: 1, userId: 'user-good-token', isFirstMessage: true }` and `message` starts with `[Date: `. The session-doc set call should include `transport: 'gear'`.

**Test 2 — gearHandoff failure → gearHandoffCleanup → 502.**
`gearHandoffMock.mock.mockImplementationOnce(async () => { throw new Error('streamQuery_not_ok:502') })`. Assert `res._status === 502`; `res._json.error === 'handoff_failed'`; `gearHandoffCleanupMock` called once with `(db, 'sess-1', runId, 1, /^gear_handoff_failed:streamQuery_not_ok/)`.

**Test 3 — sticky transport: follow-up on gear session stays gear.**
`mockDb.get` returns `{ exists: true, data: () => ({ userId: 'user-good-token', participants: ['user-good-token'], status: 'complete', transport: 'gear', lastTurnIndex: 1, ... }) }`. Submitter is NOT in `GEAR_ALLOWLIST`; `GEAR_DEFAULT === 'cloudrun'`. Assert `gearHandoffMock` called once; `tasksClient.createTask` count = 0. Also assert the session `t.update` payload does NOT contain a `transport` key (sticky preservation).

**Test 4 — v3.9 P1 regression: legacy session with no transport field stays cloudrun.**
`mockDb.get` returns `exists: true` with session data that has NO `transport` field. Submitter IS in `GEAR_ALLOWLIST` (would pick gear if it were a new session). Assert `tasksClient.createTask` count = 1; `gearHandoffMock` count = 0. The `t.update` payload still doesn't contain `transport` (the field stays nullish).

**Test 5 — `chooseInitialTransport` allowlist hit/miss/default-flipped.**
Direct unit test via parameters (no module mutation):

```javascript
assert.equal(chooseInitialTransport('user-x', new Set(), 'cloudrun'), 'cloudrun');
assert.equal(chooseInitialTransport('user-x', new Set(['user-x']), 'cloudrun'), 'gear');
assert.equal(chooseInitialTransport('user-x', new Set(), 'gear'), 'gear'); // GEAR_DEFAULT flipped scenario
assert.equal(chooseInitialTransport('user-x', new Set(['user-y']), 'cloudrun'), 'cloudrun');
```

### `functions/gear-handoff.test.js` — one new case

**Test 6 — deadline fires abort across all three signals.** `node:test` has no `vi.useFakeTimers` equivalent; the cleanest seam is an explicit `deadlineMs` parameter on `gearHandoff()` that defaults to `HANDOFF_DEADLINE_MS`:

```javascript
export async function gearHandoff({
	sid,
	runId,
	turnIdx,
	userId,
	message,
	isFirstMessage,
	deadlineMs = HANDOFF_DEADLINE_MS // testability hook — default = production value
}) {
	// ...existing body, replacing HANDOFF_DEADLINE_MS references with deadlineMs
}
```

**Why parameter, not env var (F2 P2).** The env-var alternative (`GEAR_HANDOFF_DEADLINE_MS_OVERRIDE`) would be a test-only knob that can leak into production config and read inside `gearHandoff()` on every call. Parameter is confined to test call sites and obvious from the signature.

Test setup: mock createSession + appendEvent to resolve normally; mock streamQuery's `read()` to return a promise that rejects when `init.signal.aborted` becomes true. Call `gearHandoff({ ..., deadlineMs: 100 })`. Wait ~150 ms. Assert:

- The promise rejects with `gearHandoff_deadline_exceeded:100ms`.
- All three captured `init.signal` references show `aborted === true`.
- `reader.cancel()` was called by the streamQuery `finally` block.

Real wall-clock 150 ms is acceptable for a single test — total suite still <1 s.

### `src/lib/chat-state.spec.ts` — retry post-Firestore failure cases

The previous attempt failed because of `(getDoc as Mock).mockResolvedValueOnce(...)` — TypeScript readonly module property. Use `vi.mocked(getDoc)` typed wrapper instead. The hoisted `vi.mock('firebase/firestore', ...)` factory at the top of the file already includes `getDoc: vi.fn(async () => ({ exists: () => false }))`.

**Test 7 — post-Firestore failure: doc exists with status='error' → no rollback.**
`vi.mocked(getDoc).mockResolvedValueOnce({ exists: () => true, data: () => ({ status: 'error' }) })`. POST mock rejects 502. Assert `chatState.activeSid` stays the sid (listener takes over); the doc has status='error' so the existing loadState machinery renders the error.

**Test 8 — v3.9 P2 regression: getFirebase throws → caught → rollback.**
`vi.mocked(getFirebase).mockRejectedValueOnce(new Error('firebase_offline'))`. POST mock rejects 502. Assert `chatState.activeSid === null`; `loadState === 'idle'`. This guards the wrap-getFirebase-and-import-in-same-try fix from plan §v3.9.

If `vi.mocked` still fails to propagate to chat-state's dynamic import, **do NOT skip** (F1 minor). The v3.9 P2 catch branch is real regression surface. Fall back to a manual Chrome DevTools MCP recipe: navigate to the dev server, submit a chat, force the network offline mid-POST via `evaluate_script`/`emulate`, assert chat-state rolls back to idle. Add this as a documented step in the Phase 6 smoke section below if the unit-level seam doesn't work.

## Commit 3 — `fix(gear): post-review reliability + UX hygiene`

### finalize_failed terminal write

**File**: `agent/superextra_agent/firestore_progress.py:435-441`

Replace the bare `return None` after `log.exception("finalize crashed ...")` with a best-effort fenced terminal-error write. Mirrors the empty-reply error pattern that `gear_run_state.finalize()` already produces.

```python
try:
    session_update, turn_update, _status = await per.finalize()
except Exception:
    log.exception("finalize crashed sid=%s runId=%s", per.sid, per.run_id)
    # Best-effort terminal error write so the user sees an error within
    # ~1s instead of waiting for watchdog (5min) to flip pipeline_wedged.
    # Wraps `_retry_critical` to match the existing terminal-write retry
    # semantics — transient Firestore blips get the same bounded retry
    # the happy-path terminal write already enjoys (F2 P2).
    try:
        await _retry_critical(
            lambda: fenced_session_and_turn_update(
                self._client(),
                per,
                {
                    "status": "error",
                    "error": "finalize_failed",
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                {"status": "error", "error": "finalize_failed"},
            )
        )
    except OwnershipLost:
        # Run was already flipped (watchdog or cleanup). Don't resurrect.
        pass
    except Exception:
        log.exception(
            "finalize_failed terminal write also failed sid=%s runId=%s",
            per.sid, per.run_id,
        )
    return None
```

**Reuse**: `fenced_session_and_turn_update()`, `_retry_critical()`, and `OwnershipLost` from same file.

**Test**: `agent/tests/test_firestore_progress.py` — add a case that monkeypatches `per.finalize` (or constructs a `GearRunState` whose `finalize()` raises) and asserts `fenced_session_and_turn_update` was called with the `finalize_failed` payload. Reuse the existing `_mock_invocation_context` helper.

### Drop CancelledError from title-task except

**File**: `agent/superextra_agent/gear_run_state.py:301`

```python
# before
except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
# after
except (asyncio.TimeoutError, Exception):
```

`Exception` does NOT catch `CancelledError` in Python ≥3.8 (it inherits from `BaseException`, not `Exception`). Removing the explicit clause restores normal cancellation propagation. Plan §4.1 doesn't list CancelledError. One-line fix.

**Test**: existing `test_finalize_handles_failing_title_task` covers the exception path. **Add `test_finalize_propagates_cancellation` (mandatory per F2 P3)** — the code change is one line but the behavior is subtle and important. Existing `GearRunState` test fixtures make it cheap: construct a state, set `state.title_task = asyncio.create_task(asyncio.sleep(60))`, schedule an outer `asyncio.CancelledError` via `asyncio.create_task(...)` racing `per.finalize()`, assert the cancellation propagates through finalize rather than being swallowed by the title-task wrapper.

### Places import-time warning

**File**: `agent/superextra_agent/places_tools.py:57-59`

Drop the warning entirely:

```python
# before
# Warn early if API key is missing (actual RuntimeError raised on first call)
if not os.environ.get("GOOGLE_PLACES_API_KEY"):
    logger.warning("GOOGLE_PLACES_API_KEY not set — Places API calls will fail")

# after
# (deleted — Secret Manager fallback resolves at first call; runtime
# error there has the precise message and stack)
```

The call site (`_get_api_key` → `get_secret`) already raises a `RuntimeError` containing the secret name when both env and Secret Manager fail. The import-time warning is redundant and false under GEAR.

**Test**: existing places_tools tests cover the call-site error path. No new test needed.

### Narrow ALREADY_EXISTS to status===409 (F1 + F2)

**File**: `functions/gear-handoff.js:138-143`

```javascript
// before
if (!r.ok) {
	const body = await r.text().catch(() => '');
	if (!body.includes('ALREADY_EXISTS')) {
		throw new Error(`createSession_failed:${r.status}:${body.slice(0, 200)}`);
	}
}

// after
if (!r.ok) {
	const body = await r.text().catch(() => '');
	if (r.status !== 409 || !body.includes('ALREADY_EXISTS')) {
		throw new Error(`createSession_failed:${r.status}:${body.slice(0, 200)}`);
	}
}
```

Currently any 4xx whose response body happens to contain the substring `ALREADY_EXISTS` is treated as success. Theoretical scenario: a 429 quota error message that mentions "already exists" in error text would silently treat the createSession as having succeeded — then `:appendEvent` would 4xx because the session truly doesn't exist. Pinning to status 409 plus body match closes that gap with no test changes (the existing ALREADY_EXISTS test already returns 409).

**Test**: existing `createSession ALREADY_EXISTS → continues to appendEvent` test in `functions/gear-handoff.test.js` already returns `status: 409` so it stays green. Optionally add a case where status is 4xx-but-not-409 with a body containing "ALREADY_EXISTS" → should now throw.

### Drop `__post_init__` defensive raise (F1 + F2)

**File**: `agent/superextra_agent/gear_run_state.py:80-94`

```python
# before
def __post_init__(self) -> None:
    if self.fs is None:
        raise RuntimeError("GearRunState requires fs (Firestore client)")
    started_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    ...

# after
def __post_init__(self) -> None:
    started_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    ...
```

No verified failure mode for this check; production never constructs `GearRunState` without `fs` (the plugin always passes it). The lean covenant from plan §v3.6 says "every line that looks defensive is there because a specific failure mode was identified and verified — before 'simplifying' something, find the corresponding revision-history entry." There's no entry. Removing the runtime check costs nothing; if a future caller misuses the API, they get an `AttributeError` from a downstream Firestore call instead of a `RuntimeError` here. Both surface the bug.

**Reordering note**: keep `fs: firestore.Client | None = None` as a defaulted field — the dataclass `field(init=False)` constructed sub-objects (`timeline_builder`, `timeline_writer`) need to come after non-defaulted fields, and reorganizing for `fs` to be required would shuffle the whole declaration. Pure deletion of the check is the smaller, lean-covenant-compliant change.

**Test**: no behavior change in normal path; existing test_gear_run_state suite stays green.

### Document the 10s rollback timer choice

**File**: `docs/gear-migration-execution-log-2026-04-27.md`

Add to the "Decisions / changes / learnings" section:

> **Plan §"Cross-cutting" 3s POST-rollback timer was implemented as 10s (existing `LOAD_TIMEOUT_MS`).** The plan called for a ~3s rollback timer to deselect a session whose POST never resolved. The existing `LOAD_TIMEOUT_MS = 10_000` in `chat-state.svelte.ts:101` already provides this mechanism via `loadState='loadTimedOut'` after 10s. 3s is too aggressive given gearHandoff's 75s first-NDJSON-line deadline — a normal-but-slow first turn would trip a 3s timer well before the doc materializes. 10s catches network-blackhole cases without false-positiving on legitimate slowness. Documented here per plan §"Honesty and pushback": empirical reasoning (verified gearHandoff timing) trumps unverified plan numbers.

## Chrome DevTools MCP smoke (after Commit 3)

CLAUDE.md mandates browser verification for UI changes; vitest only verifies the state machine. The literal regression Phase 6 fixes — "user sees 'Couldn't load this chat' for 0.5–1.5s" — needs eyeballs.

Phase 6 logic is transport-independent. Smoke against the live cloudrun path on the dev server (port 5199, systemd-managed). Cloud Tasks dispatch + worker takeover gives ~1–2s latency, which is enough to exercise the optimistic window. End-to-end gear smoke is deferred to Stage A allowlist soak.

**Recipe** (using the `mcp__chrome-devtools-mcp__*` tools per CLAUDE.md):

1. `new_page` → `http://localhost:5199/agent`.
2. Sign in via the existing flow (anon auth or whatever the page uses).
3. `take_snapshot` to capture the entry state.
4. `fill` the chat input with a test query (e.g. "What's the menu like at Bistro?").
5. `press_key` Enter.
6. Within 1s, `take_snapshot` — assert the chat panel is rendering with the user message and a "researching..." or similar placeholder; assert NO "Couldn't load this chat" text in the DOM.
7. `take_screenshot` to `docs/gear-phase6-smoke-2026-04-27.png` for the log.
8. Wait ~5s, take another snapshot — verify normal progress (timeline events appearing, loading state).

Update `docs/gear-migration-execution-log-2026-04-27.md` with the smoke result + screenshot reference under "Verification artifacts".

**Coverage gaps acknowledged**:

- Forced 502 (gearHandoffCleanup → status='error') needs the gear path live; revisit during Stage A.
- Network blackhole rollback test would require Chrome DevTools network blocking — brittle. Defer to Stage A or skip.

If any step fails the regression-gate, bail out and investigate before staging. Treat this smoke as the actual go/no-go for Phase 6.

## Critical files

**Modified**:

- `functions/index.js` — Commit 1 deletes lines 644-787 + the unused `GoogleAuth` import.
- `functions/index.js` — Commit 2: export `GEAR_ALLOWLIST`, `GEAR_DEFAULT`, `chooseInitialTransport(uid, allowlist?, defaultTransport?)`, `resetGearAllowlist()` (parameter-based test seam, not mutable module state).
- `functions/index.test.js` — Commit 2 adds five test cases (Tests 1-5). `mock.module('./gear-handoff.js', ...)` placed at file scope before `await import('./index.js')`.
- `functions/gear-handoff.js` — Commit 2 adds explicit `deadlineMs = HANDOFF_DEADLINE_MS` parameter on `gearHandoff()`. Commit 3 narrows ALREADY_EXISTS check to `r.status === 409 && body.includes('ALREADY_EXISTS')`.
- `functions/gear-handoff.test.js` — Commit 2 adds Test 6 (deadline-fires-abort with 100 ms `deadlineMs`).
- `src/lib/chat-state.spec.ts` — Commit 2 adds Tests 7-8 (or — if `vi.mocked` doesn't propagate — documents the fallback to manual Chrome MCP recipe in the smoke section).
- `agent/superextra_agent/firestore_progress.py` — Commit 3 finalize_failed write wrapped in `_retry_critical` at line 435.
- `agent/superextra_agent/gear_run_state.py` — Commit 3 drop CancelledError at line 301; drop `__post_init__` defensive raise at lines 80-94.
- `agent/superextra_agent/places_tools.py` — Commit 3 drop import-time warning at lines 57-59.
- `agent/tests/test_firestore_progress.py` — Commit 3 finalize_failed test case.
- `agent/tests/test_gear_run_state.py` — Commit 3 mandatory `test_finalize_propagates_cancellation` test.
- `docs/gear-migration-execution-log-2026-04-27.md` — Commit 3 10s timer note + (after smoke) screenshot reference.

**Created**:

- `docs/gear-phase6-smoke-2026-04-27.png` — Chrome MCP screenshot.

**Deleted (deployed Cloud Function instances)** — Adam runs:

- `probeHandoffAbort`, `probeHandoffLeaveOpen` via `firebase functions:delete`.

## Verification (end-to-end)

After each commit:

```bash
# Commit 1 — pure delete
grep -rn "probeHandoff\|LIFECYCLE_RESOURCE" functions/  # zero matches
cd functions && npm test                                # 64 passed (unchanged)

# Commit 2 — test additions
cd functions && npm test                                # 64 + 6 = 70 passed
npx vitest run src/lib/chat-state.spec.ts               # 36 + (1 or 2) passed

# Commit 3 — reliability fixes
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q     # 224 + 1 = 225 passed
npm run check                                           # 0 errors
```

After Chrome MCP smoke:

- Screenshot saved to `docs/gear-phase6-smoke-2026-04-27.png`.
- Execution log updated with smoke result + screenshot reference.

Final regression once all three commits + smoke are in:

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/    # 225 passed
cd functions && npm test                            # 70 passed
npm run test                                        # 60 passed
npm run test:rules                                  # 22 passed (unchanged)
npm run check                                       # 0 errors
npm run lint                                        # GEAR files clean
```

## Adam-driven follow-on (after the fixes land)

1. **Phase 1 cloud-side gcloud commands.** Run the four-block sequence in `docs/gear-migration-execution-log-2026-04-27.md` § "Phase 1 — drafted command set". Agent verifies post-hoc with `gcloud secrets versions access latest --secret=NAME | wc -c`.

2. **Delete deployed probe Cloud Functions** (the cloud-side companion to Commit 1):

   ```bash
   firebase functions:delete probeHandoffAbort probeHandoffLeaveOpen \
     --region us-central1 --project=superextra-site --force
   ```

3. **Phase 8 staging deploy** per `docs/gear-migration-execution-log-2026-04-27.md` § "Phase 8 handoff":
   - `agent_engines.create(...)` to deploy the agent app under a staging Reasoning Engine resource (~3–4 min wait).
   - Set `GEAR_REASONING_ENGINE_RESOURCE` env var on the deployed agentStream Cloud Function.
   - Add 1–2 developer UIDs to `GEAR_ALLOWLIST`, commit + deploy.

4. **Stage A soak (~1 week).** Watch:
   - `gcloud logging read 'resource.type="cloud_function" AND severity>=WARNING'` for handoff failures.
   - Firestore `sessions/*` filtered to `transport: 'gear'` reaching `status: 'complete'`.
   - End-to-end Chrome MCP smoke against the live gear path (the deferred coverage from Phase 6).

5. **Stage B default flip.** Change `GEAR_DEFAULT` from `'cloudrun'` to `'gear'`, commit + deploy.

6. **PR to main.** Open after Stage A soak proves clean (or after Stage B flip, depending on risk tolerance). Sticky-per-session means existing chats stay on cloudrun. Reverting GEAR is one commit (flip default back, drop allowlist).

7. **Phase 9 cleanup** (after 30-day rollback window): worker decommission + Firestore field migration + `agent/probe/` archival.

## Estimated effort

- Commit 1: 30 min (mostly verifying nothing else uses `LIFECYCLE_RESOURCE`).
- Commit 2: 2-3 hours (six new tests + transport seam refactor + deadline parameter + mock placement at file scope).
- Commit 3: 1.5 hours (five source changes — finalize_failed + retry, CancelledError drop, places warning, ALREADY_EXISTS narrow, `__post_init__` drop — plus two mandatory tests for finalize_failed + cancellation propagation).
- Chrome MCP smoke: 30 min.

**Total: ~5 hours single-agent.** All test suites should stay green at every commit boundary.
