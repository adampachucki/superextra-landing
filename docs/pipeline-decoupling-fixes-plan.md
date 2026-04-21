# Pipeline-Decoupling Fixes — Reconciled Plan

Follow-up to `docs/pipeline-decoupling-plan.md`. Addresses the issues surfaced
by two independent post-implementation reviews plus the live E2E smoke run —
all cross-checked against the actual code before landing. Incorporates the
external review in `docs/pipeline-decoupling-fixes-plan-review.md`.

Source documents consulted:

- `docs/pipeline-decoupling-plan.md` — design, still the source of truth.
- `docs/pipeline-decoupling-execution-log.md` — per-phase record, the
  "Post-implementation review" section, and the "Live E2E smoke" section.
- `docs/pipeline-decoupling-post-implementation-audit.md` — external auditor's
  findings.
- `docs/pipeline-decoupling-spike-results.md` — settled facts; do not
  re-litigate.
- `docs/pipeline-decoupling-fixes-plan-review.md` — external review of an
  earlier version of this plan. All three critical notes verified in code and
  incorporated below. A follow-up adversarial pass verified the revised plan
  and surfaced the whitespace-only `final_report` edge case, the `findStuckSessions`
  return-shape expansion needed for Tier 1.4, the best-effort (not guaranteed)
  nature of Tier 2.2 cleanup, and the `RecoveryContext` closure approach for
  Tier 2.3 — all folded in below.

## Findings — verified against code

| #   | Finding                                                               | Verdict                      | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | --------------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0   | Events observer still treats `type='complete'`/`'error'` as terminal  | **CONFIRMED** (review add)   | `src/lib/firestore-stream.ts:192-210` calls `callbacks.onComplete` / `onError` from event docs. `agent/superextra_agent/firestore_events.py:121-122` writes events via plain `ref.set(doc)` — **not** fenced. A stale worker can leak a terminal event doc before its next `lastEventAt` fenced update fails. Session doc is the only fenced terminal.                                                                                                               |
| 1   | Worker `_extract_sources_from_state_delta` sees only synth deltas     | **CONFIRMED**                | `agent/worker_main.py:629-632` — `sd` is per-event; specialist output keys (`market_result`, etc.) are in earlier events and gone by synth's final.                                                                                                                                                                                                                                                                                                                  |
| 2   | Router-final reply never promoted to session doc                      | **CONFIRMED**                | `agent/superextra_agent/firestore_events.py:163-168` emits `type='complete'` with reply text into the `events` collection, but `worker_main.py:630` only sets `final_reply` from `state_delta.final_report`. Router clarifications therefore reach the terminal write path with `final_reply=None`, fail the sanity gate, and the **session doc** gets `status='error'` — breaking `agentCheck` / reopen even though the event stream carried a valid clarification. |
| 3   | Deploy ordering lets `agentStream` ship before worker exists          | **CONFIRMED**                | `.github/workflows/deploy.yml:89,129` — `deploy-hosting` and `deploy-worker` both `needs: test`, parallel. Cloud Tasks retry window (~130 s total with `minBackoff=10s,maxBackoff=60s,maxAttempts=3`) shorter than first-time Python + ADK Docker build.                                                                                                                                                                                                             |
| 4   | Watchdog unfenced `.update()` can clobber a real completion           | **CONFIRMED**                | `functions/watchdog.js:141-153` — plain `.update()`, no transaction, no precondition. Existing "acceptable" comment overruled by audit-P2.                                                                                                                                                                                                                                                                                                                           |
| 5   | M4 — "Retrying…" UI cue missing on `onAttemptChange`                  | **CONFIRMED**                | `src/lib/chat-state.svelte.ts:299-306` clears state; surfaces nothing. Plan §Phase 5 explicitly requires a "brief 'Retrying…' indicator".                                                                                                                                                                                                                                                                                                                            |
| 6   | Bug-6 — reply dedup text-equality unsafe for repeat short replies     | **CONFIRMED**                | `src/lib/chat-state.svelte.ts:318,325` drops genuinely new `"OK"` / `"Yes"` short follow-ups that repeat a previous reply string.                                                                                                                                                                                                                                                                                                                                    |
| 7   | Bug-1 — `asyncio.CancelledError` bypasses `_cancel_heartbeat`         | **CONFIRMED**                | `asyncio.CancelledError` is `BaseException`-rooted, not `Exception`-rooted; `worker_main.py:634/641/651` do not catch it, so cancel-order rule (plan §Phase 3, step 3) is violated on cancellation.                                                                                                                                                                                                                                                                  |
| 8   | Stale mocks `@google-cloud/vertexai` + `google-auth-library`          | **CONFIRMED**                | `functions/index.test.js:70-93` mocks modules no longer imported by `functions/index.js`. Silent — would pass a re-introduction.                                                                                                                                                                                                                                                                                                                                     |
| 9   | SIGTERM handler constructs a fresh `firestore.Client`                 | **CONFIRMED**                | `agent/worker_main.py:494` — 10 s grace is tight; reuse `_fs`.                                                                                                                                                                                                                                                                                                                                                                                                       |
| 10  | T3 — no test for `expiresAt = max(existing, now+30d)`                 | **CONFIRMED**                | No such assertion in `functions/index.test.js`. Logic at `functions/index.js:246-248` correct but uncovered.                                                                                                                                                                                                                                                                                                                                                         |
| 11  | T4 — no test for 7-min `poll_timeout` branch                          | **CONFIRMED**                | `agent/tests/test_worker_main.py` covers `noop_stale` / `noop_complete` exits of `_poll_until_resolved`, not the 7-min ceiling.                                                                                                                                                                                                                                                                                                                                      |
| —   | T6 — "collection-group event write-deny" gap                          | **REFUTED**                  | Firestore writes target concrete document paths, not collection-group URLs. `firestore.rules.spec.js:160-171` already writes to `sessions/sid-alice/events` — that concrete path is exactly what the `/{path=**}/events/{eid}` wildcard rule governs. No separate collection-group write path to test.                                                                                                                                                               |
| —   | M7 — frontend sends unused `isFirstMessage`                           | **REFUTED as bug**           | Sent at `chat-state.svelte.ts:403`, but `functions/index.js:244` recomputes from `!existing`. Redundant, not broken.                                                                                                                                                                                                                                                                                                                                                 |
| —   | Stale `parseADKStream` / `sendSSE` / `SPECIALIST_RESULT_KEYS` exports | **REFUTED for "delete now"** | `functions/utils.test.js` still exercises them; deletion requires also dropping tests. Plan says "delete post-smoke" — defer.                                                                                                                                                                                                                                                                                                                                        |
| —   | `streamingText` state unused by new transport                         | **PARTIAL — keep**           | Never written by Firestore transport; still read by `src/lib/components/restaurants/ChatThread.svelte:14,30,60,77` (typewriter render). Harmless; cleanup can follow a future UI simplification.                                                                                                                                                                                                                                                                     |
| —   | `ios-sse-workaround.ts` stale                                         | **REFUTED**                  | Still imported by `chat-state.svelte.ts:4,627` for the transport-agnostic `handleReturnFromHidden` tab-visibility helper. Keep.                                                                                                                                                                                                                                                                                                                                      |

