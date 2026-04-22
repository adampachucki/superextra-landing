# Agent Pipeline Simplification

> Revised 2026-04-22 after the review in `docs/agent-simplification-plan-review-2026-04-22.md`.
> Deletion-first discipline. No new agents, no new state protocols, no new prompt helpers unless a direct deletion demonstrably fails.

## Context

The agent pipeline has accreted structural inefficiencies that inflate runtime tokens and concentrate reliability risk in the final step:

1. **Source-block inflation.** `_append_sources` mutates specialist text with ~0.5–1.2 KB of `## Sources` markdown per run; gap_researcher and synthesizer then re-read that text for reasoning, paying tokens for URL lists the narrative never uses. The event mapper already extracts sources from `grounding_metadata` onto specialist activity events (`firestore_events.py:270-281`), but those activity-event sources are **not accumulated into the terminal session doc** today — the final `sources[]` comes from `_extract_sources_from_state_delta` parsing `## Sources` markdown out of specialist output text (`worker_main.py:460-475`). Deletion is still the right move; it just needs a small worker-side accumulation step to preserve the final list.
2. **Synthesizer code-execution coupling.** `_inject_code_execution` adds Gemini's native code-exec tool to the final (biggest-context) step so the model can run matplotlib. `MALFORMED_FUNCTION_CALL` is an active P2 (`docs/synthesizer-malformed-function-call-plan.md`). Every synth failure currently funnels through a stacked rescue path.
3. **Four-layer reply rescue stack** (`agent.py:140, 195`; `worker_main.py:498, 790`). All added `c1d69a6` as a deliberate P1 response to a real incident, but the root cause is the synthesizer tool contract — once code execution is removed from synth, layers collapse to one callback fallback + one sanity gate.
4. **`include_contents='default'`** on every agent. Specialists inherit enricher/orchestrator/sibling history implicitly. Instruction templates already resolve all needed context via state keys at runtime (`specialists.py:152-173`). Switching to `'none'` on specialists → gap → synth is a strong simplification, though not a total-isolation guarantee (current-turn context still flows).
5. **Gap researcher runs unconditionally.** Uses Gemini Pro + MEDIUM thinking + 3 searches (~30–50K tokens, 20–40s) even when all specialists succeeded. The only existing gate is `_skip_if_no_outputs` (`specialists.py:307`), which checks a template _default_ `"Agent did not produce output."` — that string is never actually written by a specialist; real failure shapes are `"NOT_RELEVANT"` (skipped/unassigned, `specialists.py:195`), `"Research unavailable: <ExceptionType>"` (model error, `specialists.py:205`), or a tool-error dict (`specialists.py:212`).
6. **Prompt duplication.** `_SOURCE_GUIDANCE` (919 chars) is injected into ~10 agents; 7 instruction files repeat language/date/legal/tone boilerplate; router examples are long. Specialist catalog is duplicated between `research_orchestrator.md:59-70` and `specialists.py:265-273` (acknowledged drift risk in AUTHORING.md) but fixing that is a separate concern from this simplification pass.

Intended outcome: fewer moving parts (not a number target), the `MALFORMED_FUNCTION_CALL` root cause removed, and measurable-but-unspecified token reduction dominated by `include_contents='none'` and the gap-researcher skip. Token and LOC savings will be measured per phase, not promised up front.

## Charts: product constraint

