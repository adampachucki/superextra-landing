# Pipeline Decoupling Implementation Review

Date: 2026-04-21

## Executive Verdict

The architecture is correct and proportionate to the problem. The queue plus private worker plus Firestore plus watchdog design should stay.

The transport refactor is not fully finalized yet, but it does **not** need re-architecture. It needs **targeted fixes** before I would call the work complete:

1. a real live end-to-end run can still terminate with `empty_or_malformed_reply`
2. follow-up routing quality is still failing realistic multi-turn cases
3. a few smaller recovery-path issues remain in the browser client

If the bar is "is the transport design itself the right solution?", the answer is yes. If the bar is "can this whole change be called done and closed?", the answer is no, not yet.

## Scope Reviewed

Primary docs reviewed:

- `docs/pipeline-decoupling-project-brief.md`
- `docs/pipeline-decoupling-plan.md`
- `docs/pipeline-decoupling-deploy-report.md`
- `docs/pipeline-decoupling-fixes-plan.md`
- `docs/pipeline-decoupling-post-implementation-audit.md`
- `docs/pipeline-decoupling-followup-audit.md`
- `docs/pipeline-decoupling-fix-execution-audit.md`
- `docs/pipeline-decoupling-final-predeploy-audit.md`
- `docs/deployment-gotchas.md`

Main code paths reviewed:

- `agent/worker_main.py`
- `agent/superextra_agent/agent.py`
- `agent/superextra_agent/firestore_events.py`
- `functions/index.js`
- `functions/watchdog.js`
- `src/lib/firestore-stream.ts`
- `src/lib/chat-state.svelte.ts`
- `src/lib/chat-recovery.ts`
- `firestore.rules`
- `firestore.indexes.json`
- `.github/workflows/deploy.yml`

## Verification Performed

### Local test runs

