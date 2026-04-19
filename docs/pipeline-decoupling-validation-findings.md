# Pipeline Decoupling Validation Findings

Validated on 2026-04-19 against the current repo and live `superextra-site` project resources.

This document is a practical summary of what was actually verified before implementation, what failed, and what should change in the implementation plan as a result.

## Executive summary

The core architecture remains the right one:

- Cloud Tasks as the durable execution boundary
- a dedicated worker that runs ADK in-process
- Firestore as the durable UI state and reconnect channel
- browser refresh/reconnect driven from Firestore, not from a long-lived browser-to-agent stream

That is not overengineering for this repo's failure mode. The current transport is still too tightly coupled to request lifetime, and the validation work did not uncover a materially simpler design that would provide the same stability.

The main corrections from live validation are narrower:

- the Firestore event query absolutely needs the composite index the plan now describes
- the current agent baseline already has routing regressions, so transport work should not be treated as the only source of user-visible instability
- Cloud Tasks to private Cloud Run OIDC auth was more nuanced in this project than the plan assumed

## What was run

### Local repo validation

- `npm run test`
- `cd functions && npm test`
- `npm run check`
- `npm run build`
- `npm run lint`
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`
- `npm run test:evals`

### Live GCP and Firebase validation

- Firestore database inspection in project `superextra-site`
- Cloud Run service inspection for deployed `agentstream` and `agentcheck`
- Cloud Tasks API enablement and queue creation
- scratch Cloud Run services for private/public task-delivery probes
- live Cloud Tasks HTTP dispatches with OIDC
- Firestore listener and query spikes using the real project

## Verified findings

### 1. The overall refactor direction is justified

What was verified:

- the current deployed `agentstream` path is still a request/response HTTP endpoint on Cloud Run-backed infrastructure
- the current deployed `agentcheck` path is a separate short-timeout endpoint
- Firestore realtime listeners do deliver the current matching dataset on initial snapshot and then stream appended data

Implication:

- moving long-running work off the browser-facing request path is the correct design direction
- using Firestore as the reconnect source of truth is appropriate for the "refresh during pipeline execution" goal

### 2. The planned Firestore event ordering query needs a composite index

What was verified:

- a live query against `events` ordered by `attempt` then `seqInAttempt` failed immediately with Firestore error `The query requires an index`
- a simpler single-field ordered listener worked as expected once the query itself was valid

Implication:

- the plan's explicit composite index for the events query is required
- this should be treated as mandatory config, not as runtime-discovered setup

Recommendation:

- keep the explicit `events` composite index in the plan and ship it with `firestore.indexes.json`

### 3. Firestore listener behavior matches the reconnect model the plan expects

What was verified:

- initial snapshot returned existing event docs
- a later event write produced a second snapshot containing the appended doc
- a fresh requery returned the full ordered set

Implication:

- the browser-side "load current session state, then stay attached for new events" model is valid
- refresh/reconnect does not require replaying the original upstream stream

Recommendation:

- keep Firestore as the durable UI transport
- treat `agentCheck` as fallback only, not the primary progress transport

### 4. ADK `Runner(app=app, session_service=...)` is a valid integration point

What was verified:

- the installed `google-adk==1.28.0` exposes `Runner(app=app, session_service=...)`
- a real in-process run using the repo's `app` object worked
- the same session ID could be reused across turns

Implication:

- the planned worker shape is compatible with the current ADK version
- there is no need for a second service boundary inside the worker just to talk to ADK

Recommendation:

- keep the worker design centered on in-process ADK execution with a session service

### 5. The current agent baseline already has routing regressions

What was verified:

- full agent test suite result: `94 passed, 4 failed`
- failing file: [agent/tests/test_follow_up_routing.py](/Users/adampachucki/src/superextra-landing-vm/agent/tests/test_follow_up_routing.py:1)
- live eval result: `8 passed, 2 failed`
- failing file: [agent/tests/test_router_evals.py](/Users/adampachucki/src/superextra-landing-vm/agent/tests/test_router_evals.py:1)

Observed failures:

- some simple follow-ups after a report do not route to `follow_up`
- some messages that should clarify instead transfer to `research_pipeline`

Implication:

- not every user-visible failure should be attributed to the transport layer
- the decoupling refactor should not be considered complete stability work on its own

Recommendation:

- track routing quality separately from transport stability
- do not use current routing behavior as a proxy for transport correctness during rollout

### 6. Cloud Tasks OIDC delivery worked, but only after a project-specific auth adjustment

What was verified:

- Cloud Tasks did attach an `Authorization: Bearer ...` header and `X-CloudTasks-*` headers to dispatched requests
- dispatch to a private Cloud Run service initially returned `403`
- after granting `roles/iam.serviceAccountTokenCreator` to the Cloud Tasks service agent on the target service account, private dispatch succeeded with `200`
- using the service's canonical Cloud Run URL/audience pair also mattered during testing

Implication:

- the auth section of the plan should not rely only on the theoretical `serviceAccountUser` path
- the implementation runbook should use the exact binding set that was proven to work in this project

Recommendation:

- update the implementation notes to include live-validated Cloud Tasks auth setup:
- worker service account has `roles/run.invoker` on the private worker service
- Cloud Tasks primary service agent has `roles/iam.serviceAccountUser` on the worker service account
- Cloud Tasks primary service agent also has `roles/iam.serviceAccountTokenCreator` on the worker service account
- task URL and OIDC audience should use the service's canonical Cloud Run URL

Note:

- this result conflicts with the simpler interpretation of the public Cloud Tasks guide, so the runbook should prefer the working project recipe over the doc simplification

### 7. The current deployed baseline is still public where the plan expects private worker auth

What was verified:

- `agentstream` currently has public invoker access
- `agentcheck` currently runs as a public endpoint as well

Implication:

- moving to a private worker is part of the refactor, not something already true in production

Recommendation:

- treat private worker auth as an explicit implementation milestone, not as an assumed baseline

## Non-blocking repo notes

### Existing checks

- `npm run test`: passed
- `cd functions && npm test`: passed
- `npm run check`: passed with existing warnings
- `npm run build`: passed

### Existing lint issue

- `npm run lint` currently fails because [pipeline-decoupling-plan.md](/Users/adampachucki/src/superextra-landing-vm/docs/pipeline-decoupling-plan.md:1) is not Prettier-formatted

This is not a design blocker for the refactor.

## Recommendations

### Keep

- Keep Cloud Tasks as the async durability boundary
- Keep a dedicated private worker service
- Keep Firestore as the primary progress and reconnect transport
- Keep the watchdog
- Keep `runId` separate from stable conversation `sid`

### Change

- Encode the live-validated Cloud Tasks auth recipe in the plan and implementation checklist
- Treat the Firestore composite index as required infrastructure, not as optional setup
- Keep routing-quality work separate from transport-stability work in rollout and measurement

### Validate again during implementation

- takeover and watchdog transitions under forced failure
- heartbeat cancellation ordering around terminal state writes
- SIGTERM behavior in the real worker container
- first-turn session creation and owner-field initialization
- end-to-end refresh during an in-flight run with Firestore-backed recovery

## Cleanup and project impact

Scratch validation resources were deleted after testing:

- scratch Cloud Run probe services
- scratch Cloud Tasks queue
- scratch service account

Persistent project change from validation:

- `cloudtasks.googleapis.com` is now enabled in `superextra-site`

## Sources

Official references checked during validation:

- [Cloud Tasks: Create HTTP target tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Cloud Tasks OIDC token reference](https://cloud.google.com/tasks/docs/reference/rest/v2/OidcToken)
- [Cloud Run authentication overview](https://docs.cloud.google.com/run/docs/authenticating/overview)
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Run async tasks](https://cloud.google.com/run/docs/triggering/using-tasks)
- [Firestore realtime listeners](https://firebase.google.com/docs/firestore/query-data/listen)
- [Firestore indexing](https://firebase.google.com/docs/firestore/query-data/indexing)
- [Firestore rules conditions](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Firebase Auth persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence)
- [ADK session state](https://adk.dev/sessions/state/)