Charts are a required product feature — removing them (review's Case B) is off the table. The revised plan preserves charts via **inline chart-spec blocks** emitted in the synth reply markdown, rendered by the frontend. This removes the `code_execution` root cause without building a second reporting pipeline.

## Recommended order

Structural-then-editorial, deletion-first, dependency-respecting. Ship each phase as a single PR. Tests green + one live eval run before proceeding.

---

### Phase 1 — Delete `_append_sources`; accumulate specialist sources in the worker

**Why first:** lowest risk, enables `include_contents='none'` (specialists must not rely on sibling source markdown). `_map_specialist` already emits grounding-derived sources on specialist activity events (`firestore_events.py:260-286`). Today the terminal session `sources[]` is built by parsing `## Sources` markdown from specialist output text (`worker_main.py:460-475`); that markdown-parse path must be replaced by accumulating the already-emitted specialist activity-event sources, or the final list will shrink.

**Changes (deletion + one small worker accumulator):**

- `agent/superextra_agent/specialists.py`
  - Delete `_append_sources` (lines 25–74).
  - Remove `after_model_callback=_append_sources` from `_make_specialist` (line 253) and from gap_researcher construction.
  - Delete the unused `_web_search_queries` state write along with it.
- `agent/superextra_agent/worker_main.py`
  - In the event loop, when a specialist activity event carries `data.sources`, append them into a run-scoped `specialist_sources` list (dedup by URL) alongside the existing `accumulated_state` dict.
  - In the terminal-reply assembly (~lines 696–716), replace `state_sources = _extract_sources_from_state_delta(accumulated_state)` with `state_sources = specialist_sources`. Merge with `mapper_sources` exactly as today.
  - Delete `_extract_sources_from_state_delta` (lines 460–475) once the accumulator is in place.
- Instruction files: remove any `## Sources` formatting guidance in `specialist_base.md` and specialist-specific instructions.

**No new ADK state keys. No new payload fields. One small in-worker list.**

**Tests:**

- Delete `test_append_sources.py`; replace with a regression test asserting specialist output text never contains `## Sources`.
- Add a worker test: feed two specialist activity events with overlapping `data.sources` → final `sources[]` contains the deduped union.
- `test_firestore_events.py` mapper tests already exercise the grounding path — ensure they still pass.

**Verify:** pytest green; one live pipeline run; terminal session `sources[]` count and UI source pills match baseline.

---

### Phase 2 — Remove `code_execution` from synth; inline chart specs (Option D)

**Why second:** removes the root cause of `MALFORMED_FUNCTION_CALL` (tool-use in the largest-context step) without introducing a separate chart agent, a new `charts[]` payload, or a new pipeline stage. Charts stay in the narrative; the **shape** of chart content in the reply changes from base64 PNG to JSON chart-spec blocks inside fenced code blocks.

**Not Case C.** The review is correct that a separate chart_agent with its own payload field and new pipeline stage is "a second reporting pipeline" — not a simplification. Option D keeps one synth, one reply string, one output contract.

**Changes (deletion-first):**

- `agent/superextra_agent/agent.py`
  - Delete `_inject_code_execution` (lines 110–123) and its registration on the synthesizer (line 285).
  - Gut `_embed_chart_images` (lines 168–273): keep ONLY the error_code / empty-response / no-text fallback branches (~45 LOC); delete image-parsing, base64-inlining, size-checks (~80 LOC). Rename to `_synth_fallback_callback`.
- `agent/superextra_agent/instructions/synthesizer.md`
  - Replace the matplotlib/code-execution chart block (lines 44–50) with a short instruction to emit chart specs as fenced code blocks, e.g. ` `chart\n{"type":"bar","title":"…","data":[…]}\n` `. Rules: bar/pie/line, max 3 charts, skip if no numeric data.
- `src/lib/components/restaurants/ChatThread.svelte` (corrected path from review) + the markdown renderer used there
  - Add a chart-block handler: when the markdown renderer sees a ` ```chart ` fence, parse the JSON and render via a lightweight chart library (Chart.js or similar). The reply string is unchanged in shape — same `reply` field.

**No new state key, no new payload field, no new agent, no pipeline change.**

**Known tradeoff — mixed `reply` contract.** `final_report` will contain both narrative prose and machine-readable chart fences. That text flows into two downstream consumers:

- `follow_up.md` injects `{final_report}` verbatim (`agent/superextra_agent/instructions/follow_up.md:5-21`) — the model will see chart JSON in its context.
- The TTS layer reads `msg.text` directly (`src/lib/components/restaurants/ChatThread.svelte:88-89`).

This is an accepted tradeoff for keeping one synth + one reply string. If live observation shows follow-up quality or read-aloud audibly degrades, the targeted fix is a small strip/filter step at those two consumers (regex out ` ```chart ... ``` ` fences) — not a new chart pipeline.

**Tests:**

- From `test_embed_chart_images.py`: keep the 6 fallback tests (renamed to `test_synth_fallback.py`); delete the 3 image-embedding tests (`test_valid_image_replacement`, `test_bogus_image_index_unchanged`, `test_oversized_image_skipped`).
- Add a synth-output format test: model emits chart-fenced block → reply contains well-formed JSON.
- Frontend: unit test for the chart-block renderer (well-formed spec → chart; malformed → graceful fallback to code block).

**Verify:** pytest + `npm run test` green; live run on a numeric-heavy query (pricing comparison) produces chart-fenced blocks in the reply and renders them; `synth_outcome` event distribution (from `c1d69a6` telemetry) shows `MALFORMED_FUNCTION_CALL` rate drops to zero; sanity-check one follow-up on a charted report and one TTS playback to confirm the tradeoff is cosmetic only.

---

### Phase 3 — Collapse rescue stack

**Why third:** only safe once Phase 2 removes the main failure mode. The callback + worker-level redundancy exists because the synth callback and the event mapper disagreed on "success" when `code_execution` was involved. A tool-free synth has a deterministic terminal-state contract.

**Gate on live observation:** do not ship Phase 3 until Phase 2 has run for at least one full deploy cycle with zero `MALFORMED_FUNCTION_CALL` events observed in `synth_outcome`.

**Changes:**

- `agent/superextra_agent/worker_main.py`
  - Delete `_build_degraded_reply` (lines 498–512) and its invocation (lines 773–780). The callback fallback (`_synth_fallback_callback` from Phase 2) populates `final_report` whenever specialists produced anything.
  - Keep the sanity gate (lines 790–803).
- `agent/superextra_agent/agent.py`
  - Merge the error_code + empty-response branches in `_synth_fallback_callback` — they call the same `_build_fallback_report`.

**Tests:**

- Delete `test_degraded_reply_builds_from_specialist_state` and `test_degraded_reply_returns_empty_when_no_specialist_output`.
- Keep sanity-gate tests.
- Add integration test: stub synth emits empty → callback fallback populates `final_report` → sanity gate passes.

**Verify:** pytest green; live run with stub-forced synth failure produces a valid fallback reply without touching worker-level degraded path.

---

### Phase 4 — `include_contents='none'` on specialists → gap → synth

**Why fourth:** safe now that (a) sources are out-of-band and (b) synth is tool-free. Instruction templates resolve context via state keys at runtime.

**What this actually does:** switches the agent from receiving prior ADK conversation history to receiving only current-turn context (instruction + its own input). It is a strong simplification. It is **not** total isolation — current-turn context still flows. Treat as a staged rollout with eval gates, not a guaranteed no-regression change.

**Changes:**

- `agent/superextra_agent/specialists.py`
  - `_make_specialist` (line 245): pass `include_contents='none'`.
  - `make_gap_researcher` (line 320): same.
- `agent/superextra_agent/agent.py`
  - `_make_synthesizer` (line 276): same.

**Rollout (per-agent, eval between steps):**

1. One specialist (e.g., `market_landscape`) — compare output quality + token count vs baseline.
2. Remaining specialists.
3. Gap researcher.
4. Synthesizer.

Router, enricher, orchestrator, follow_up keep defaults — they use history.

**Tests:** fixtures that inject briefs into state and assert equivalent output without sibling history; `npm run test:evals` (RUN_LIVE_EVALS).

**Verify:** per step, one end-to-end live query; compare reliability + tokens vs baseline. Roll back the affected agent if quality regresses; address by making the missing context explicit in the brief.

---

### Phase 5 — Minimal gap-researcher gate

**Why fifth:** depends on specialists being stable with `include_contents='none'`. Saves one Gemini Pro call when no specialist failed.

**Minimal gate — match the runtime's real failure shapes, no new state protocol.** Specialists today can produce:

- `"NOT_RELEVANT"` — skip callback fired because no brief was assigned (`specialists.py:195`). This is a valid skip, not a failure.
- `"Research unavailable: <ExceptionType>"` — model-error fallback (`specialists.py:205`).
- A missing state key entirely — specialist crashed before emitting anything.
- Otherwise, a normal markdown output on success.

**Changes:**

- `agent/superextra_agent/specialists.py`
  - Extend `_skip_if_no_outputs` (lines 307–317) → `_should_run_gap_researcher(callback_context)`:
    - **Run** if, for any required specialist output key:
      - the key is missing from state, OR
      - the value starts with `"Research unavailable: "` (model-error fallback).
    - **Skip** if all required specialists succeeded OR emitted `"NOT_RELEVANT"` (intentional skip).
  - Log the decision + reason (per-specialist status) for ops visibility.

No `{name}_error` state keys. No source-count heuristic (review correctly noted review_analyst is URL-free; 3+ sources would misclassify it). If the minimal gate proves too coarse in production, add signals later.

**Tests:**

- All specialists succeeded → skip.
- One specialist missing from state → run.
- One specialist emitted `"Research unavailable: RuntimeError"` → run.
- One specialist emitted `"NOT_RELEVANT"`, rest succeeded → skip.
- All specialists `"NOT_RELEVANT"` → skip (existing no-outputs behavior preserved).

**Verify:** pytest green; 10 varied live queries; confirm gap researcher skips on success and runs on real failures.

---

### Phase 6 — Direct prompt deletions

**Why last:** lowest marginal value; safer to land after structure is settled so regressions are attributable to edits, not architecture.

**Deletion-only. No new helpers, no shared-partial infrastructure, no `output_schema`/Pydantic layer.**

**Changes:**

- `agent/superextra_agent/specialists.py`
  - Trim `_SOURCE_GUIDANCE` (lines 116–132) — shorten in place. Do not refactor into a separate injection point.
- `agent/superextra_agent/instructions/*.md`
  - Manually delete duplicated language/date/legal/tone boilerplate from the 7 files that repeat it. Accept the small remaining duplication as cheaper than a shared-partial system.
- `agent/superextra_agent/instructions/router.md`
  - Condense examples (lines 28–33, 48–53, 64–69, 76–79) into a compact table or bullet list.

**Explicitly deferred to a later pass (not this one):**

- `_build_orchestrator_catalog()` helper to de-duplicate the specialist catalog.
- Shared prompt-partial infrastructure.
- `output_schema`/Pydantic structured outputs.

**Tests:** `npm run lint`, `cd agent && pytest`, `npm run test:evals`.

**Verify:** live queries produce equivalent routing + synthesis quality; eval suite passes.

---

## Critical files

- `agent/superextra_agent/agent.py` — synth factory, synth fallback callback
- `agent/superextra_agent/specialists.py` — `_make_specialist`, `_make_instruction`, delete `_append_sources`, extend skip gate
- `agent/superextra_agent/firestore_events.py` — unchanged (grounding path already emits specialist activity-event sources)
- `agent/superextra_agent/worker_main.py` — add specialist-sources accumulator (Phase 1); delete `_extract_sources_from_state_delta` and degraded-reply stitching; keep sanity gate
- `agent/superextra_agent/instructions/synthesizer.md` — swap matplotlib guidance for chart-fenced-block guidance
- `agent/superextra_agent/instructions/router.md` — condense examples
- `agent/superextra_agent/instructions/specialist_base.md` + 6 others — delete duplicated boilerplate
- `src/lib/components/restaurants/ChatThread.svelte` + its markdown renderer — add chart-fenced-block handler

## Reusable existing pieces

- `extract_sources_from_grounding()` — `firestore_events.py:337` (already emits sources onto specialist activity events; Phase 1 accumulator reads from there)
- Specialist activity-event `data.sources` — `firestore_events.py:270-283` (Phase 1 accumulator input)
- Existing failure shapes: `"NOT_RELEVANT"` / `"Research unavailable: …"` — `specialists.py:195, 205` (Phase 5 gate inputs; no new state needed)
- `InstructionProvider` closure + state-key substitution — `specialists.py:152-173` (Phase 4 relies on this)
- `synth_outcome` telemetry — `c1d69a6` (Phase 2/3 gate signals)
- Sanity gate — `worker_main.py:790-803` (Phase 3 keeps this)

## Verification — end-to-end per phase

1. **Unit**: `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` and `npm run test` after each phase.
2. **Integration**: `cd functions && npm test` after any phase touching mappers or terminal payload.
3. **Rules**: `npm run test:rules` — not expected to trigger, since session-doc shape is unchanged.
4. **Live pipeline**: after each phase, run one full research query:
   - Verify session doc fields: `reply`, `sources[]` unchanged in shape; reply text now contains chart-fenced blocks instead of base64 images after Phase 2.
   - Inspect `synth_outcome` event distribution — `MALFORMED_FUNCTION_CALL` rate should be zero after Phase 2.
5. **Token measurement**: before Phase 1, capture baseline prompt+completion token counts for a representative query. After each phase, re-measure. Report actual deltas; do not pre-commit to a target.
6. **Eval gate before merge of Phase 4 & 6**: `npm run test:evals` (live Gemini).
7. **Rollback plan**: each phase is a single PR that reverts cleanly. Phase 4 has per-agent staging inside the phase; revert affected agent only, not the whole phase.

## What was rejected from the earlier draft (and why)

- Separate `chart_agent` + `charts[]` payload + new pipeline stage — was a second reporting pipeline, not a simplification. Replaced with Option D (inline chart-spec blocks).
- Per-agent `*_sources` ADK state keys — new plumbing. Replaced with a worker-local sources accumulator fed by existing specialist activity events.
- `{name}_error` state protocol for the gap gate — new plumbing. Replaced with checks against real runtime failure shapes (`"Research unavailable: "` prefix + missing keys).
- Gating gap_researcher on `"Agent did not produce output."` — that string is a template default, not a written marker. Corrected.
- `_build_orchestrator_catalog()` helper, shared prompt partials, `output_schema`/Pydantic — new abstractions in a simplification pass. Deferred.
- Claimed savings of "25–35% tokens" and "300 LOC" — unverified. Dropped in favor of measuring per phase.