- `npm run test` -> passed, 77 tests
- `npm run check` -> passed, 0 errors, 13 warnings
- `npm run lint` -> passed, 0 errors, 22 warnings
- `cd functions && npm test` -> passed, 47 tests
- `npm run test:rules` -> passed, 10 tests
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` -> 155 passed, 4 failed

The 4 failing Python tests are all in `agent/tests/test_follow_up_routing.py`. They are not transport regressions, but they do block calling the overall conversational experience finalized.

### Live end-to-end smoke

I ran `agent/tests/e2e_worker_live.py` against real Google services with valid ADC credentials.

Result:

- failed after about 314 seconds
- handler result: `{"ok": false, "action": "empty_or_malformed_reply"}`
- final session state: `status=error`, `error=empty_or_malformed_reply`
- `adkSessionId` persisted successfully
- progress and activity events were written
- no durable terminal reply landed

Evidence artifact:

- `agent/tests/e2e_worker_live.json`

### Read-only live infrastructure checks

I verified the deployed GCP state with `gcloud`.

Confirmed live and aligned with the intended topology:

- `superextra-worker` exists and is `Ready=True`
- worker timeout is `1790s`
- worker `containerConcurrency` is `1`
- worker service account is `superextra-worker@superextra-site.iam.gserviceaccount.com`
- worker IAM allows invocation by Firebase Admin SDK and the worker service account
- Cloud Tasks service agent has both `roles/iam.serviceAccountTokenCreator` and `roles/iam.serviceAccountUser` on the worker service account
- `agent-dispatch` queue exists with `maxAttempts=3`, `minBackoff=10s`, `maxBackoff=60s`
- queue IAM grants enqueue permission to the project compute service account
- `agentStream` and `agentCheck` are deployed at `timeoutSeconds=30`
- watchdog scheduler exists, enabled, every 2 minutes
- all required composite indexes are `READY`
- TTL policies for both `sessions.expiresAt` and `events.expiresAt` are `ACTIVE`

Noted but non-blocking:

- old `superextra-agent` service still exists alongside `superextra-worker`

## What Is Already Correct

The core refactor goals are largely met in code and infrastructure:

- browser writes no longer depend on a long-lived streaming function response
- turns are scoped by stable `sid` plus per-turn `runId`
- queue dispatch is the durability boundary
- the worker runs the ADK pipeline in-process
- terminal state comes from fenced writes to `sessions/{sid}`
- browser Firestore use is read-only
- watchdog fencing is implemented
- deployment ordering has been corrected
- Firestore indexes, TTL, scheduler, queue IAM, and worker IAM are in place

Several earlier audit findings appear genuinely fixed:

- router/clarification completions are now promotable into the durable session doc path
- watchdog terminal flips are transaction-fenced
- deploy sequencing now waits for the worker and resolves the real worker URL before function deploy

This is why my recommendation is targeted fixes, not rework.

## Findings

### P1 - A real live run can still finish without a durable reply

This is the most important remaining issue.

The live smoke run produced a full pipeline execution, including specialist outputs and a final synthesizer event, but the session still ended as `empty_or_malformed_reply`.

Code path:

- `agent/superextra_agent/agent.py:176-193`
- `agent/superextra_agent/firestore_events.py:289-299`
- `agent/worker_main.py:621-666`
- `agent/worker_main.py:723-736`

What is happening:

1. the worker only promotes a terminal reply when the mapper emits `type="complete"`
2. the synthesizer mapper only emits `complete` when `state_delta.final_report` exists
3. the synthesizer callback fallback only activates when `llm_response.error_code` is set
4. in the failing live run, the synthesizer produced a final event but apparently no usable text and no `final_report` state delta
5. the worker therefore exits the loop with `final_reply=None` and writes `status='error'`

Why this matters:

- this is not theoretical or unit-test-only
- it fails on a real first-turn request against the live stack
- it breaks the central promise of the refactor: long-running work must still converge to a durable terminal answer or a clean, intentional terminal error

Recommendation:

1. Extend the synthesizer fallback so it also covers the "final event with no usable text / no `final_report`" case, not just `error_code`.
2. Tighten the worker/mapper contract so every final synthesizer or follow-up completion produces either a durable reply or an explicit structured terminal error with preserved diagnostics.
3. Add tests for the exact "final synthesizer event, no `state_delta.final_report`, no text content" shape so the worker cannot silently devolve to `empty_or_malformed_reply` without a controlled fallback.
4. Keep `agent/tests/e2e_worker_live.py` as a release gate for this change until it passes consistently.

### P2 - Follow-up routing is still not at release quality

Evidence:

- `agent/tests/test_follow_up_routing.py:124-158`

Current failing cases:

- `"Summarize that in bullet points"`
- `"What did you find about pricing?"`
- `"Can you compare restaurants A and B from the report?"`
- `"What about the delivery market in this area?"`

These are realistic multi-turn prompts. They currently misroute to clarification instead of either `follow_up` or `research_pipeline`.

Why this matters:

- this is not a transport design failure
- it is still part of the shipped user experience created by this project
- if the team wants to say the pipeline-decoupled chat flow is fully done, these failures undercut that claim

Recommendation:

1. Tighten `agent/superextra_agent/instructions/router.md` around the distinction between answerable-from-report follow-ups, new-research requests, and true clarification cases.
2. Keep these prompts in a manual or automated release gate until the behavior is stable.
3. Do not treat these failures as ignorable baseline noise if the release claim is "finalized".

### P3a - Recovery and resume paths drop server-generated conversation titles

Code path:

- `functions/index.js:512-519`
- `src/lib/chat-recovery.ts:30-32`
- `src/lib/chat-recovery.ts:101-105`
- `src/lib/chat-state.svelte.ts:339-343`
- `src/lib/chat-state.svelte.ts:544-560`

What is happening:

- `agentCheck` returns `title` on complete
- the live Firestore terminal path updates title correctly
- the recovery callback shape only carries `reply` and `sources`
- the refresh/resume path appends the recovered reply but ignores `title`

Impact:

- the final answer can recover correctly after refresh or fallback polling
- the conversation title can remain the client-side placeholder instead of the worker-generated title
- this is user-visible specifically in the recovery paths this refactor was meant to harden

Recommendation:

1. Widen the recovery callback/result handling to include `title`.
2. Sync title in both REST recovery and `resumeIfInFlight()`.
3. Add tests for reload-after-complete and REST-fallback-after-complete title sync.

### P3b - Firestore fallback can start duplicate recovery polls

Code path:

- `src/lib/firestore-stream.ts:64-68`
- `src/lib/firestore-stream.ts:115-119`
- `src/lib/chat-state.svelte.ts:362-376`
- `src/lib/chat-state.svelte.ts:603-642`
- `src/lib/firestore-stream.spec.ts:415-424`

The interface comment says `onPermissionDenied` is emitted once, but the implementation does not enforce that. If both Firestore observers error, the callback fires twice. The current test suite explicitly expects that behavior.

Impact:

- likely multiple concurrent `agentCheck` polling loops for the same run
- low correctness risk because terminal append dedup is run-scoped
- unnecessary load and avoidable complexity in failure mode handling

Recommendation:

1. Make fallback start one-shot per subscription or per run.
2. Guard `recover()` behind a local "recovery already started" flag.
3. Update the spec and tests to match the intended one-shot behavior.

## Additional Non-Blocking Cleanup

### P4 - Production endpoint URLs are still hardcoded in the client

Code path:

- `src/lib/chat-state.svelte.ts:244-250`
- `firebase.json:78-86`

The app already has Firebase Hosting rewrites for `/api/agent/stream` and `/api/agent/check`, but production client code still hardcodes direct function URLs.

This is not currently breaking, and the live URLs still resolve. It is still unnecessary drift.

Recommendation:

- use the same-origin rewrite paths in production too

### P5 - The live smoke test fixture itself is inconsistent

Code path:

- `agent/tests/e2e_worker_live.py:67-71`

The test labels the target as `Umami, Berlin`, but the provided Place ID resolves to Noma in Copenhagen. The pipeline noticed this mismatch during the live run.

This did not create the `empty_or_malformed_reply` bug by itself, but it reduces signal quality for the smoke test.

Recommendation:

- align the test's `name`, `secondary`, and `placeId` to a single verified place

## Final Assessment Against the Spec

### Was the implementation broadly faithful to the design?

Yes.

The implemented topology, state model, ownership checks, fencing strategy, recovery approach, and deployment shape all substantially match the plan.

### Did the team address the major issues from the earlier audits?

Mostly yes.

The earlier transport-critical findings around router durability, watchdog fencing, and deploy ordering appear resolved.

### Is the work finalized?

No.

It is close, but I would not sign off on "fully finalized" while:

1. the live E2E worker smoke still fails with `empty_or_malformed_reply`
2. the follow-up routing suite still fails on realistic prompts

### Does it need rework?

No.

The right call here is **targeted fixes**, then a short re-validation pass.

## Recommended Exit Criteria

I would call this ready to close when all of the following are true:

1. `agent/tests/e2e_worker_live.py` passes consistently and writes a durable terminal reply
2. `agent/tests/test_follow_up_routing.py` is green, or the team explicitly narrows scope and stops calling the conversational layer finalized
3. recovery/resume paths preserve titles
4. recovery fallback is one-shot per run

## Official Documentation Consulted

- Cloud Run request timeout: <https://docs.cloud.google.com/run/docs/configuring/request-timeout>
- Cloud Run concurrency: <https://docs.cloud.google.com/run/docs/about-concurrency>
- Cloud Tasks HTTP target tasks: <https://cloud.google.com/tasks/docs/creating-http-target-tasks>
- Cloud Tasks secure delivery: <https://cloud.google.com/tasks/docs/secure-delivery>
- Firestore transactions: <https://docs.cloud.google.com/firestore/docs/manage-data/transactions>
- Firestore TTL: <https://docs.cloud.google.com/firestore/docs/ttl>

---

## Verification + Forward Plan (appended 2026-04-21)

Each review claim was verified against the actual code at HEAD. Per-claim verdict, evidence, and fix approach below. Nothing has been changed yet — this section is the plan the review recommends executing.

### P1 — live E2E `empty_or_malformed_reply` — **CONFIRMED**

Evidence:

- `agent/tests/e2e_worker_live.json` (mtime 2026-04-21 11:14, newer than the `.log` from 2026-04-20 10:38):
  - `handler_result = {"ok": false, "action": "empty_or_malformed_reply"}`
  - `final_session.status = "error"`, `reply_len = 0`, `sources_n = 0`
  - `events.by_type = {activity: 8, progress: 2}` — **zero `complete` events** (vs. the earlier passing run which emitted 1 complete event with `reply_len=336175`). The synth ran, but its event was filtered out by the mapper.
- `agent/superextra_agent/firestore_events.py:289-299` — `_map_synthesizer` returns `None` unless `_has_state_delta(event, "final_report")`. A synth event with text-only content and no `final_report` state_delta produces no event doc and therefore no `complete` event.
- `agent/superextra_agent/agent.py:170-205` — `_embed_chart_images` fallback activates only when `llm_response.error_code` is truthy. It does **not** cover "final event with no usable text / no `final_report`".
- `agent/worker_main.py:723-736` — sanity gate flips `status='error'` when `final_reply is None`. With no mapped complete event and no fallback, this is where the bad state lands.

Instability note: the **previous** live run in the checked-in `.log` file **passed** (complete event, 336 kB reply). So the failure is intermittent, not every time. Both shapes are reachable; the code has no lower-bound contract that guarantees a durable reply on every synth success.

**Fix approach (P1):**

1. **Primary — widen `_map_synthesizer`** (`agent/superextra_agent/firestore_events.py:283-293`):
   - If the event has usable `event.content.parts[*].text`, emit a `complete` event whose `data.reply` is the joined text, even without `state_delta.final_report`. Reserve `final_report` as the preferred source when present (preserves today's format-normalization behavior).
   - Dedup source harvest against `extract_sources_from_text` on the reply.
2. **Secondary — worker-side last-resort fallback** (`agent/worker_main.py:621-666`):
   - If the event loop terminates with `final_reply is None` but `accumulated_state` carries specialist outputs (`market_result`, `pricing_result`, `revenue_result`, `guest_result`, `location_result`, `ops_result`, `marketing_result`, `review_result`, `dynamic_result_1`, `dynamic_result_2`), build a concatenated degraded reply from those sections. Prefer a clearly-labeled degraded reply over `status='error'` on the terminal user experience. Keep `status='error'` only when nothing usable exists anywhere.
   - Do not require a new `reply_quality` session field unless the team explicitly wants the extra schema. A short note in the fallback reply plus logs/tests is sufficient and more pragmatic.
3. **Safety net in the synth fallback** (`agent/superextra_agent/agent.py:170-205`): extend the `error_code`-only guard to also cover "final LLM response with no parts or no text". The `_build_fallback_report` helper already drafts a usable degraded report from `callback_context.state`; invoke it from the empty-response branch too.
4. **Tests** (`agent/tests/test_worker_main.py`, `agent/tests/test_firestore_events.py`):
   - `_map_synthesizer` fixture: event with `.content.parts[0].text` only, no `state_delta` → asserts a `complete` doc emitted.
   - Worker-loop fixture: final event with no `final_report`, no `error_code`, no text → asserts session ends `status='complete'` with degraded reply (if any state) OR `status='error'` with preserved diagnostics (if truly empty), **never** silent `empty_or_malformed_reply` without a recorded fallback attempt.
5. **Release gate:** keep `agent/tests/e2e_worker_live.py` as a mandatory gate for this change; three consecutive passing runs before calling it done.

### P2 — follow-up routing 4 failing realistic prompts — **CONFIRMED, not a transport regression**

Evidence:

- `agent/tests/test_follow_up_routing.py:124-158`: three `SHOULD_FOLLOW_UP` and two `SHOULD_RESEARCH` params, four of which fail per the review. Same four listed as pre-existing baseline failures in earlier tier gates.
- Tests exercise router instructions (`agent/superextra_agent/instructions/router.md`), not Cloud Tasks / worker / Firestore. This is an instruction-quality issue, not a pipeline-decoupling regression.

**Fix approach (P2):**

1. Tighten `router.md` with explicit positive/negative examples for:
   - **`follow_up`**: "Summarize that in bullet points", "What did you find about pricing?", "Can you compare restaurants A and B from the report?"
   - **`research_pipeline`**: "What about the delivery market in this area?", "Now analyze Restaurant D in Krakow"
   - The failing cases trigger on "answerable from existing report" vs. "new-topic fetch" vs. "clarify": add short worked examples and a decision rule in that order.
2. Run `test_follow_up_routing.py` + `npm run test:evals` (live Gemini eval) as a release gate. Do **not** mark conversational layer finalized while these fail.
3. Scope gate: this change is independent of P1; can land in parallel.

### P3a — recovery/resume paths drop server title — **CONFIRMED**

Evidence:

- `functions/index.js:512-519` returns `title: data.title || undefined` on `status=='complete'` — server carries it.
- `src/lib/chat-recovery.ts:30-31` — `onReply(reply, sources)` signature; no `title` parameter.
- `src/lib/chat-recovery.ts:101-105` — reads `data.reply` and `data.sources` only; `data.title` is discarded.
- `src/lib/chat-state.svelte.ts:339-343` — **Firestore observer path DOES sync title** (works).
- `src/lib/chat-state.svelte.ts:544-560` — `resumeIfInFlight()` on `status==='complete'` reads `reply`, `runId`, `sources`; **does not read `data.title`**.
- `src/lib/chat-state.svelte.ts:603-642` — `recover()` passes no title into the `onReply` callback.

**Fix approach (P3a):**

1. Widen `RecoveryContext.onReply` signature in `chat-recovery.ts` to `(reply, sources, title?)` and pass `data.title` through at line 104.
2. Update `chat-state.svelte.ts:recover()` onReply to accept `title` and, when truthy, `conversations[idx] = { ...conversations[idx], title }` before `persist()`.
3. Update `chat-state.svelte.ts:resumeIfInFlight()` on `status==='complete'` to read `data.title` and apply the same "update title if present" pattern.
4. **Tests** (`src/lib/chat-state.spec.ts`):
   - reload-after-complete: session-doc has `title='X'`, resumeIfInFlight runs, conversation title becomes `X`.
   - REST-fallback-after-complete: `agentCheck` returns `{ok, reply, title: 'Y'}`, recover() runs, conversation title becomes `Y`.

### P3b — duplicate recovery polls — **CONFIRMED**

Evidence:

- `src/lib/firestore-stream.ts:64-68` interface comment: "Emitted **once** when either observer returns `PERMISSION_DENIED`." — a contract.
- `src/lib/firestore-stream.ts:115-119` `handleErr` implementation: plain `callbacks.onPermissionDenied?.()` — no once-guard. Both `unsubSession` and `unsubEvents` bind the same `handleErr`, so two errors → two calls.
- `src/lib/firestore-stream.spec.ts:415-425` **explicitly asserts** `permDenied === 2` after both observers error. Test enforces the wrong behavior.
- `src/lib/chat-state.svelte.ts:362-376` `onPermissionDenied` fires `recover().catch(() => {})` without a local "already recovering" guard. Two calls → two concurrent polling loops for the same run.

**Fix approach (P3b):**

1. Add `permissionDeniedFired: boolean` flag in the `subscribeToSession` closure; guard the `callbacks.onPermissionDenied?.()` call. One-shot per subscription.
2. Update `src/lib/firestore-stream.spec.ts:415-425` to assert `permDenied === 1` after both observers error (the intended contract).
3. Belt-and-braces: add a `recoveryStarted` closure flag around `recover()` calls in `chat-state.svelte.ts:362-376` and `:370-376` so double-fire of `onFirstSnapshotTimeout` + `onPermissionDenied` cannot start two polls either.
4. **Tests** (`src/lib/chat-state.spec.ts`): trigger both `onPermissionDenied` **and** `onFirstSnapshotTimeout` on the same subscription; assert `recover()` is invoked **once**.

### P4 — hardcoded production URLs — **CONFIRMED, non-blocking**

Evidence:

- `src/lib/chat-state.svelte.ts:244` hardcodes `https://agentstream-22b3fxahka-uc.a.run.app` in prod.
- `src/lib/chat-state.svelte.ts:250` hardcodes `https://us-central1-superextra-site.cloudfunctions.net/agentCheck` in prod.
- `firebase.json:78-86` already has working rewrites: `/api/agent/check` → `agentCheck`, `/api/agent/stream` → `agentStream` under the `agent` hosting target.
- History: the hardcoded Cloud Run URL for `agentStream` was a workaround for the `cloudfunctions.net` GFE proxy killing SSE streams (`docs/deployment-gotchas.md`). Post-decoupling, `agentStream` is a plain POST-returns-JSON enqueue, so the SSE workaround is no longer load-bearing.