## Tier 1 — Critical durability (must land before first prod deploy)

### 1.1 Remove unfenced terminal emission from the events observer

- `src/lib/firestore-stream.ts:192-210`. Drop the `case 'complete'` and
  `case 'error'` branches in the **events** observer. Keep `'progress'` and
  `'activity'` — those are fine to surface from the unfenced event stream
  because they are additive UI state.
- The session doc observer at lines 141-158 remains the single terminal
  source. Session-doc writes already go through `_fenced_update`, so a
  stale worker cannot flip `status`/`reply` after being fenced out.
- Update the JSDoc at lines 1-22 to state "session doc is the only
  terminal source; events stream carries progress only."
- Why this must land before 1.2/1.3: the worker write path emits the
  event doc first (line 621) and the fenced `lastEventAt` update second
  (line 625). A stale worker can leak one post-takeover `complete`/`error`
  event doc before hitting `OwnershipLost`. Without 1.1, that leaked doc
  becomes a terminal UI signal that races the fenced session doc.
- Test: extend `src/lib/firestore-stream.spec.ts` with a case that fires a
  `type='complete'` event doc when the session doc `status` is still
  `running` — assert `onComplete` is **not** called.
- **Tradeoff note**: removing `case 'error'` makes the session doc the
  only error surface. The worker writes `status='error'` via fenced
  update in every error path (`worker_main.py:659-662` for pipeline
  exceptions; other paths raise 500 and let Cloud Tasks retry, which
  eventually triggers the watchdog). A transient Firestore lag between
  the event doc and the session doc write could delay the error message
  by seconds. Accepted — error UX is unchanged from today.

