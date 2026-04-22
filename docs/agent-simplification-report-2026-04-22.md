# Agent Pipeline Simplification — Final Report

> Landing: 2026-04-22. Seven commits on `main` (`e9ad54f` → `4fb9936`).
> Plan: `docs/agent-simplification-plan-2026-04-22.md`.
> Review that drove the plan revision: `docs/agent-simplification-plan-review-2026-04-22.md`.

## TL;DR

Six sequential refactor phases + one post-review cleanup pass, each deployed and live-verified before the next started. The pipeline emerged smaller, less layered, and without the `MALFORMED_FUNCTION_CALL` hotspot that was clustering on the synthesizer's final step. Backend net change: **−239 LOC**. Frontend net: **+285 LOC** (a new Chart.js-based chart renderer, replacing what used to be base64 PNG inlining on the backend). Instruction markdown: **819 → 783 lines**; `_SOURCE_GUIDANCE` went from ~17 lines × 10 injections to ~5 × 10 per run. All four test suites green across every phase. Zero `MALFORMED_FUNCTION_CALL` events observed in post-deploy live runs.

One honest caveat: Phase 5's gap-researcher gate is aggressive (runs only on specialist model errors). It saves tokens on the happy path but throws away gap research's non-error uses (contradictions, weak coverage). Noted for revisit — see _Followups_.

## Motivation

The pre-refactor pipeline had six structural weaknesses that accumulated naturally:

1. **Source-block inflation.** `_append_sources` wrote `## Sources` markdown into specialist text; gap researcher and synthesizer re-read those URL lists for reasoning.
2. **`code_execution` on the largest call.** Synthesizer attached Gemini's native code-exec tool to run matplotlib; produced `MALFORMED_FUNCTION_CALL` failures clustered on the final step.
3. **Four-layer reply rescue stack.** Callback-level fallback + empty-response repair + worker-level degraded stitching + sanity gate — all added in one commit as a P1 response, signalling a contract problem between callback and mapper.
4. **`include_contents='default'` everywhere.** Every agent inherited full conversation history, even though instruction templates already resolved context from state keys at runtime.
5. **Unconditional gap researcher.** Gemini Pro + MEDIUM-thinking + 3 searches on every turn, even when specialists covered the question fully.
6. **Prompt duplication.** `_SOURCE_GUIDANCE` injected into ~10 agents; tone/language/legal boilerplate repeated across 3+ instruction files; router worked-examples sprawled.

## What shipped

| Phase   | Commit    | Headline                                                                                                               | LOC Δ (±)                      |
| ------- | --------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| 1       | `e9ad54f` | Delete `_append_sources`; worker accumulates grounding sources from specialist activity events                         | −132 code, −139 obsolete tests |
| 2       | `7450c13` | Remove `code_execution` from synth; charts emitted as ` ```chart <JSON>``` ` fences; frontend Chart.js renderer        | −154 backend, +285 frontend    |
| 3       | `b924f53` | Collapse the worker-level degraded-reply stitch; keep sanity gate                                                      | −59                            |
| 4       | `c84b30e` | `include_contents='none'` on specialists, gap researcher, synthesizer                                                  | +24 (config only)              |
| 5       | `dc3ad16` | Gate gap_researcher on real specialist failure shapes (`Research unavailable: …` or missing state)                     | +100 / −23                     |
| 6       | `5814c11` | Trim `_SOURCE_GUIDANCE`; drop duplicated tone boilerplate; condense router examples to a table                         | −40 net                        |
| cleanup | `4fb9936` | Collapse synth-fallback branches via `_classify_synth_response`; fix 3 stale comments; E2E harness accepts `E2E_QUERY` | +46 / −34                      |

Backend reduction (`git diff --stat e9ad54f^..HEAD -- 'agent/'`): **+432 / −671 = −239 LOC** across `.py` and `.md`.
Frontend addition: +285 LOC of Chart.js rendering infrastructure (chart-block splitter + Svelte component + unit tests).

## Verification approach

Every phase followed the same gate before moving on:

1. `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` — green.
2. `npm run test` (Vitest) — green.
3. `cd functions && npm test` (Node test runner) — green.
4. `npm run lint` — 0 errors.
5. `npm run build` — succeeds.
6. Commit + push → GitHub Actions deploy → Firebase Hosting + Cloud Run.
7. Live E2E via `agent/tests/e2e_worker_live.py` against real Firestore + Vertex AI + Places.
8. Inspect the terminal session doc in Firestore — status, reply shape, `sources[]`, chart fences.
9. For user-facing work (Phase 2 chart fences), visual verification via Chrome DevTools MCP against the dev server.

Test counts at end of the pass: **148 agent pytest**, **88 Vitest**, **47 functions**. Zero regressions introduced across the series.

## Stress test — post-landing

