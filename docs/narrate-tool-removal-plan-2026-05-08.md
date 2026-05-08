# Remove `narrate()` tool — cleanup plan

**Date:** 2026-05-08
**Status:** Local cleanup executed; production redeploy/browser smoke pending
**Author context:** Investigation triggered by "agent thoughts shown to users feel long." `narrate()` was found to duplicate Gemini's native thought summaries — same column, same styling, adjacent in the timeline, no structural role downstream.

## Goal

Delete `narrate()` and every dependency it carries: the tool definition, the agent registrations, the instruction blocks, the firestore-event mapping, the tests, the frontend type arm, and the rendering branch. End state: progress messaging is carried entirely by Gemini's `include_thoughts=True` summaries (`kind: 'thought'`) plus tool detail rows (`kind: 'detail'`).

## Why this is safe

- **Not used as a step title.** Step titles in `LiveActivity.svelte:111-115` come from a `**Bold lead**` regex applied to _thought_ text, not notes.
- **Not used as the running headline.** The "current activity" label at the bottom of the activity card (`LiveActivity.svelte:53-59`) reads `detail.family` or `thought.author`. Notes fall through to the generic "Updating analysis" string.
- **Not used for grouping or sequencing.** Notes attach to whatever step is current; they don't drive grouping.

What's lost: the ≤25-word brevity floor on "what I'm about to do" lines. Gemini's thought summaries have no such floor — that's the _reason_ this plan exists. Per Vertex docs, thought summaries are best-effort, so a small fraction of turns may have no progress prose at all. We accept that. Engineering a fallback would re-introduce the duplication this plan exists to remove.

## Inventory of touch points

Every place `narrate` or `narration` appears in code (excluding historical execution-log docs and frozen eval audit trails — see "Out of scope" below):

### Agent (Python)

- `agent/superextra_agent/narrate_tool.py` — entire file (the no-op tool definition).
- `agent/superextra_agent/agent.py:13` — `from .narrate_tool import narrate`
- `agent/superextra_agent/agent.py:69` — `narrate,` inside `_ENRICHER_TOOLS`
- `agent/superextra_agent/agent.py:151` — `narrate,` inside `research_lead.tools=[...]`
- `agent/superextra_agent/firestore_events.py:71` — comment "model's own narration of what it's doing"
- `agent/superextra_agent/firestore_events.py:143` — `"narrate": "narration",` entry in `_FUNCTION_TOOL_LABELS` (auto-flows into `_PROVIDER_TOOL_LABELS` via the dict comprehension at line 148)
- `agent/superextra_agent/firestore_events.py:271-279` — the `if name == "narrate":` branch in `map_tool_call`
- `agent/superextra_agent/gear_run_state.py:183` — stale comment "Narrate notes land synchronously"

### Agent instructions (Markdown)

- `agent/superextra_agent/instructions/context_enricher.md:5-7` — entire `## Narrate first` section
- `agent/superextra_agent/instructions/context_enricher.md:39` — `narrate/narration` mention in the "Boundaries" list of forbidden internal labels
- `agent/superextra_agent/instructions/research_lead.md:56` — the **Narrate first.** paragraph inside step 7
- `agent/superextra_agent/instructions/research_lead.md:108` — `narrate/narration` mention in the key-principles list
- `agent/superextra_agent/instructions/specialist_base.md:50` — `narrate/narration` mention in the "Boundaries" list

### Agent tests (Python)

- `agent/tests/test_firestore_progress_hooks.py:62-78` — `test_before_tool_narrate_writes_note`
- `agent/tests/test_firestore_progress.py:690` — fixture returning `{"kind": "note"}`
- `agent/tests/test_firestore_events.py:222-233` — `test_map_event_ignores_tool_parts_after_typed_hook_migration` includes a `narrate` function call in its fixture
- `agent/tests/test_firestore_events.py:255-266` — `test_narrate_tool_call_emits_note`
- `agent/tests/test_firestore_events.py:269-275` — `test_narrate_normalizes_escaped_newlines`
- `agent/tests/test_firestore_events.py:278-279` — `test_narrate_with_empty_text_is_dropped`
- `agent/tests/test_firestore_events.py:282-283` — `test_narrate_with_non_string_text_is_dropped`

