# Review: Pipeline Decoupling Plan

Date: 2026-04-19

Reviewed file: `docs/pipeline-decoupling-plan.md`

## Verdict

The architecture is still right.

Decoupling execution from the browser, running the agent in a dedicated worker, storing progress in Firestore, and letting the browser recover from durable state is still the correct solution shape for this repo's failure mode. The queue + worker + Firestore design remains proportionate and not overengineered.

The plan is close to implementation-ready, but two P1 correctness issues remain in the current draft.

## What Is Correct

The current draft gets the main design decisions right:

- long-running execution is moved behind Cloud Tasks
- ADK runs in-process in the worker instead of through `/run_sse`
- Firestore is the durable browser-facing progress channel
- browser Firestore access is read-only
- `sid` and `runId` are separated correctly
- timeout/deadline alignment is correct
- ownership fencing is present
- worker auth is simplified to private Cloud Run IAM
- queued-session timeout uses `queuedAt`, not `createdAt`
- `agentStream` and `agentCheck` have explicit ownership checks
- events now denormalize `userId` for simpler and cheaper rules
- the watchdog query split and indexes are directionally correct

These are the changes that matter for your stated goals: no stuck sessions, safe refresh during long runs, same-browser continuity, and automatic retry on infrastructure failures.

## Repo Facts That Matter

Two current codebase facts still shape the correct design:

1. `src/lib/chat-state.svelte.ts` reuses a stable conversation ID as `sessionId` across multiple `send()` calls.
2. `agent/superextra_agent/agent.py` uses persistent ADK session state to decide whether a report already exists in the current conversation.

That means the system must keep:

- one stable conversation/session identity
- one fresh per-turn run identity
- serialized turns on the same conversation

That part of the plan is justified by the repo and by ADK session behavior. It is not accidental complexity.

## Findings

### Finding 1

#### [P1] New sessions still do not explicitly initialize `userId` and `createdAt`

The transaction now checks ownership on existing sessions, but the create path still only lists `userId` and `createdAt` under "Preserved if existing".

If implemented literally, a brand-new `sessions/{sid}` document can be created without those fields. That breaks the Phase 1 read rule:

- `request.auth.uid == resource.data.userId`

on the first turn, and it also weakens later owner checks and the watchdog backfill assumptions.

This is a blocking issue.

Pragmatic correction:

- if the doc does not exist, explicitly set:
  - `userId = decodedToken.uid`
  - `createdAt = serverTimestamp()`
- only preserve those fields on later turns when the doc already exists

### Finding 2

#### [P1] Event writes no longer match the new `userId`-denormalized rules contract

The denormalization change is correct in principle, but the Phase 3 event-write call still invokes `write_event` without `userId` even though Phase 2 changed the mapper contract to require it and the Firestore rule for `events/{eid}` now checks `resource.data.userId` directly.

If implemented as written, one of two things happens:

- the mapper API does not match the call site
- or event documents are written without `userId`

In the second case, the browser will be denied access to progress events, which breaks the core refresh/reconnect goal.

This is a blocking issue.

Pragmatic correction:

- pass `user_id` into every `write_event(...)` call in the worker
- make the event doc contract and the worker call site agree exactly

## Non-Blocking Cleanup

Two cleanup items remain, but neither changes the architecture recommendation:

1. The risk table still references the old Phase 0 threshold (`< 25 min`) even though the main plan now uses `< 22 min`.
2. The Firebase bundle-size figure is a planning estimate, not something independently verified from a repo build here.

## Recommended Changes Before Implementation

Update the plan with these concrete changes:

1. Make the create path explicit for brand-new sessions.
   - if `sessions/{sid}` does not exist:
   - set `userId = decodedToken.uid`
   - set `createdAt = serverTimestamp()`
   - then set the per-run fields

2. Make the event-write contract consistent.
   - pass `user_id` to `write_event(...)` from the worker stream loop
   - ensure every event doc includes `userId`

3. Clean up stale wording.
   - update the risk table to the new `< 22 min` gate
   - keep bundle-size language clearly as an estimate unless measured

## Pragmatic Assessment

### Is the architecture overengineered?

No.

Given the current SSE-coupled implementation, Cloud Run request behavior, Cloud Tasks delivery semantics, Firestore listener behavior, and ADK session behavior, the queue + worker + Firestore design is the right amount of system for this problem.

The old design failed because execution was still coupled to the browser connection. This plan fixes that at the correct boundary.

### Is there unnecessary complexity left?

Very little.

The remaining issues are not architectural churn. They are implementation-contract mismatches: one around first-session initialization, and one around the event schema used by Firestore rules.

### Is the design stable after the current changes?

Almost.

Once the two blockers above are corrected, I would consider this design stable, proportionate, and ready to implement.

## Final Recommendation

Keep this architecture.

Do not reopen the queue + worker + Firestore decision. That part is justified by the codebase and by the documented behavior of the Google/Firebase components involved.

Revise the plan first to:

- explicitly initialize `userId` and `createdAt` on first session creation
- pass `userId` into event writes so the new rules contract is actually satisfied

After those changes, this is a proper long-term fix rather than another temporary workaround.

## Verified References

- Cloud Tasks overview: <https://docs.cloud.google.com/tasks/docs/dual-overview>
- Create HTTP target tasks: <https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks>
- Cloud Tasks OIDC token reference: <https://docs.cloud.google.com/tasks/docs/reference/rest/v2/OidcToken>
- Cloud Run authentication overview: <https://docs.cloud.google.com/run/docs/authenticating/overview>
- Cloud Run general development tips: <https://docs.cloud.google.com/run/docs/tips/general>
- Firestore security rules conditions: <https://firebase.google.com/docs/firestore/security/rules-conditions>
- Firestore secure query guidance: <https://firebase.google.com/docs/firestore/security/rules-query>
- Firestore pricing: <https://firebase.google.com/docs/firestore/pricing>
- Firestore realtime listeners: <https://firebase.google.com/docs/firestore/query-data/listen>
- Firestore index overview: <https://firebase.google.com/docs/firestore/query-data/index-overview>
- Firestore TTL: <https://firebase.google.com/docs/firestore/ttl>
- Firebase anonymous auth: <https://firebase.google.com/docs/auth/web/anonymous-auth>
- Firebase auth persistence: <https://firebase.google.com/docs/auth/web/auth-state-persistence>
- ADK session state: <https://adk.dev/sessions/state/>