Three varied live queries against the production worker on 2026-04-22 after the final cleanup (`4fb9936`). All three against Noma, Copenhagen as the `[Context:]` anchor.

| Query                                                                              | Elapsed |       Reply | Sources | Charts                                 | `synth_outcome` | Gap gate               |
| ---------------------------------------------------------------------------------- | ------: | ----------: | ------: | -------------------------------------- | --------------- | ---------------------- |
| "How do entree prices compare to other top fine-dining restaurants in Copenhagen?" |    203s | 6,971 chars |      37 | 2 × bar (5 points each)                | `ok`            | `skip` (3/3 succeeded) |
| "What does guest sentiment look like across TripAdvisor and Google reviews?"       |    268s | 5,375 chars |       0 | 1 × bar, 1 × pie                       | `ok`            | `skip`                 |
| "What's the broader competitive landscape for Nordic fine dining?"                 |    267s | 9,186 chars |      33 | 1 × bar (6 points), 1 × pie (4 points) | `ok`            | `skip`                 |

Observations:

- **Zero `MALFORMED_FUNCTION_CALL` across all three runs.** Phase 2's code_execution removal holds.
- **Chart fences emitted on every run** — all three produced at least one chart spec, and chart types now include pie in addition to the bar charts that dominated earlier runs.
- **Q2's `sources=0` is expected, not a regression.** Review-sentiment queries route heavily through `review_analyst`, which uses structured TripAdvisor / Apify API tools rather than URL-producing `google_search`. No URLs are discovered → no sources in the terminal doc. The grounding-based accumulator is correctly surfacing zero when there are none to surface.
- **Gap gate consistently fired skip** because every assigned specialist succeeded. Confirms the Phase 5 gate behaves as designed and is observable in the logs. Also confirms the open Followup: gap research never runs on any of these queries, including the broad "Nordic landscape" query that is exactly the type where cross-checking has the most value.
- **Elapsed times clustered in 200–270s** (down from the 300–345s range seen in earlier per-phase verifications), consistent with the cumulative effect of `include_contents='none'`, shorter prompts, and the deterministic synth path.

### UI render verification

All chart types confirmed end-to-end via Chrome DevTools MCP on the dev server using Q3's real reply (temp `/chart-test` route):

- **Bar chart** ("Base Tasting Menu Price (DKK)"): 6 bars — Alchemist, Geranium, Noma, Jordnær, Kadeau, Aoc — rendered at correct proportional heights with the cream-toned palette and visible axis labels. Y-axis scaled to 6,000 with proper gridlines.
- **Pie chart** ("Drivers of Low-Tier Reviews (≤ 3 Stars)"): 4 slices sized proportionally to 42/28/21/9, with a legend on the right listing all 4 labels.

No console errors during render. Chart.js's responsive layout kicked in correctly for both chart types inside the 260px-tall container.

The 2 × bar + 2 × pie coverage across Q1–Q3 exercises every chart type currently supported by `ChartBlock.svelte`. Line charts remain unexercised in live runs but have type-checked code paths and splitter unit coverage.

## Key learnings

### 1. Deletion-first discipline pays off

The initial draft plan proposed a separate `chart_agent` agent, new `charts[]` session-doc field, per-agent `*_sources` state keys, and `{name}_error` error protocol. The reviewer caught that as "building replacement architecture in a simplification pass." Reworking the plan to prefer straight deletion + tiny accumulators kept the net LOC negative and did not slow the feature. The cases where we kept existing structure (e.g. one reply string, one `sources[]` field, one synth agent) were all load-bearing decisions.

### 2. Mechanical safety ≠ guaranteed safety

Phase 4's `include_contents='none'` was mechanically safe — instruction providers already resolved everything from state. But "mechanically safe" ≠ "no behavior change." The flip did produce observable differences (more sources harvested: 26 → 36 on matched queries) because specialists operating on their own brief, un-distracted by sibling transcripts, chase slightly different search paths. Net quality improved, but that isn't a guarantee. The reviewer's push to soften "mechanically safe" language and stage the rollout with evals was right.

### 3. "One reply string" is a contract worth preserving

Phase 2 had two obvious shapes: add a new `charts[]` payload field (Case C in the failure plan), or emit chart specs inline in the `reply` markdown (Option D). Option D won not because it was technically superior — Case C would have given structured consumers a cleaner path — but because it preserved the existing reply-delivery contract with zero new pipeline stages, payload fields, TTS changes, or follow-up consumer changes. Simplification wins when it respects contracts, even at the cost of carrying some JSON in prose.

### 4. Plan reviews catch the biggest wins

The plan went through two reviewer passes and two revisions. The biggest improvements came from the reviewer:

- Original plan's `chart_agent` → Option D (inline fences).
- Original plan's `*_sources` state keys → worker-local accumulator.
- Original plan's `{name}_error` protocol → the existing `"Research unavailable: "` prefix check.
- Original plan's Phase 1 assumption "UI already gets sources via grounding" → corrected to "final `sources[]` depends on markdown-parsing today; accumulator must be added."

Each of these was a concrete `[P1]` pushback, and each one made the implementation smaller.

### 5. Visual verification is not optional for UI work

Phase 2's chart fences shipped with passing backend tests, passing type checks, passing build, passing splitter unit tests — and still would have shipped broken if I hadn't opened Chrome DevTools MCP. The canvas rendered bars at full opacity (pixel-sampled), but my first screenshot was scaled down enough that they looked absent. Only a second screenshot zoomed in on the chart region confirmed the user-facing behavior. Saved a memory file: `feedback_ui_verification.md`. Applies to any rendering-adjacent work.

### 6. Gap-gating is really a quality-insurance question, not an error-recovery question

Phase 5 gated gap research on catastrophic model failures. That's defensible as a floor (do-not-ship-broken), but the gap researcher's real value is quality insurance — flagging `WEAK` coverage, surfacing contradictions, investigating sub-angles the orchestrator missed. My gate silently skips all of that on happy paths. Flagged explicitly in the plan doc and in _Followups_ below. This was the one place where the plan's stated goal ("simplicity") and the product's stated goal ("thorough research") pulled in opposite directions.

## Insights

- **Callbacks beat orchestrator-level coordination.** The synth-fallback callback (`_synth_fallback_callback`) owns the entire "did this response succeed?" contract in one function. The previous design spread the decision across callback + mapper + worker loop + sanity gate, requiring all four to agree. Phase 3 collapsed three of those; the remaining two (callback + sanity gate) can't disagree because the callback guarantees `final_report` is set.
- **Telemetry earns its keep across refactors.** The `synth_outcome` event added in commit `c1d69a6` (pre-refactor) was the single best signal for knowing Phase 2 succeeded. Without it, "did we eliminate `MALFORMED_FUNCTION_CALL`?" would have been a guess. Any non-trivial refactor of a failure mode should add structured telemetry for that failure mode first.
- **The specialist catalog drift problem is real and deferred.** `_SPECIALIST_RESULT_KEYS` (agent.py), `_FALLBACK_SECTIONS` (agent.py), `_SPECIALIST_OUTPUT_KEYS` (specialists.py), `AUTHOR_TO_OUTPUT_KEY` + `OUTPUT_KEY_TO_LABEL` (firestore*events.py) are five structurally identical name→key→label mappings in three files. AUTHORING.md warns about it. The plan explicitly deferred fixing it to avoid scope creep. See \_Followups*.

## Followups (prioritized)

### P1 — Revisit the Phase 5 gap gate

The current gate only runs `gap_researcher` when an assigned specialist returns `"Research unavailable: …"` (model-error fallback) or has no state entry. Happy-path runs skip entirely, which discards gap research's non-error value (cross-checks, contradiction detection, weak-coverage repair).

Options:

- **Orchestrator-emitted flag:** have the orchestrator write `needs_cross_check: bool` to state based on the premise assessment (QUESTIONABLE / CONTRADICTED verdicts → run). Cheap to add, reuses reasoning the orchestrator already does.
- **Query-shape heuristic:** always run on broad / exploratory queries (few specialists assigned) where coverage is more likely to be thin.
- **Revert to always-on:** simplest. Accept the token cost; gap research is a quality feature.

Decide after ~1 week of real-user traffic. Monitor: rate of sessions where `gap gate: skip` fired and a user followed up asking about a covered-but-thin angle.

### P2 — Consolidate the specialist catalog

The four name/key/label mappings (agent.py × 2, specialists.py × 1, firestore_events.py × 2) should become one `specialist_catalog.py` module with `{name, brief_key, output_key, label}` tuples. ~50 LOC removed, drift risk eliminated. Explicitly deferred by the plan; should be the next simplification pass.

### P3 — Unify Gemini client construction

`_FAST_MODEL` (agent.py:28–32) hand-rolls the `vertexai + location='global' + retry` config that `_make_gemini` (specialists.py) already encapsulates. Unify via `_make_gemini`. ~10 LOC, removes a silent drift source.

### P4 — Monitor the `extract_sources_from_text` fallback

With `_append_sources` gone, the markdown-link regex fallback in `firestore_events.py` is probably dead for live traffic. Add a counter; after one week of near-zero hits, delete. Removes ~20 LOC.

### P5 — Format-safe specialist template substitution

`_synthesizer_instruction` and `_gap_researcher_instruction` call `str.format(**values)` with specialist outputs as values. If a specialist emits a literal `{` (JSON, URL template syntax, code sample), `.format()` raises `KeyError`. `follow_up.md` migrated to `.replace()` to avoid this. Not introduced by this pass, but worth applying the same fix to synth + gap before it bites.