### Frontend (TypeScript / Svelte)

- `src/lib/chat-types.ts:27-32` — the `kind: 'note'` arm of the `TimelineEvent` union
- `src/lib/components/agent/LiveActivity.svelte:150-151` — the `if (ev.kind === 'note')` branch in the step-grouping loop

### Frontend tests

- `src/lib/chat-state.spec.ts` lines 614, 620, 626, 631, 647, 670, 713, 719 — fixtures that use `kind: 'note'` as a generic timeline-event placeholder. These tests are not testing narrate-specific behaviour; they exercise listener semantics ("only `added` doc-changes", "timeline persists on completed turn", "hydrate from history"). They need to pivot to a different `kind` (e.g. `'thought'`) but the assertions stay structurally the same.

### Docs (current, non-historical)

- `docs/architecture-overview-for-non-developers-2026-04-30.md:185, 229` — describes the enricher's narration. Update to reflect the new (thought-only) model.

## Out of scope (explicitly not touched)

These are historical/audit artifacts. Editing them rewrites history.

- `docs/inline-narrative-via-narrate-tool-2026-04-30.md`
- `docs/inline-narrative-execution-log-2026-04-30.md`
- `docs/inline-narrative-cleanup-execution-log-2026-04-30.md`
- `docs/lean-agent-cleanup-{plan,overview,implementation-review}-2026-04-30.md`
- `docs/activity-timeline-redesign{,-review}.md`
- `agent/evals/instructions_variants/round{1,2,3,4,5}/research_lead.md` — frozen eval inputs
- `agent/evals/results/**` and `agent/agent/evals/results/**` — directory-level exclusion for all frozen eval run outputs (multiple files contain `narrate` strings)

If we want a record that `narrate` was retired, this plan file plus a short note in the new architecture doc is enough.

## Execution order

The agent runs as a deployed Vertex AI Agent Engine Reasoning Engine; the frontend ships via Firebase Hosting. CI (`.github/workflows/deploy.yml:113, 120`) deploys hosting/functions/firestore on push to `main` and only **warns** if the engine package is stale — it does not call `agent_engines.update`. Engine redeploy is a manual step via `agent/scripts/redeploy_engine.py:339`.

The sequence is **agent first, frontend second**:

### Phase 1 — Agent

1. Delete `agent/superextra_agent/narrate_tool.py`.
2. In `agent/superextra_agent/agent.py`: drop the import (line 13), the entry in `_ENRICHER_TOOLS` (line 69), and the entry in `research_lead.tools` (line 151).
3. In `agent/superextra_agent/firestore_events.py`:
   - Delete the `if name == "narrate":` branch in `map_tool_call` (lines 271-279).
   - Remove the `"narrate": "narration"` entry from `_FUNCTION_TOOL_LABELS` (line 143). The derived entry in `_PROVIDER_TOOL_LABELS` follows automatically via the dict comprehension.
   - Update the comment block at line 71 to remove the "model's own narration" phrasing — it's about thought summaries, not narrate.
4. In `agent/superextra_agent/gear_run_state.py:183`: update the stale "Narrate notes land synchronously" comment to reflect the thought-only model.
5. In the three instruction files:
   - `context_enricher.md`: delete the entire `## Narrate first` section (lines 5-7) and remove `narrate/narration,` from the boundary-list at line 39 (since the term no longer needs to be guarded against in thought summaries — but keep the rest of the list intact).
   - `research_lead.md`: delete the **Narrate first.** paragraph at line 56 (the surrounding numbered step still makes sense without it). Remove `narrate/narration,` from the key-principles list at line 108.
   - `specialist_base.md`: remove `narrate/narration,` from line 50.