### 1.2 Accumulate `state_delta` across the event loop

- `agent/worker_main.py:608-632`. Add `accumulated_state: dict[str, Any] = {}`
  before the `async for`. On every event, merge string values from its
  `state_delta` into `accumulated_state`.
- At the final-report branch, pass `accumulated_state` — not `sd` — to
  `_extract_sources_from_state_delta`. Dedup by URL against any sources
  the mapper already extracted from the synth's own reply text.
- Test in `agent/tests/test_worker_main.py`: drive three synthetic events
  (two specialists with output keys, one synth with `final_report`).
  Assert the written session doc's `sources` contains both specialists'
  URLs.

### 1.3 Promote router-final replies + simplify the reply-sanity gate

- `agent/worker_main.py`. Reuse the return value of `map_and_write_event(...)`
  rather than re-running `map_event(event)` — the mapper already ran once
  in the write path. Capture `emitted = await map_and_write_event(...)`;
  when `emitted["type"] == "complete"` and `final_reply is None`, set
  `final_reply` / `final_sources` from the mapper's `data`.
- **Simplify the reply-sanity check at `worker_main.py:672-676`.** Replace
  the three-part guard with a single stripped non-empty check:
  `if not final_reply or not final_reply.strip(): ...`. The `.strip()`
  matters because `_has_state_delta` at `firestore_events.py:390-401` only
  filters `if not value` (catches `""` but not `"   "`) and
  `_map_synthesizer` at `firestore_events.py:283-293` does not trim. A
  whitespace-only `final_report` would otherwise render as
  `status='complete'` with meaningless text.
- Remove:
  - `len(final_reply) < REPLY_MIN_LEN`. The original purpose was to catch
    `MALFORMED_FUNCTION_CALL` / `UNEXPECTED_TOOL_CALL` producing an empty
    synth reply. The `_embed_chart_images` fallback at
    `agent/superextra_agent/agent.py:180-189` already covers the subset
    where `llm_response.error_code` is set (exec log's 2 broad queries
    hit this and got 33 KB / 36 KB fallback reports). **Uncovered**: a
    synth that silently produces a short non-empty reply with no
    `error_code`. That mode is rare but not impossible; accepting it now
    means a truly bad short reply would render as `status='complete'`
    rather than `status='error'`. Mitigation is user-visible retry — the
    trade is worth it because the current gate false-rejects every router
    clarification and every legitimately-short synth reply.
  - `final_reply.startswith("Error:")` — obsolete per spike-results
    ("ADK synthetic-error in reply — Moot via in-process Runner"). Real
    pipeline exceptions hit the `except Exception` branch and write
    `status='error'` correctly.
- Remove the `REPLY_MIN_LEN` constant along with the check. No new
  `terminal_source` field needed — router vs synth paths no longer
  diverge at the gate.
- Tests:
  - Synthetic router-clarification fixture → assert `status='complete'`,
    short reply written.
  - Synth fixture with no `final_report` anywhere → assert `status='error'`
    (empty-reply guard still catches it).
  - **Whitespace-only `final_report`** → assert `status='error'` (the
    `.strip()` guard catches this; without `.strip()` it would slip
    through both the mapper and the worker check).
  - If any existing test asserts the `len < 100` or `startswith('Error:')`
    rejection behaviour, delete or rewrite it. Quick grep confirmed no such
    test exists today (`grep -n REPLY_MIN_LEN agent/tests/` → 0 hits) but
    double-check during execution before removing the constant.

### 1.4 Fenced watchdog terminal writes

- `functions/watchdog.js:141-153`. Wrap each flip in `db.runTransaction`.
  The txn must re-verify that the session is still in the stuck state it
  was when `findStuckSessions` returned; otherwise a worker that completes
  between the initial query and the flip gets clobbered.
- **Expand `findStuckSessions` return shape** (`functions/watchdog.js:37-97`).
  Today it returns `{sid, reason, errorDetails}`. Must also return:
  - `expectedStatus` — `'queued'` for `queue_dispatch_timeout`;
    `'running'` for `worker_lost` / `pipeline_wedged`.
  - `expectedRunId` — `d.currentRunId` captured at classification time.
  - `thresholdField` — `'queuedAt'` / `'lastHeartbeat'` / `'lastEventAt'`
    depending on classifier.
  - `thresholdMillis` — the absolute upper-bound timestamp (millis)
    beyond which the field is considered stale (e.g. `nowMs - 30min` for
    queued). Simpler to re-check than an age delta.
