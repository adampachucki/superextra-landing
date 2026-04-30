# Inline narrative cleanup — execution log

**Started:** 2026-04-30  
**Purpose:** Finish the post-ship cleanup for inline narrative progress. The target is lean code: keep the `narrate()` core, remove stale progress-summary/count scaffolding, and add typewriter behavior for LLM notes plus final answers without reintroducing lifecycle complexity.

## Initial audit

- Working tree had only unrelated untracked docs before this pass.
- Some cleanup from the review plan was already present in `HEAD`:
  - completed-turn note rows were already replaced by a simple duration footer in `ChatThread.svelte`
  - `drafting` was already removed from `TimelineEvent`
  - chat-state no longer depended on a backend `drafting` event
  - `map_event()` no longer returned the old `milestones` object
- Remaining cleanup targets:
  - remove unused note `counts` and summary `finalCounts`
  - delete `TurnSummaryBuilder` count accumulation that only fed `finalCounts`
  - add a small component-scoped typewriter for LLM notes and final answers
  - simplify `ProgressWrapper` now that it is only a live "Working" shell

## Backend contract cleanup

- Removed `counts` and `noteSource` from narrate timeline events. The UI renders only text; the extra fields had no consumer.
- Removed `TurnCounts` and `TurnSummary.finalCounts` from the frontend type contract.
- Collapsed `TurnSummaryBuilder` down to elapsed-time footer fields plus detail-row dedupe. Deleted the count accumulator, event walkers, URL/query normalizers, and the dead `GearRunState.seq` counter.
- Updated the affected tests and stale comments that still referenced background note tasks.

## UI cleanup and typewriter

- Replaced `ProgressWrapper`'s completed/minimized/step-count API with a single live "Working" shell. The component is mounted only while work is active, so the old completion label was unreachable complexity.
- Simplified `ProgressEventRow` to the only state it now renders: a completed detail row. Removed running/error/connector props.
- Added `TypewriterText.svelte` plus a small single-instance `createTypewriter()` utility. This intentionally does not restore the old grouped typewriter API.
- Wired typewriter rendering for LLM narrative notes and final answers. Final-answer animation is local to turns observed moving from running/pending to complete in the current browser; already-complete historical turns render immediately.
- Removed the unused `chatState.isStreaming` getter while touching the progress surface.

## Verification

- `rg` check found no remaining `finalCounts`, `TurnCounts`, `noteSource`, `typingMessageTimestamp`, `createTypewriterGroup`, `isStreaming`, `shouldMinimize`, `showConnector`, or `stepCount` references in `src/`, `agent/superextra_agent/`, or `agent/tests/`.
- `npm run test:unit -- --run src/lib/typewriter.spec.ts src/lib/chat-state.spec.ts src/lib/components/restaurants/ChatThread.spec.ts` passed: 39 tests.
- `npm run test` passed: 60 tests.
- `npm run check` passed with 0 errors and 9 pre-existing warnings in unrelated files.
- `npx eslint` on changed frontend files passed with 0 errors and existing `ChatThread.svelte` warnings for unkeyed each blocks and `{@html}` markdown rendering.
- `npx prettier --check` on changed frontend files passed.
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/test_firestore_events.py tests/test_gear_run_state.py -q` passed: 29 tests, 1 dependency deprecation warning.
- `cd functions && npm test` passed: 63 tests.
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` passed: 146 tests, 17 skipped live evals, 1 dependency deprecation warning.
- `JAVA_HOME=/opt/homebrew/opt/openjdk@21 PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH" npm_config_cache=/tmp/superextra-npm-cache XDG_CONFIG_HOME=/tmp/superextra-firebase-config CI=true npm run test:rules` passed: 22 tests. The extra env vars avoid the macOS Java stub, npm cache permission issues, and Firebase CLI update-check writes to `~/.config`.
- `npm run build` passed with the same pre-existing Svelte warnings as `npm run check`.

## LOC snapshot

- Existing tracked files: 150 insertions, 263 deletions, net -113.
- New focused typewriter files: `typewriter.ts` 50 lines, `typewriter.spec.ts` 72 lines, `TypewriterText.svelte` 44 lines.
- Net code/test movement for this cleanup is about +53 lines, with most added lines being targeted tests for the final-answer typewriter rule.