**Fix approach (P4):**

1. Change both URL helpers to use the same-origin rewrite paths in prod:
   ```ts
   function agentStreamUrl() { return '/api/agent/stream'; }
   function agentCheckUrl(sid, runId) { return `/api/agent/check?sid=${...}&runId=${...}`; }
   ```
2. Validate by running a live production smoke test after deploy (first-message + multi-turn follow-up through `agent.superextra.ai`).
3. Do **not** re-introduce the SSE deployment-gotchas note — add a short line under "Cloud Functions streaming" noting that `agentStream` no longer streams, so `cloudfunctions.net` rewrites are fine again.

### P5 — E2E fixture Noma/Umami mismatch — **CONFIRMED, non-blocking**

Evidence:

- `agent/tests/e2e_worker_live.py:67-71`:
  ```python
  PLACE = {"name": "Umami", "secondary": "Berlin", "placeId": "ChIJpYCQZztTUkYRFOE368Xs6kI"}
  ```
- Reviewer claims `ChIJpYCQZztTUkYRFOE368Xs6kI` resolves to Noma, Copenhagen. The pipeline noticed the mismatch during the run, which reduces signal quality for the smoke.

**Fix approach (P5):**

1. Replace the fixture with a single verified place (ideally a real Umami in Berlin, or switch the label to Noma Copenhagen). Verify via Places API (`gcloud places:lookup` equivalent) before committing.
2. Add a one-line comment documenting the source of the Place ID so future edits stay consistent.

