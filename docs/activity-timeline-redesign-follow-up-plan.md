# Timeline Redesign Follow-up Plan

## Summary

Keep the redesign architecture as-is and make one focused polish pass before shipping.

This pass should only address the issues that materially improve clarity or correctness without reintroducing complexity:

- remove the duplicated counts row in completed summaries
- fix the refresh-mid-flight startup hole
- remove the small dead/duplicate cleanup leftovers
- keep rollout simple: coordinated deploy only, no compatibility layer

Do **not** widen scope into another transport abstraction, old/new event bridging, or detail-row redesign.

## Key Changes

### 1. Completed-turn summary polish

- In the completed reply summary, remove the standalone `finalCounts` line from the bottom of the expanded transcript.
- Keep counts only under each kept note.
- Do not replace this with comparison logic or special-case rendering. The simpler rule is: completed summary shows notes plus their attached counts, nothing else.

### 2. Refresh-mid-flight recovery fix

- Add one explicit public chat-state entrypoint for startup/session restoration, for example `resumeCurrentIfNeeded()`.
- That method should:
  - read the currently active conversation from state
  - return immediately if there is no active conversation
  - return immediately if the last message is not from the user
  - otherwise call the existing Firestore-based in-flight resume path
- Use this method from the chat page startup flow after URL/localStorage restoration instead of relying on `recover()` when `currentRunId` is still unknown.
- Keep `recover()` as the Firestore-fallback / visibility-return path only.
- Do not persist `currentRunId` to localStorage. Keep Firestore as the source of truth.

### 3. Small cleanup pass

- Simplify the live timer expression in `StreamingProgress.svelte` to a direct `startedAtMs ? now - startedAtMs : 0` style check.
- Remove the duplicate `research_placeholder` filtering in `TurnSummaryBuilder.finalize_notes()`.
- Do not change the note-generation architecture, milestone model, or drafting trigger.

### 4. Explicit non-changes

- Do not add old/new event-contract compatibility.
- Do not add the temporary `?newTimeline=1` rollout gate now.
- Do not change detail-row verbosity yet.
- Do not optimize the LLM-note freeze race in this pass unless it falls out trivially from another edit. It is acceptable to leave as-is for now.

## Interfaces / Behavior

- Add one public chat-state method dedicated to startup resumption.
- No backend API shape changes.
- No Firestore schema changes.
- No worker event-contract changes.
- No completed-summary wire-shape changes; only the renderer changes.

## Test Plan

### Automated

- Add or update a state-level test proving startup resumption works when:
  - an active conversation exists
  - the last message is from the user
  - `currentRunId` is not locally known yet
  - the Firestore resume path is invoked
- Add or update a rendering test proving completed-turn summaries do not render a duplicate bottom counts row.
- Keep all existing timeline, recovery, worker, and function tests green.

### Acceptance scenarios

- Reload the chat page during an in-flight run where `?sid` already matches the active conversation:
  - timeline reattaches
  - terminal reply still lands
  - no manual retry is needed
- Complete a run and expand the `Worked for …` summary:
  - notes render
  - counts render under notes
  - no duplicate totals line appears at the bottom
- Live timeline still shows:
  - elapsed time
  - note rows
  - grouped detail rows
  - drafting row
- Completed reply still keeps:
  - answer
  - sources
  - collapsed summary transcript

## Assumptions

- The deploy model remains a single coordinated deploy, with worker landing before hosting via the existing workflow.
- The current deployed worker being old-contract is treated as an operational rollout fact, not a reason to add compatibility code.
- The goal of this pass is polish plus one real startup bug fix, not another redesign cycle.