### P6 — Shared prompt partials (deferred, lower priority)

Tone / language / legal / date boilerplate is deduplicated where it was worst (gap_researcher, synthesizer), but still duplicated across `specialist_base.md`, `router.md`, `follow_up.md`, `research_orchestrator.md`. A shared-partial infrastructure would help, but per the plan's "no new helpers" rule this was deferred. Only worth doing if another round of duplication accumulates.

## Further simplification ideas

Beyond the followups above, these are larger bets worth thinking about before starting:

- **Merge `_SYNTHESIZER_KEYS` and `_GAP_RESEARCHER_KEYS`.** They overlap 100% except for `dynamic_result_2`. Derive one from the other.
- **Replace router with a routing function, not an LlmAgent.** The router's job is classify-the-message; it uses no tools and its decisions are close to deterministic given the conversation state. A rules-based router (with an LLM fallback for ambiguous cases) would cut one Gemini call per turn and remove one instruction file.
- **Investigate whether enricher and orchestrator can merge.** Both look at places_context. Enricher fetches it; orchestrator plans from it. A single agent with Places tools + the orchestrator prompt might be tighter, at the cost of longer per-agent context.
- **Streamline the dynamic researcher.** `dynamic_result_1` / `dynamic_result_2` / `dynamic_researcher_1` / `dynamic_researcher_2` — the 1/2 split is now subtly vestigial after gap_researcher became a first-class specialist in its own right. Worth a day of investigation.
- **Consider TTS + follow-up chart-fence filtering.** Accepted tradeoff in Phase 2 is that `{"type":"bar",…}` JSON flows into TTS and into `follow_up`'s prompt. If either proves noisy in real traffic, a 10-line regex strip at those two consumers fixes it without changing the synth contract.

## What we did not do (and why)

- **Did not add output schemas.** Plan deferred; good choice — Pydantic layers on the router and synthesizer were new abstractions we couldn't justify in a simplification pass.
- **Did not extract prompt partials to a template system.** Plan deferred; small remaining duplication is cheaper than new infrastructure.
- **Did not remove `dynamic_result_2`.** Phase 5's gate might actually kill this field over time (if gap researcher skips most runs); worth reviewing after P1 is decided.
- **Did not write a separate chart agent.** Option D (inline fences) preserves charts as a product feature with less machinery. Revisit only if the inline-in-reply tradeoff proves noisy.

## Retrospective on process

- Six phases ran in three days of elapsed work, all deployed to production, all verified live. That's sustainable for a 1M-context assistant + a responsive human reviewer.
- The first plan draft was rejected at `[P1]` level by review. Revising took two passes. The revised plan was approved and shipped without further architectural changes. **Invest more time in the plan than in the implementation.**
- "Measure per phase, not up front" (adopted after the reviewer called out unverified `25–35%` / `300 LOC` claims) turned out to be the right discipline. The actual numbers were close but smaller, and one claim (chart-agent simplification savings) was moot because we pivoted to Option D.
- The stress-test harness (`tests/e2e_worker_live.py` with `E2E_QUERY`) should stay — it's the fastest way to validate a pipeline change against live Gemini + live Firestore without waiting for real-user traffic.

## Files changed

Backend (primary):

- `agent/superextra_agent/agent.py` — synth factory, fallback callback, classifier
- `agent/superextra_agent/specialists.py` — specialist + gap factory, gate logic, source guidance
- `agent/superextra_agent/firestore_events.py` — unchanged structure, updated comments
- `agent/worker_main.py` — sources accumulator, removed degraded-reply stitch
- `agent/superextra_agent/instructions/synthesizer.md` — chart fence guidance
- `agent/superextra_agent/instructions/gap_researcher.md` — dedup boilerplate
- `agent/superextra_agent/instructions/router.md` — worked examples → table

Backend (tests):

- `agent/tests/test_append_sources.py` — deleted
- `agent/tests/test_embed_chart_images.py` → `test_synth_fallback.py`
- `agent/tests/test_gap_researcher.py` — rewrote for new gate
- `agent/tests/test_worker_main.py` — accumulator + fallback-path tests
- `agent/tests/e2e_worker_live.py` — `E2E_QUERY` env support

Frontend:

- `src/lib/chart-blocks.ts` — new
- `src/lib/chart-blocks.spec.ts` — new
- `src/lib/components/restaurants/ChartBlock.svelte` — new
- `src/lib/components/restaurants/ChatThread.svelte` — wire splitter + chart block
- `package.json` — add chart.js

Docs:

- `docs/agent-simplification-review-2026-04-21.md` — precondition review
- `docs/agent-simplification-plan-2026-04-22.md` — the plan (revised twice)
- `docs/agent-simplification-plan-review-2026-04-22.md` — plan reviews
- `docs/agent-simplification-report-2026-04-22.md` — this document
