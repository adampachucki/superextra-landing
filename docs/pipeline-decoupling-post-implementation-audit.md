# Pipeline-Decoupling Post-Implementation Audit

Date: 2026-04-20

## 1. Findings

### [P1] Router-only / clarification replies do not persist as a durable terminal result

Files:

- [agent/worker_main.py](/Users/adampachucki/src/superextra-landing-vm/agent/worker_main.py:629)
- [agent/superextra_agent/firestore_events.py](/Users/adampachucki/src/superextra-landing-vm/agent/superextra_agent/firestore_events.py:163)
- [functions/index.js](/Users/adampachucki/src/superextra-landing-vm/functions/index.js:501)

The worker only promotes `state_delta.final_report` into `final_reply`. Direct router completions are emitted as text content and mapped to Firestore `complete` events, but they are not copied onto `sessions/{sid}`. After the run loop ends, the worker treats the missing `final_reply` as `empty_or_malformed_reply` and writes `status='error'`.

Impact:

- Live listeners can momentarily show the router reply from the event stream.
- Refreshing later, reopening the page, or falling back to `agentCheck` reads the session doc and sees `status='error'` instead of the valid clarification/reply.
- This breaks goal 3 ("returning later still shows final answer or clear error") for router-final turns and weakens the `agentCheck` fallback path.

Why this is real:

- The mapper explicitly emits router text as `type='complete'`.
- The worker completion path only recognizes `final_report`.
- `test_router_evals.py` now passes, so router clarification behavior is definitely exercised in this repo.

### [P1] Deployment ordering is still optimistic: functions can go live before the worker exists or is ready

Files:

- [.github/workflows/deploy.yml](/Users/adampachucki/src/superextra-landing-vm/.github/workflows/deploy.yml:89)
- [.github/workflows/deploy.yml](/Users/adampachucki/src/superextra-landing-vm/.github/workflows/deploy.yml:129)
- [functions/index.js](/Users/adampachucki/src/superextra-landing-vm/functions/index.js:131)

`deploy-hosting` and `deploy-worker` run in parallel after tests. The new `agentStream` code always enqueues to the predicted `superextra-worker` URL. That is not enough to make rollout order safe: if the worker service does not exist yet, or source deploy is still building, `agentStream` can still return `202` while Cloud Tasks dispatches into a missing target.

Impact:

- Early production traffic during first rollout, or any rollout where the worker is absent or delayed, can enqueue tasks that fail before the worker is live.
- Queue retry policy is only `maxAttempts=3`, `minBackoff=10s`, `maxBackoff=60s`, so the retry window is short.
- Those sessions stay `queued` until the watchdog eventually flips them, which is not the intended "auto-retry without manual user action" experience.

Live read-only verification makes this concrete:

- `agent-dispatch` exists and is active.
- The Cloud Tasks service agent has the documented double binding on the worker SA.
- `superextra-worker` does **not** exist in the live `superextra-site` project right now.

That means the repo's current "either order is fine" rollout story is not operationally complete.

### [P2] Watchdog terminal writes are still unfenced and can overwrite a legitimate completion

Files:

- [functions/watchdog.js](/Users/adampachucki/src/superextra-landing-vm/functions/watchdog.js:138)
- [agent/worker_main.py](/Users/adampachucki/src/superextra-landing-vm/agent/worker_main.py:689)

The watchdog flips matched sessions to `status='error'` using an unconditional update. It does not re-check `status`, `currentAttempt`, or `currentWorkerId` before writing. A worker that finishes after the watchdog query runs but before the watchdog update lands can be overwritten back to `error`.

Impact:

- A valid completed reply can later look like a failed session on refresh or via `agentCheck`.
- This is the same durable-state surface the refactor is supposed to harden.

The race window is small, but the failure mode is specifically "final answer existed, later reads show error", which is high-value state corruption for this design.

## 2. Verification Summary

### Commands run

