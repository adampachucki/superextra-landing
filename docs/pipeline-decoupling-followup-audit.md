# Pipeline-Decoupling Follow-Up Audit

Date: 2026-04-20

Follow-up audit after the transport fixes landed. Scope: verify the current
implementation against the decoupling docs, rerun the relevant checks, and
call out remaining code/doc drift plus cleanup candidates.

## Findings

### P1 — Live cutover is still not complete

- Read-only `gcloud` checks still show **no `superextra-worker` service** in
  `superextra-site/us-central1`, while `superextra-agent` still exists.
- `agentStream` is still deployed with `timeoutSeconds = 500`, not the repo's
  30-second config.
- Repo code is now aligned with the worker-backed design, but the live project
  has not fully switched to it yet.

Evidence:

- `gcloud run services list --region=us-central1 --project=superextra-site`
- `gcloud functions describe agentStream --gen2 --region=us-central1 --project=superextra-site`

### No new transport-code regressions found in the landed fixes

The previously reported defects appear fixed in code and test coverage:

- Router/clarification completions now promote into the session doc terminal
  path in `agent/worker_main.py`.
- The events observer no longer treats unfenced event docs as terminal state in
  `src/lib/firestore-stream.ts`.
- The watchdog now fences error flips with transaction re-checks in
  `functions/watchdog.js`.
- Refresh/recovery dedup is now runId-based rather than reply-text-based in
  `src/lib/chat-state.svelte.ts`.
- `agentStream` and `agentCheck` now reject missing-`userId` session docs
  instead of treating them as implicitly owned.

## Verification summary

### Checks run

- `npm run test`
- `npm run check`
- `npm run build`
- `npm run lint`
- `npm run test:rules`
- `cd functions && npm test`
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`
- Read-only `gcloud` checks for Cloud Run, Cloud Functions, and Cloud Tasks

### Passing

- `npm run test` → 74 passed
- `npm run check` → 0 errors, 13 warnings
- `npm run build` → passed
- `npm run lint` → passed (0 errors, warnings only)
- `cd functions && npm test` → 49 passed
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` →
  153 passed, including `tests/test_router_evals.py`

### Failing / blocked

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` →
  4 failures in `agent/tests/test_follow_up_routing.py`
  These match the known pre-existing failure file and count.
- `npm run test:rules` could not run locally because Java is not installed in
  this environment.

### Live infra state observed

- `agent-dispatch` queue exists with `maxAttempts: 3`,
  `minBackoff: 10s`, `maxBackoff: 60s`.
- `agentStream` live timeout is still `500`.
- Live Cloud Run services still include `superextra-agent`; no
  `superextra-worker` service is present.

## Goal assessment

At repo level, the implementation is now in good shape and remains pragmatic:

- durable terminal state is session-doc-backed
- stale worker takeover is fenced
- duplicate delivery and retry paths are accounted for
- browser Firestore access stays read-only
- `sid` / `runId` separation is preserved
- deployment workflow ordering is fixed in code

That said, the work is not complete end-to-end until the live project actually
ships the new worker-backed topology.

## Stale code / cleanup candidates

These are not current transport correctness bugs, but they are legitimate
cleanup targets:

1. `functions/package.json` still carries unused top-level dependencies:
   `@google-cloud/vertexai` and `google-auth-library`.
2. `scripts/mock-stream.js` and the root `mock-stream` npm script are SSE-era
   tooling with no remaining code references.
3. `src/lib/chat-state.svelte.ts` still defines `ChatMessage.partial?: boolean`
   even though the Firestore transport no longer writes partial agent messages.
4. `src/lib/chat-state.svelte.ts` now triggers Svelte
   `state_referenced_locally` warnings during `npm run check`; they do not fail
   the build, but they are worth cleaning up to keep the transport module quiet.

## Doc drift

These docs no longer match the current implementation:

1. `docs/deployment-gotchas.md`
   - still documents `deploy-agent`, `adk deploy cloud_run`,
     `superextra-agent`, and Cloud Functions SSE bypasses.
2. `AGENTS.md`
   - still describes the old test/deploy shape (`SSE client`, `stream parser`,
     four parallel jobs, `deploy-agent`).
3. `docs/pipeline-decoupling-execution-log.md`
   - still contains stale rollout-order notes saying hosting/functions and
     worker deploy in parallel and that Cloud Tasks retry makes the ordering
     harmless.
   - still contains the earlier "Zero hard blockers" review section, which is
     now outdated relative to the later fixes and the still-incomplete live
     cutover.
