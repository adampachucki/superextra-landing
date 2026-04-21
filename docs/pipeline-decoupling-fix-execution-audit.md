# Pipeline Decoupling Fix Execution Audit

Date: 2026-04-20

## Findings

1. Live rollout is still incomplete.
   - Read-only `gcloud` checks show the queue exists, but `superextra-worker` does not exist in `us-central1`.
   - `gcloud run services list --region=us-central1 --project=superextra-site` still shows `superextra-agent`.
   - `gcloud functions describe agentStream --region=us-central1 --project=superextra-site --format=json` still reports `serviceConfig.timeoutSeconds = 500`, while the repo now sets `timeoutSeconds: 30`.
   - Result: the repo implementation has moved, but the live project is still on the pre-cutover stack.

2. Refresh recovery still has one text-based dedup path.
   - [`src/lib/chat-state.svelte.ts`](../src/lib/chat-state.svelte.ts) `resumeIfInFlight()` still suppresses a terminal append via `messages.some((m) => m.role === 'agent' && m.text === reply)`.
   - If turn N completes with the same short text as an earlier turn, a reload after completion can still drop the current turn's final answer.
   - Existing tests cover runId dedup on the live subscription path, but not this refresh recovery path.

3. Ownership checks are still nullable on missing `userId`.
   - [`functions/index.js`](../functions/index.js) only rejects on `existing.userId !== uid` / `data.userId !== uid` when `userId` is present.
   - For legacy or malformed session docs without `userId`, both `agentStream` and `agentCheck` would bypass the explicit owner check even though Admin SDK bypasses Firestore rules.
   - Result: the intended `session.userId == decoded uid` invariant is not fully enforced on old docs.

4. The current tree is not quality-gate clean.
   - `npm run lint` fails.
   - `prettier --check` reports formatting drift in:
     - `docs/pipeline-decoupling-post-implementation-audit.md`
     - `functions/index.test.js`
     - `src/lib/chat-state.svelte.ts`
     - `src/lib/firestore-stream.spec.ts`
   - `eslint` reports one error in `src/lib/chat-state.svelte.ts` (`_attempt` unused).

## Verification Summary

Ran locally:

- `npm run test` -> passed, 89 tests
- `npm run check` -> passed with 13 warnings, 0 errors
- `npm run build` -> passed
- `cd functions && npm test` -> passed, 47 tests
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` -> 153 passed, 4 failed
- `npm run test:evals` -> failed once (1/10), then the failing case passed on immediate rerun
- `npm run lint` -> failed
- `npx eslint .` -> failed
- `npm run test:rules` -> could not run locally; Java runtime missing

Failure classification:

- `agent/tests/test_follow_up_routing.py`: 4 failures, same known pre-existing file and count
- `npm run test:evals`: one live-model router eval flaked (`salary_needs_location`) on the first rerun and passed immediately on a single-test rerun; ambiguous / nondeterministic, not attributable to the transport refactor
- `npm run lint` / `npx eslint .`: current-tree quality failures, including one real lint error in the changed chat-state file

Read-only live checks:

- `gcloud tasks queues describe agent-dispatch` -> queue exists, `maxAttempts: 3`, `minBackoff: 10s`, `maxBackoff: 60s`
- `gcloud run services list --region=us-central1 --project=superextra-site` -> no `superextra-worker`; old `superextra-agent` still present
- `gcloud functions describe agentStream --region=us-central1 --project=superextra-site --format=json` -> `serviceConfig.timeoutSeconds: 500`
- `gcloud functions describe agentCheck --region=us-central1 --project=superextra-site --format=json` -> function exists

## Assessment

The repo implementation is much closer to the intended architecture now:

- worker terminal promotion is fixed
- watchdog fencing is implemented and tested
- event-stream terminals are retired on the client
- retry UI and runId-based dedup are mostly in place
- deploy ordering in the workflow is corrected

But the execution is not complete yet:

- the live project is still not on the new worker-backed transport
- one refresh-recovery path still uses reply-text dedup
- owner checks are still too permissive on missing `userId`
- the current tree is not lint/format clean

## Recommendations

1. Fix `resumeIfInFlight()` to use run-scoped terminal dedup instead of reply-text dedup, then add a test for refresh-after-complete with repeated short replies across turns.
2. Tighten `agentStream` and `agentCheck` ownership checks so missing `userId` is rejected or explicitly healed during a controlled legacy migration path.
3. Make the tree pass `prettier --check` and `eslint` before treating it as merge-ready.
4. Verify the deployment actually landed: `superextra-worker` must exist, and live `agentStream` must match the repo's 30-second config instead of the current 500-second pre-cutover value.