- `npm run test`
- `npm run check`
- `npm run build`
- `cd functions && npm test`
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`
- `npm run test:evals`
- Extra read-only checks with `gcloud` for Cloud Run, Cloud Tasks, Firestore indexes, Firestore TTL
- Extra attempt: `npm run test:rules`

### Passed

- `npm run test` → 8 files, 86 tests passed.
- `npm run check` → passed with 13 pre-existing warnings, 0 errors.
- `npm run build` → passed.
- `cd functions && npm test` → 120 total tests passed (`utils.test.js`, `index.test.js`, `watchdog.test.js`).
- `npm run test:evals` → 10 passed.
- Live read-only checks confirmed:
  - Cloud Tasks queue `agent-dispatch` exists with `maxAttempts=3`, `minBackoff=10s`, `maxBackoff=60s`, `maxDoublings=4`.
  - Cloud Tasks service agent has both `roles/iam.serviceAccountUser` and `roles/iam.serviceAccountTokenCreator` on `superextra-worker@superextra-site.iam.gserviceaccount.com`.
  - Queue IAM grants `roles/cloudtasks.enqueuer` to `907466498524-compute@developer.gserviceaccount.com`.
  - Firestore TTL is ACTIVE for both `sessions.expiresAt` and `events.expiresAt`.
  - Live Firestore composite index exists for collection-group `events` on `(userId, runId, attempt, seqInAttempt)`.

### Failed

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` → 145 passed, 4 failed.
  - Failures are all in [agent/tests/test_follow_up_routing.py](/Users/adampachucki/src/superextra-landing-vm/agent/tests/test_follow_up_routing.py:1).
  - These match the known pre-existing routing issue count called out in the docs.
  - They should not be attributed to the transport refactor.

### Could not verify directly

- `npm run test:rules` could not run in this environment because local Java is missing (`java -version` failed). I did not change the repo to work around that.
- The live project does not currently have the refactor fully rolled out, so end-to-end live transport behavior of the new path could not be verified directly against production.

### Live project state observed

- `agentStream` and `agentCheck` are still live as public Cloud Run-backed gen2 functions.
- Live `agentStream` still reports `timeoutSeconds: 500`.
- `superextra-agent` still exists.
- `superextra-worker` does not exist.
- Live composite indexes currently show the required `events` index, but not the three `sessions` watchdog indexes declared in the repo.

That combination indicates the live project is still on the old transport path, not the fully rolled-out refactor.

## 3. Goal Assessment

### Does the implementation satisfy the original goals?

Partially in repo code, not yet fully in deployed reality.

What is solid in the repo:

- `sid` stays stable in the client conversation model.
- `runId` is freshly server-generated per turn.
- `agentStream` verifies Firebase ID tokens and checks ownership before session reuse.
- First-turn session creation initializes `userId` and `createdAt`.
- Browser Firestore access is read-only by rules.
- Event docs carry `userId`, and the client uses the required `collectionGroup('events')` query ordered by `attempt`, `seqInAttempt`.
- The worker has stale-run guard, ownership fencing, best-effort title generation, and follow-up title preservation.
- `agentCheck` is implemented as a fallback path, not the primary transport.

What still prevents calling this fully complete:

- Router-final turns are not durably completed on the session doc.
- Rollout sequencing is still optimistic for the first live cutover / worker-missing case.
- The watchdog can still overwrite a real completion in a race.
- The live project is not yet on the new architecture, so the repo is ahead of production.

### Is it pragmatic rather than overengineered?

Yes, overall.

Queue + private worker + Firestore + watchdog is still the right shape for this problem, and the implementation mostly stays within that boundary. The issues above are not signs of overengineering; they are completion gaps on core durability guarantees.

## 4. Doc Drift

### Drift against the live project

- [docs/pipeline-decoupling-execution-log.md](/Users/adampachucki/src/superextra-landing-vm/docs/pipeline-decoupling-execution-log.md:763) says first production deploy can let functions and worker land in either order because Cloud Tasks will just retry until the worker is live. The current workflow and live project state do not support that claim safely:
  - the worker service does not exist live,
  - queue retries are limited,
  - and `deploy-hosting` / `deploy-worker` are parallel.

### Drift against current test state

- [docs/pipeline-decoupling-validation-findings.md](/Users/adampachucki/src/superextra-landing-vm/docs/pipeline-decoupling-validation-findings.md:115) still records `test_router_evals.py` as `8 passed, 2 failed`.
- Current rerun in this workspace passed `10/10`.

### Drift in counts / completion claims

- [docs/pipeline-decoupling-execution-log.md](/Users/adampachucki/src/superextra-landing-vm/docs/pipeline-decoupling-execution-log.md:766) still quotes older suite counts (`Vitest 72`, `agent pytest 131 excluding ...`).
- Current local reruns are `Vitest 86` and `agent pytest 149 collected / 145 passed / 4 failed`.

### Residual risks not fully exercised by tests

- The execution log's own test-gap note about `_poll_until_resolved` is still true. There is no direct unit coverage for the poll loop's terminal, stale-run, stale-heartbeat takeover, and timeout branches.
- That matters because duplicate Cloud Tasks delivery handling is one of the refactor's load-bearing behaviors.