- **Txn body per doc**:
  1. Read session doc.
  2. Abort silently if `data.status !== expectedStatus`.
  3. Abort silently if `data.currentRunId !== expectedRunId`.
  4. Abort silently if `toMillis(data[thresholdField]) > thresholdMillis`
     (the field has been freshened; worker is alive again).
  5. Otherwise `tx.update(ref, { status: 'error', error: reason, errorDetails })`.
- Reference: Firestore transactions docs — reads before writes, callback
  retries automatically on contention, no partial writes.
- Tests in `functions/watchdog.test.js`:
  - Session completes (`status → 'complete'`) between query and txn → no
    write.
  - Worker writes a fresh `lastHeartbeat` between query and txn → no
    write (`thresholdField` check).
  - New turn started (`currentRunId` advanced) between query and txn →
    no write.
  - Session still genuinely stuck → write lands.

### 1.5 Serialize deploy — hosting waits for worker

- `.github/workflows/deploy.yml:89`. Change `deploy-hosting` to
  `needs: [test, deploy-worker]`, plus
  `if: always() && needs.test.result == 'success' && (needs.deploy-worker.result == 'success' || needs.deploy-worker.result == 'skipped')`.
- Effect: when the agent filter skips `deploy-worker`, hosting proceeds
  normally; when a worker deploy runs, hosting waits for it to succeed.
  Removes the "first-deploy into nothing" window.
- Reference: GitHub Actions `needs` + `if: always()` + the four possible
  `needs.<job>.result` values (`success`, `failure`, `cancelled`,
  `skipped`).
- Verify with a dry inspection of the workflow graph in a draft PR.
- **Rerun policy note**: if `deploy-worker` fails and the operator
  manually reruns that single job, `deploy-hosting` will not auto-run
  (GitHub Actions does not re-evaluate `needs` for a single-job rerun).
  Operator must rerun the whole workflow — or use "Rerun failed jobs".
  Document in `docs/deployment-gotchas.md`.

## Tier 2 — Plan-explicit misses (UX + ordering)

### 2.1 "Retrying…" UI cue

- `src/lib/chat-state.svelte.ts:299-306` `onAttemptChange`. After clearing
  `streamingActivities` / `streamingProgress`, seed
  `streamingProgress = [{ stage: 'retrying', status: 'running', label: 'Retrying…' }]`
  so the existing `StreamingProgress.svelte` renders a visible cue
  without new components. Subsequent progress events overwrite it.
- Spec: extend `chat-state.spec.ts` to assert the seeded entry after
  `onAttemptChange(2)`.

### 2.2 Heartbeat cancel on `asyncio.CancelledError` (try/finally)

- `agent/worker_main.py:614-667`. Wrap the event loop body in a
  `try / except / finally` so heartbeat cancel is guaranteed on every
  exit path, including `CancelledError`:

  ```python
  try:
      async for event in _runner.run_async(...):
          ...
  except OwnershipLost:
      raise HTTPException(status_code=500, detail="ownership_lost")
  except GoogleAPICallError as e:
      raise HTTPException(status_code=500, detail=f"google_api_error: {type(e).__name__}")
  except asyncio.CancelledError:
      raise  # propagate — framework will terminate
  except Exception as e:  # pipeline-layer exception
      await _cancel_heartbeat()  # cancel BEFORE fenced error write — plan cancel-order rule
      err_msg = f"{type(e).__name__}: {str(e)[:500]}"
      try:
          await _fenced_update(sid, attempt, worker_id, {"status": "error", "error": err_msg})
      except OwnershipLost:
          pass
      return {"ok": False, "action": "pipeline_error", "error": err_msg}
  finally:
      await _cancel_heartbeat()  # idempotent; covers Cancelled + success + HTTPException paths
  ```

- `_cancel_heartbeat()` is idempotent (checks
  `if _heartbeat_task and not _heartbeat_task.done()` and nulls the
  handle on the way out), so calling it twice is safe.
- **Guarantee level**: `_heartbeat_task.cancel()` is a synchronous call
  and always registers the cancellation. The subsequent
  `await asyncio.wait_for(_heartbeat_task, timeout=1.0)` is **best-effort**
  — during a `CancelledError` unwind, that await itself can re-raise
  (Python docs: awaits in `finally` during cancellation re-raise at the
  next suspension point). `_cancel_heartbeat` already swallows both
  `CancelledError` and `TimeoutError` in its inner except, so we still
  get the cancel registered; we just may not wait for the loop to fully
  exit. That is acceptable here because the heartbeat's writes are
  fenced — a late tick from a cancelled loop will fail cleanly with
  `OwnershipLost`. No `asyncio.shield` needed.
