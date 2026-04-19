# Review: Pipeline Decoupling Plan

Date: 2026-04-19

Reviewed files:

- `docs/pipeline-decoupling-plan.md`
- `docs/pipeline-decoupling-spike-results.md`
- `docs/pipeline-decoupling-validation-findings.md`

## Verdict

The architecture is still the right one.

Queueing long-running work behind Cloud Tasks, running ADK in-process in a dedicated worker, storing progress in Firestore, and recovering browser state from durable data is still the correct fix for this repo's failure mode. That part is not overengineered.

The major correctness issues from earlier review rounds are now addressed in the current plan. I do not see a remaining blocking design bug. What remains is mostly doc hygiene and a small amount of scope tightening.

**Scope of this document**: this file shows the current review state only. "What Is Correct" summarises items settled across prior rounds (each was a finding once, now resolved). "Findings" below lists only issues still open against the current plan. Prior rounds' raw finding text is preserved in git history — the commit log is the historical record.

## What Is Correct

The current draft gets the important design calls right:

- stable conversation `sid` plus fresh per-turn `runId`
- Cloud Tasks as the durability boundary
- worker-side in-process ADK `Runner(app=app, ...)`
- stale-run guard in worker takeover
- ownership fencing on worker-owned writes
- Firestore as the browser-facing progress channel
- read-only browser rules with Admin SDK writes only
- explicit ownership checks in `agentStream` and `agentCheck`
- `queuedAt` instead of `createdAt` for queued-turn timeout logic
- per-attempt sequencing instead of a hot-doc global counter
- watchdog split across `queuedAt`, `lastHeartbeat`, and `lastEventAt`
- collection-group event query with explicit index
- live-validated Cloud Tasks IAM recipe for OIDC delivery
- title generation moved off the primary completion path
- legacy `sessionMap` reuse dropped from the new design
- partial-text handling correctly deferred out of v1

Those choices are proportionate to the problem and aligned with the repo's actual conversation model.

## Findings

### Finding 1

#### [P2] Spike log still contains the old, wrong `gcloud` limitation

File: `docs/pipeline-decoupling-spike-results.md:187-188`

Finding D.1 still says COLLECTION-scoped indexes "gcloud CLI can't create", but Finding D.3 in the same file corrects that, and the current `gcloud firestore indexes composite create` docs expose `--query-scope=collection`.

That leaves the spike log internally contradictory and can send implementers back toward a false tooling constraint.

Recommended fix:

- remove or rewrite the stale sentence in D.1
- keep the file's final position consistent: collection-group is a design choice, not a CLI limitation

### Finding 2

#### [P2] Review history doc is now stale against the current plan

File: `docs/pipeline-decoupling-review.md:1-999`

This review doc previously still said the current draft had unresolved cleanup findings around title overwrites, partial-text mapper scope, legacy `sessionMap` reuse, and the Firestore "internal index" note.

The latest plan revision has already fixed those. Because the main plan tells implementers to read this file early, stale findings here push them back into already-resolved work and weaken confidence in the docs set.

Recommended fix:

- update this file to reflect the current plan state
- if old findings are worth keeping, label them clearly as historical review context rather than current blockers

### Finding 3

#### [P3] 'Resolve before starting implementation' is stricter than the remaining questions justify

File: `docs/pipeline-decoupling-plan.md:48-66`

The architecture is now settled, but this section still frames several non-load-bearing product choices as preconditions to start.

Items like cross-device error wording, stale-`runId` fallback semantics, turn-error rendering, and Agent Engine cleanup cadence are defaults or deferred work, not blockers for the transport refactor.

Recommended fix:

- rename the section to something like `Open product decisions` or `Defaults to confirm`
- keep only true implementation blockers under a hard pre-start heading

### Finding 4

#### [P3] Worker image dependency list is broader than the worker design needs

File: `docs/pipeline-decoupling-plan.md:254-256`

The worker plan currently installs `firebase-admin` and `google-cloud-tasks` into the Python image, but the worker does not enqueue tasks and its Firestore writes can be handled by `google-cloud-firestore` alone.

Carrying unused libraries makes the image heavier and widens the maintenance surface without improving stability.

Recommended fix:

- keep the worker dependency set aligned with what `worker_main.py` actually imports
- add extra libraries later only if the implementation ends up needing them

## Pragmatic Assessment

### Is the architecture overengineered?

No.

The old design failed at the wrong boundary. Queue + worker + Firestore is the correct boundary shift for this app.

### Are the previous high-severity findings now addressed?

Yes.

The current plan now correctly incorporates the earlier load-bearing fixes:

- `sid`/`runId` separation
- explicit owner checks
- `queuedAt`
- per-attempt sequencing
- collection-group query
- explicit indexes
- double IAM binding
- stale-run guard
- title off the main completion path
- first-turn session initialization
- denormalized `userId` on event docs

### What still feels heavier than necessary?

Only a little:

- the pre-implementation questions are framed too strictly
- the worker dependency list is broader than needed
- the spike log still carries one stale corrected statement

These are simplifications, not architecture changes.

## Final Recommendation

Keep this architecture.

Do not reopen the queue + worker + Firestore decision. That is the right solution shape.

The plan is implementation-ready as a design. Before treating the docs set as fully clean and authoritative, make one more pass to:

- remove the stale `gcloud` limitation from the spike log
- keep this review file aligned with the latest draft
- soften the "resolve before starting implementation" heading
- trim the worker dependency list to what the worker actually uses

After that, the docs should be in strong shape for execution.

## Verified References

- Cloud Tasks issues and limitations: <https://cloud.google.com/tasks/docs/common-pitfalls>
- Create HTTP target tasks: <https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks>
- Cloud Tasks OIDC token reference: <https://docs.cloud.google.com/tasks/docs/reference/rest/v2/OidcToken>
- Cloud Run authentication overview: <https://docs.cloud.google.com/run/docs/authenticating/overview>
- Firestore TTL: <https://firebase.google.com/docs/firestore/ttl>
- Firestore indexing: <https://firebase.google.com/docs/firestore/query-data/indexing>
- gcloud Firestore composite indexes: <https://cloud.google.com/sdk/gcloud/reference/firestore/indexes/composite/create>
- Firestore secure collection-group queries: <https://firebase.google.com/docs/firestore/security/rules-query>
- Firestore realtime listeners: <https://firebase.google.com/docs/firestore/query-data/listen>
- Firebase auth persistence: <https://firebase.google.com/docs/auth/web/auth-state-persistence>
- ADK session state: <https://adk.dev/sessions/state/>
