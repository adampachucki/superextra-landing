# Pipeline-Decoupling Final Pre-Deploy Audit

Date: 2026-04-21

Scope: final re-check after the fixes for the three transport findings landed.
Goal: determine whether the transport refactor itself is ready to deploy, and
what non-transport issues still remain.

## Verdict

No blocking transport findings.

The three original findings are fixed in code:

- Router / clarification completions now promote into the durable session-doc
  terminal path in `agent/worker_main.py`.
- `deploy-hosting` now waits for `deploy-worker` and reads the real worker URL
  from Cloud Run before deploying functions.
- Watchdog terminal flips are now fenced in Firestore transactions.

The last deploy-order concern also checks out after a deeper `firebase-tools`
inspection:

- the deploy engine does execute targets sequentially
- but `filterTargets()` normalizes `--only` against the CLI's internal
  `VALID_DEPLOY_TARGETS` list, and Lodash `intersection()` preserves the order
  of that first array
- in the current CLI, that internal order places `functions` before `hosting`

So the combined
`firebase-tools deploy --only hosting,functions,firestore:rules,firestore:indexes`
call still deploys `functions` before `hosting`, which avoids the UI/API
cutover gap.

## Verification summary

### Code paths inspected

- `agent/worker_main.py`
- `functions/watchdog.js`
- `.github/workflows/deploy.yml`
- `src/lib/firestore-stream.ts`
- `src/lib/chat-state.svelte.ts`
- `functions/index.js`
- `docs/deployment-gotchas.md`
- `AGENTS.md`
- installed `firebase-tools` deploy implementation
- installed `firebase-tools` target-filtering implementation

### Commands run

- `npm run test`
- `npm run check`
- `npm run build`
- `npm run lint`
- `cd functions && npm test`
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`
- `npm run test:evals`
- `npm run test:rules`
- read-only `gcloud` checks for Cloud Run + `agentStream`

### Passed

- `npm run test` → 77 passed
- `npm run check` → 0 errors, 13 warnings
- `npm run build` → passed
- `npm run lint` → 0 errors, 22 warnings
- `cd functions && npm test` → 49 passed
- `npm run test:evals` → 10 passed
- transport-focused agent tests in `test_worker_main.py` / `test_firestore_events.py`
  all passed

### Failed / blocked

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`
  - 152 passed, 5 failed
  - 4 failures are in `agent/tests/test_follow_up_routing.py`
  - 1 failure is in `agent/tests/test_router_evals.py`
  - this is worse than the old known baseline and no longer fits the
    "unchanged pre-existing failures" bucket
- full-suite eval behavior is nondeterministic
  - inside the full agent run, `tests/test_router_evals.py::test_asks_for_clarification[salary_needs_location]`
    failed
  - on immediate standalone rerun via `npm run test:evals`, the eval file passed
    10/10
- `npm run test:rules`
  - blocked locally: Java runtime missing

## Remaining issues before deploy

### Not transport blockers

1. Agent routing is still not fully green, and CI currently masks it.
   - The deploy workflow still ignores `tests/test_follow_up_routing.py` and
     `tests/test_router_evals.py`.
   - That was defensible when the failures were a stable known baseline; it is
     stale now that the failure shape has changed again.
   - These remain routing / instruction quality issues rather than transport
     correctness issues, but the workflow no longer reflects actual repo
     health.

2. Warning-only repo hygiene remains.
   - `npm run check` still reports 13 Svelte warnings.
   - `npm run lint` still reports 22 ESLint warnings.
   - Most are longstanding UI warnings; the new transport module still emits
     `state_referenced_locally` warnings in `src/lib/chat-state.svelte.ts`.

3. One stale transport-adjacent cleanup remains in the browser client.
   - `src/lib/chat-state.svelte.ts` still hardcodes the old project-number
     `agentStream` `run.app` URL instead of the currently reported hashed
     service URL.
   - It still resolves today, so this is not blocking, but it is avoidable
     drift.

### Live environment note

Read-only `gcloud` checks still show the live project on the old topology:

- `superextra-agent` still exists
- no `superextra-worker` service is present yet
- live `agentStream` still reports `timeoutSeconds = 500`

That is expected pre-deploy, but it means production has not validated the new
path yet.

## Recommended deploy call

If the goal is specifically to ship the pipeline-decoupling transport refactor,
the transport work is ready.

If the goal is a fully green repo with no changed-shape agent-routing failures,
fix the remaining routing cases first, stop masking them in CI, and then
deploy.