- **Redundant-call cleanup.** With the `finally` branch in place, drop the
  explicit `await _cancel_heartbeat()` calls at `worker_main.py:637`
  (OwnershipLost), `:644` (GoogleAPICallError), and `:670` (pre-sanity-check
  on success). The one at `:655` **stays** — it's the pipeline-exception
  branch and must run before the fenced error write to honour the
  cancel-before-terminal-write rule. The one at `:604` also stays — it's
  in the `create_session` failure path, outside the event-loop try block.
- Reference: Python asyncio docs — `CancelledError` is `BaseException`,
  must be re-raised after cleanup.
- Test: unit test that fires `CancelledError` inside the `run_async`
  generator; assert `_cancel_heartbeat` was awaited and the exception
  propagated out.

### 2.3 Reply dedup by `runId`

- After Tier 1.1 lands, the only remaining duplicate-terminal race is
  session-doc observer vs `agentCheck` REST recovery. Both serve the same
  `sessions/{sid}.reply` keyed by `currentRunId`. `(runId, attempt)` is
  unnecessary — the terminal is written once per turn and keyed on runId.
  `agentCheck` does not expose `attempt`; extending that surface just to
  dedup is over-engineering.
- `src/lib/chat-state.svelte.ts`. Inside `buildStreamCallbacks` introduce
  a local `appendedReplyForRunId: string | null = null`. On first
  `onComplete`, append and set the key to the current `runId`. Subsequent
  calls for the same runId are no-ops; any different runId always
  appends.
- `chat-recovery.ts` integration: **no signature change needed on
  `RecoveryContext`**. The caller (`chat-state.svelte.ts`) already builds
  the `ctx` object per call and knows the `runId`; close `runId` into the
  `isDuplicateReply` callback so it behaves as
  `() => appendedReplyForRunId === thatRunId`. The existing
  `isDuplicateReply?.(data.reply)` call at `chat-recovery.ts:102` passes
  the reply text, which we ignore in favour of the closed-over runId.
  Simpler than widening the recovery API.
- Spec: `chat-state.spec.ts` — assert a second reply with identical text
  but a different `runId` still appends; duplicate `runId` does not.

## Tier 3 — Test gaps

### 3.1 T3 — `expiresAt` never-shrinks

- `functions/index.test.js`. Existing session mocked with
  `expiresAt = now + 60d`; exercise the enqueue path; assert the
  transaction payload preserves `now + 60d` (not shrunk to `now + 30d`).

### 3.2 T4 — 7-min poll ceiling

- `agent/tests/test_worker_main.py`. Drive `_poll_until_resolved` with a
  mocked `asyncio.get_event_loop().time()` / mocked `asyncio.sleep`;
  have the session read return a fresh-heartbeat running state
  indefinitely. Assert
  `HTTPException(status_code=500, detail='poll_timeout...')` after the
  7-min bound.

### 3.3 Exception-propagation call-order

- `agent/tests/test_worker_main.py`. Replace the existing "assert
  called" form with a `Mock` that records call ordering via
  `call_args_list`; assert `_cancel_heartbeat` was awaited before the
  `_fenced_update(status='error')` write. Closes the T-weak item from
  the earlier review.

## Tier 4 — Low-risk cleanup

### 4.1 Remove dead mocks in `functions/index.test.js`

- Delete `@google-cloud/vertexai` and `google-auth-library` mock blocks
  at `functions/index.test.js:70-93`. Modules are no longer imported by
  `functions/index.js`. Tests remain green.

### 4.2 SIGTERM handler reuses `_fs`

- `agent/worker_main.py:494`. One-line change to reuse the module-level
  `_fs` Firestore client; fall back to `firestore.Client(project=PROJECT)`
  only if `_fs is None` (lifespan has not run — should not happen in
  production).
- **Thread-safety**: `google-cloud-firestore` clients are documented as
  thread-safe; concurrent use from the signal-handler thread and the
  event-loop's `to_thread` workers serialises at the gRPC channel.
  No lock needed.

## Optional hardening

### Pre-deploy sanity check when agent is unchanged