---

## Execution order

1. **P1** (blocking): `_map_synthesizer` widening + worker fallback + agent.py empty-response guard + tests + three consecutive E2E passes.
2. **P3b** (UX correctness): one-shot guards in `firestore-stream.ts` and `chat-state.svelte.ts`; fix misaligned spec.
3. **P3a** (UX correctness): widen `onReply` signature, plumb title through `recover()` + `resumeIfInFlight()`.
4. **P5** (test signal): fix the fixture before re-running the E2E gate.
5. **P4** (cleanup): swap to rewrite paths; document.
6. **P2** (conversational quality): router instruction tightening, running behind `test:evals`. Independent track.

Test gate after each tier:

```
npm run test
npm run check
npm run lint
cd functions && npm test
npm run test:rules
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ --ignore=tests/test_router_evals.py
```

Only pre-existing failures allowed are the four `test_follow_up_routing.py` cases until P2 lands.

## Exit criteria (updated)

Ready to close when all of:

1. `agent/tests/e2e_worker_live.py` passes **three consecutive runs**, each writing a durable terminal reply with `status='complete'` and `reply_len > 0` for a multi-specialist prompt. `sources_n > 0` is strongly preferred for research prompts, but should not be the sole pass/fail gate for the transport fix.
2. `agent/tests/test_follow_up_routing.py` is green, OR the team explicitly narrows "finalized" to the transport layer only.
3. Refresh-after-complete and REST-fallback-after-complete both preserve titles (covered by new `chat-state.spec.ts` tests).
4. Recovery fallback is one-shot per run (covered by updated `firestore-stream.spec.ts` + new `chat-state.spec.ts` test).
5. Smoke fixture is internally consistent.
6. (Optional polish) Client uses same-origin rewrite paths in prod.
