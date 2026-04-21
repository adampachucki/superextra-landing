# Pipeline-Decoupling Fixes Plan Review

Review target: [docs/pipeline-decoupling-fixes-plan.md](/Users/adampachucki/src/superextra-landing-vm/docs/pipeline-decoupling-fixes-plan.md)

This pass reviews the current plan revision against:

- the current code
- the earlier audit / validation findings
- the local spike and execution-log evidence
- official documentation for Cloud Tasks, Cloud Run, Firestore, GitHub Actions, Python asyncio, and the Firestore Python client

## Findings

No blocking findings.

No non-blocking findings either in the current revision.

## Verified solutions

The current plan correctly addresses the substantive implementation findings:

- Tier 1.1 removes terminal UI reads from the unfenced `events` observer
- Tier 1.2 accumulates `state_delta` across the worker event loop for source harvest
- Tier 1.3 uses the mapper emission as the terminal source and correctly simplifies the old reply-sanity heuristics
- Tier 1.3 keeps the needed stripped non-empty guard: `not final_reply or not final_reply.strip()`
- Tier 1.4 re-verifies watchdog flips inside a Firestore transaction with status/runId/staleness checks
- Tier 1.5 uses the correct GitHub Actions `needs` + `always()` + `needs.<job>.result` pattern
- Tier 2.1 adds the missing visible retry cue
- Tier 2.2 switches to the safer `try/finally` cleanup structure and treats cancellation waiting as best-effort, which matches asyncio behavior
- Tier 2.3 is correctly scoped to `runId`, matching the real recovery API and avoiding unnecessary surface expansion
- Tier 4.2's Firestore client reuse is supported by the Firestore Python client guidance that client instances are safe to share across threads
- the optional hardening step is now explicit that `deploy-hosting` needs `google-github-actions/setup-gcloud` before the `gcloud` preflight

## Notes on the newer plan additions

These newer notes are sound:

- the whitespace-only terminal reply edge case is real and the `.strip()` guard is the right fix
- expanding `findStuckSessions` return data for Tier 1.4 is necessary; the watchdog transaction cannot safely re-check state without carrying the expected status/runId/threshold metadata forward
- the Tier 2.2 "best-effort" wording is accurate: Python documents that `Task.cancel()` arranges cancellation but does not guarantee completion, and `CancelledError` should generally be re-raised
- the Tier 2.3 closure-based `isDuplicateReply` approach is pragmatic and fits the current `RecoveryContext` shape without widening the interface
- the optional deploy preflight is now specified consistently with the documented GitHub Actions Cloud SDK setup flow

## Bottom line

The plan is implementation-ready from a design standpoint.

I would execute it as written.