- `.github/workflows/deploy.yml` — add a single step at the top of
  `deploy-hosting` that runs `gcloud run services describe superextra-worker --region=us-central1 --project=superextra-site`
  and fails fast if the service does not exist. Guards against infra
  drift (service manually deleted, region mismatch, etc.).
- **Prerequisite**: `deploy-hosting` currently uses
  `google-github-actions/auth@v2` but does **not** install the gcloud
  CLI. Add `uses: google-github-actions/setup-gcloud@v2` between the
  `auth` step and the preflight step. That action is the documented way
  to install `gcloud` on GitHub Actions runners.
- Cheap — one auth + setup + describe call — and protects against the
  "worker unexpectedly missing" tail of the rollout story that Tier 1.5's
  `needs: deploy-worker` doesn't cover (because deploy-worker is skipped
  when agent didn't change).
- Not blocking Tier 1. Land alongside or after 1.5.

## Explicitly deferred / not doing

- **T6 collection-group write-deny rules test** — `assertFails(addDoc(...))`
  against the concrete `sessions/{sid}/events` path already covers the
  wildcard `{path=**}/events` rule. No separate collection-group write
  target exists in Firestore (writes target documents, not groups).
- **Pre-existing routing regressions** in `test_follow_up_routing.py` —
  out of scope per plan (4 failures; tracked separately).
- **M7 `isFirstMessage` frontend echo** — refuted; backend recomputes.
- **`functions/utils.js` dead exports** — still exercised by
  `functions/utils.test.js`; deletion requires test removal too. Honour
  the plan's "post-smoke" deletion.
- **`streamingText` state cleanup** — dead in new transport but still
  rendered by `ChatThread.svelte` typewriter. Needs a UI simplification
  pass; not blocking durability.
- **`sse-client.ts` deletion** — plan says post-smoke.
  `ios-sse-workaround.ts` stays regardless (transport-agnostic).

## Execution order

Tier 1 → Tier 2 → Tier 3 → Tier 4, with optional hardening anywhere in
Tier 1 once 1.5 lands. Within Tier 1:

- **1.1 first.** Removing the stale terminal path unblocks 1.3's "session
  doc is the sole terminal source" contract.
- **1.2 and 1.3 land as one commit.** Both mutate the same `async for`
  region (`worker_main.py:608-632`) — keeping them together avoids
  conflict churn and halves the retest cost.
- **1.4 independent** of worker changes.
- **1.5 CI-only**; land last so workflow changes don't block other work.
- **2.2 interacts with 1.2/1.3** (all three touch the event-loop area). Do
  2.2 immediately after 1.2+1.3 to clean up the redundant `_cancel_heartbeat`
  calls in one sitting.

After each tier, run the full test gate. Commit per logical unit; keep
diffs small enough that `git bisect` stays useful.

## Post-Tier-1 verification

After Tier 1 lands, re-run the live E2E smoke at
`agent/tests/e2e_worker_live.py` (same harness that surfaced the sources
bug) against a real Firestore + Agent Engine. Must confirm:

- Session doc `sources` array is non-empty for a multi-specialist run.
- A router clarification query (e.g. deliberately ambiguous input without
  place context) produces `status='complete'` with the router's reply,
  not `status='error'`.
- No stale terminal event doc leaks — session doc is the only path that
  triggered `onComplete` in the test harness log.

Save the new log + JSON report under `agent/tests/` with a suffix like
`_post_fixes`.

## Test gate (after each tier)

```
npm run test                                            # Vitest
npm run check                                           # svelte-check
cd functions && npm test                                # Node (index + watchdog + utils)
npm run test:rules                                      # Firestore rules emulator
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ \
  --ignore=tests/test_router_evals.py                   # agent suite
```

Baseline: capture current counts on a clean `main` checkout before the
first fix commit. The only pre-existing failures allowed are the 4 in
`test_follow_up_routing.py` — any other failure is a regression from the
fixes. Report deltas in the execution-log update (exec log + audit cite
different functions-suite counts — 41 vs 120 — depending on whether
`utils.test.js` is counted separately; don't trust either without a
fresh run).

## Execution-log update

Append a new section titled "Follow-up triage (post-review cleanup)" to
`docs/pipeline-decoupling-execution-log.md`, with:

- Per-fix bullet: what changed, file(s), test(s) added.
- Deferred items and the reason they are deferred.
- Updated suite counts after the full sweep.
- Post-deploy manual-smoke checklist unchanged (re-run after first prod
  deploy).

Prettier-format every markdown file touched.