6. In `agent/tests/` — delete narrate-specific tests outright, do not replace them:
   - Delete `test_before_tool_narrate_writes_note` from `test_firestore_progress_hooks.py`.
   - Delete the four `test_narrate_*` cases from `test_firestore_events.py` (lines 255-283).
   - In `test_firestore_progress.py:690`, drop the `{"kind": "note"}` fixture entry.
   - In `test_map_event_ignores_tool_parts_after_typed_hook_migration` (line 222), drop the `("narrate", ...)` entry from the `function_calls` fixture. The remaining `google_search` call still exercises the same assertion (mapping returns `[]` for tool parts).
7. Run `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — all pass.
8. Redeploy the Reasoning Engine via `agent/scripts/redeploy_engine.py`. At this point new runs no longer emit `kind: 'note'` events.

### Phase 2 — Frontend

Wait until Phase 1 is deployed and verified. Then:

1. In `src/lib/chat-types.ts`: remove the `kind: 'note'` arm of the `TimelineEvent` union (lines 28-32).
2. In `src/lib/components/agent/LiveActivity.svelte`: delete the `if (ev.kind === 'note')` branch (lines 150-151). The current `else` at line 152 then handles the remaining case (tool detail). Verify the branch logic still type-checks against the trimmed union — TypeScript will flag any miss.
3. In `src/lib/chat-state.spec.ts`: rewrite the eight fixtures in place from `kind: 'note'` to `kind: 'thought'` with `author: 'research_lead'`. The tests exercise listener semantics, not narrate; the assertions stay structurally the same. No helper abstraction.
4. Run `npm run lint && npm run check && npm run test` — all pass.
5. Confirm a real run end-to-end with Chrome DevTools MCP on `localhost:5199`: the activity timeline should still render thoughts, tool details, and step grouping. The only visible difference is the absence of the short narrate line at the top of each step.
6. Push to `main`. CI runs the full test matrix; deploy goes through `.github/workflows/deploy.yml`.

### Phase 3 — Doc tidy (same PR as phase 2, low-risk)

Update `docs/architecture-overview-for-non-developers-2026-04-30.md` lines 185 and 229 to drop the "narrates exactly once" framing. Replace with a one-sentence reflection of the new model — e.g., "the enricher's thought summary surfaces what it's about to look up before it fetches anything."

## Backward compatibility

Events written before the deploy carry a 3-day TTL (`expiresAt` is computed client-side as `datetime.now(timezone.utc) + timedelta(days=EVENT_TTL_DAYS)` in `agent/superextra_agent/timeline.py:16, 81`; the TTL policy lives in `firestore.indexes.json:44`). After Phase 2 deploys, the frontend has no `'note'` arm in `TimelineEvent`; `chat-state.svelte.ts:553` casts Firestore payloads without runtime validation, so an old `'note'` doc falls through to the remaining non-`'thought'` branch in `LiveActivity.svelte` and renders as a tool-detail row using its `text` field. Affects only users viewing a completed turn from the prior 3-day window. Accepted — engineering around it would re-add a code path we are deleting.

## Verification checklist

- [x] `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — green
- [x] `npm run lint && npm run check && npm run test` — green
- [x] `cd functions && npm test` — green (no narrate touch points but full suite confirms nothing else broke)
- [x] `npm run test:rules` — green
- [ ] Reasoning Engine redeployed; a fresh run completes without errors and produces a thought timeline.
- [ ] Browser smoke (Chrome DevTools MCP, `localhost:5199`): activity timeline renders thoughts and tool details, steps still group correctly, "current activity" label still shows author/family while running.
- [x] `rg -n 'narrate|narration' agent/superextra_agent agent/tests src functions` returns zero hits (frozen eval outputs under `agent/evals/results/` and `agent/agent/evals/results/` are excluded by path).

## Optional follow-up — not part of this cleanup

If thoughts still feel long after the duplication is gone, the next lever is a single brevity instruction added to `research_lead.md`, `context_enricher.md`, and `specialist_base.md` — e.g., _"Keep thought summaries to one short sentence per step. State what you're about to do, not why."_ Worth A/B testing; Gemini's thought-summarizer is somewhat indirect to steer.

If that doesn't land it, the next question is whether thought summaries belong in the user-facing activity UI at all — not whether to bolt on a "show more" clamp.
