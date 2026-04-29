# Agent routing redesign — evaluation plan

**Date:** 2026-04-29
**Owner:** Adam (PM); execution: Claude
**Status:** Draft, pre-execution
**Companion:** `docs/agent-routing-redesign-context-2026-04-29.md`
(motivations + findings)

## What we want to know

A **directional A/B comparison** between two orchestration patterns,
fast enough to inform a go/no-go decision in a coffee break. Specifically:

1. Does Variant B (AgentTool-wrapped specialists with rich descriptions)
   produce **comparable or better quality** outputs than Variant A
   (current `set_specialist_briefs` + `ParallelAgent`) across query
   types we expect to be hardest?
2. Does Variant B preserve **comparable latency** (the key risk: parallel
   AgentTool dispatch is model-dependent — if the model serializes calls,
   we lose the parallel fan-out the current `ParallelAgent` guarantees)?
3. Does Variant B **dispatch the right specialists** for queries where
   the current pattern relies on the query-type coverage floor (esp.
   openings/closings, wage/labor)?

**Out of scope for this eval:**

- Production-grade quality gating (would need full grid, ≥3 trials per
  cell, multi-judge ensemble)
- Cost optimization (we accept the spend for this test)
- Plugin lifecycle and frontend verification (covered by separate
  spike work if Variant B passes the eval)

## Approach

Three deliberate choices to keep this fast:

1. **Pairwise judging, not absolute rubric.** Existing harness at
   `agent/evals/pairwise.py` already does pairwise verdicts via a Gemini
   judge. Faster (one prompt sees both outputs), stronger signal per
   token, no need to calibrate absolute scoring across queries.
2. **Focused matrix over full grid.** 4 queries chosen for routing
   diversity; 1 venue (monsun, well-resolved Place ID); 2 trials per
   cell. Total: 16 production runs.
3. **Parallel execution in `run_matrix.py`.** Today combos run
   sequentially. With `asyncio.gather` + `Semaphore(K)`, K=4 cuts
   wall-clock by ~75%. Cost is unchanged (same number of runs).

## Test matrix

**Two query groups** — on-matrix (queries the production floor was
tuned for; tests "does B match A on A's home turf?") and **off-matrix**
(long-tail phrasings the floor doesn't anticipate; tests "does B
generalize?", which is the load-bearing claim of the redesign).
Including off-matrix queries from the first pass — the eval is
worthless without them, because matching A on A's tuned cases doesn't
disprove the null hypothesis "B is no better at the thing we care
about."

**On-matrix (4 queries):**

| Query ID               | Pill                | Expected specialist set (from production floor)                              | Why this query                                                                          |
| ---------------------- | ------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `q1_openings_closings` | competitor_tracking | `market_landscape` + `menu_pricing` + `marketing_digital` + `review_analyst` | Multi-angle. Hardest test of "does rich-description routing pick the right set?".       |
| `q3_price_comparison`  | price_positioning   | `menu_pricing` + `review_analyst` + `marketing_digital`                      | Focused. Spike continuity.                                                              |
| `q4_sentiment_themes`  | sentiment_trends    | `review_analyst` + `guest_intelligence`                                      | Boundary between structured-API reviews and cross-platform qualitative.                 |
| `q8_wage_benchmarks`   | wage_benchmarking   | `operations` + `dynamic_researcher_1`                                        | Smallest production floor; tests "can rich descriptions replace a 2-specialist floor?". |

**Off-matrix (2 hand-crafted phrasings):** drafted as the long-tail
test. These won't match any floor pattern in the production prompt, so
A has to route them via its general guidance and B has to route them
via rich descriptions. Same intent space as the floors, deliberately
worded to evade the rule triggers:

| Query ID           | Hand-crafted text                                                                     | Tests what                                                                                                                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `qX_quietly_dying` | "Which restaurants near us are quietly losing momentum or could be in trouble?"       | Same intent as q1/q2 (closings), no floor-trigger phrasing. Should still surface `market_landscape` + `menu_pricing` (delivery-listing dropouts) + `review_analyst` (rating decline + complaint patterns). |
| `qY_what_to_watch` | "What should I be watching in the local food and drink scene over the next 3 months?" | Vague, multi-angle, doesn't match any floor. Tests whether B reasons about coverage from descriptions alone.                                                                                               |

Add these to a new fixture file `agent/evals/queries_routing_subset.json`
that contains all 6 queries, used by both variants in this eval.
Production `evals/queries.json` is untouched.

**Venue:** `monsun` only (Świętojańska 49, Gdynia; Place ID
`ChIJ48HwEQCn_UYRmVqYQULc9pM`). Resolved Place ID exists in
`agent/evals/venues.json` so no Places API resolution per run.

**Variants:**

- **A (V_baseline):** current production pipeline at git commit
  `dd3abd6` (the head of `main` at eval start, 2026-04-29). Use the
  existing `agent/superextra_agent/agent.py` `app` as-is. Treat
  `research_orchestrator.md` as frozen — no edits during the eval.
- **B (V_agenttool):** AgentTool-wrapped specialists with rich
  descriptions, count-based dispatch principle, no query-type-coverage
  floors. **Wired as the full production-shape pipeline** (see Sec 2
  below) — `SequentialAgent[enricher, orchestrator_b, gap_researcher,
synthesizer]`. Only the orchestrator step changes vs A.

**Trials:** 2 per (variant × query) cell.

**Total runs:** 6 queries × 1 venue × 2 variants × 2 trials = **24 runs**.

## Components to build

### 1. `EventCapturePlugin` (~25 lines) — `agent/evals/event_capture_plugin.py`

A plugin that appends every event into a list. Plugins propagate to
child runners (`agent_tool.py:222-236`), so this captures specialist
events under both Variant A and Variant B. Replaces the current pattern
of consuming events from the runner stream.

```python
from google.adk.events.event import Event
from google.adk.plugins.base_plugin import BasePlugin

class EventCapturePlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="event_capture")
        self.events: list[Event] = []

    async def on_event_callback(self, *, invocation_context, event):
        self.events.append(event)
        return None
```

### 2. Variant B production-shape pipeline — `agent/superextra_agent/agent_v3.py`

A new module exporting `app_v3` — **the full production-shape pipeline**:
`SequentialAgent[ContextEnricher, orchestrator_b, GapResearcher,
Synthesizer]`. Only the orchestrator step changes vs A; enricher, gap
researcher, and synthesizer stay identical to production. This is a
deliberate decision — a stripped orchestrator-only eval would test the
mechanism in isolation, but wouldn't reflect what users experience.
The whole point of the eval is to predict production quality, so the
eval has to run the production-shape pipeline.

Key differences from the spike orchestrator:

- Orchestrator wraps **all 8 briefable specialists** as `AgentTool`s
  (not just 2 like the spike).
- Orchestrator gets a production-shape prompt (recon, premise audit,
  count-based floor, pre-dispatch coverage check) — adapted from
  `research_orchestrator.md` with the query-type-coverage section
  replaced. **The prompt explicitly invites iterative dispatch** — see
  Sec 6 below; this is required for the iterative-dispatch success
  gate to be meaningful.
- Specialists are constructed with `include_contents='default'` (so
  brief from `request` arg is visible) and **without** the
  `_make_skip_callback` (orchestrator only calls specialists it wants).
- `gap_researcher` and `synthesizer` stay as sequential post-steps on
  the orchestrator's output. Each runs at the parent level, no
  AgentTool wrapping, no plugin lifecycle issue.
- Plugin lifecycle: see Sec 3 below for the plan (Option B —
  nested-invocation guard, ~10 lines).

### 3. Per-specialist event capture under AgentTool — Option B

Use `include_plugins=True` on each `AgentTool`, and add a
nested-invocation guard to plugin lifecycle callbacks. ~10 lines per
plugin:

```python
async def before_run_callback(self, *, invocation_context):
    if getattr(invocation_context, "parent_context", None) is not None:
        return None  # nested invocation — parent owns lifecycle
    # ...existing top-level claim/heartbeat logic...
```

Same guard on `after_run_callback`. `on_event_callback` /
`before_tool_callback` / `after_tool_callback` need no change — they
correctly fire per-event in nested invocations.

**Why not Option A** (state-write-only scoring, simpler in the short
term)? Doing it the simple way first then re-running on Option B if
inconclusive costs a full re-run (~$25-75) for trivial savings. The
guard is small and the eval-side benefit is total: per-specialist tool
counts, fetched URLs, token usage all preserved, no path divergence
between A and B in the scorer.

**The guard is also exactly the change Path A would need anyway** if
we proceed to full migration. So we're not throwing away work — we're
prototyping the smallest piece of Path A's plugin refactor and using it
to instrument the eval.

**Verification step:** before running the matrix, manually invoke a
single combo with `print` instrumentation in the guard, confirm it
returns early on child invocations and runs normally on parent
invocations. ~15 minutes.

### 4. Parallelized `run_matrix.py`

Modify `agent/evals/run_matrix.py` to run combos with bounded
concurrency. Sketch:

```python
import asyncio
sem = asyncio.Semaphore(args.concurrency or 4)
async def _run_with_sem(venue, query):
    async with sem:
        return await _run_single(runner, svc, app.name, venue, query, args.variant)
results = await asyncio.gather(*(_run_with_sem(v, q) for v, q in combos))
```

Add `--concurrency` flag (default 4). Existing single-combo flow stays
intact. Vertex AI Gemini 3.1 quota should comfortably handle K=4
concurrent invocations; K=8 is probably the practical ceiling without
checking quotas. Default to **K=4** for safety.

### 5. Pairwise judging — adapt existing `evals/pairwise.py`

`evals/pairwise.py` already does pairwise verdicts using Gemini 2.5
Pro via `_judge_gemini` (`pairwise.py:152-166`, ~14 lines). Adapting
to Claude Opus needs:

- New `_judge_claude(prompt, model)` function — ~20 lines. Anthropic
  SDK shape mirrors Gemini: client → messages.create with system +
  user prompt + max_tokens.
- Dispatch in `main()`: if `model.startswith("claude")` → claude path,
  else gemini. ~10 lines.
- `anthropic` package added to `agent/requirements-dev.txt`. Existing
  Claude API key in env or via `gcloud secret-manager`. ~5 minutes.
- `--judge-system-prompt` flag for the judge instruction (not in the
  current Gemini-only flow because the system prompt is inlined).

**Total adaptation effort: ~30-45 minutes.** Add to build estimate
below.

**Why Claude (not Gemini)?** Same-family correlation bias — judging
Gemini outputs with Gemini 2.5 Pro tends to favor outputs that look
like the judge's own training distribution. Different family
(Anthropic) gives an independent signal.

**Judging dimensions** (per pairwise verdict):

- **Coverage** — did all relevant angles get addressed?
- **Specificity** — concrete numbers, named competitors, sourced claims?
- **Source diversity** — ≥2 source types (delivery platforms, social,
  community, press)?
- **Actionability** — would an operator know what to do?
- **Specialist set correctness** — did the orchestrator dispatch the
  specialists we'd expect for this query? Apply this to **every query
  with a defensible expected set** (all on-matrix queries in the
  matrix above; off-matrix queries get a softer expected set —
  "specialists whose data sources would clearly produce distinct
  insight").

Verdict per dimension + overall winner. Output: `{"winner": "A"|"B"|"TIE",
"dimensions": {<dim>: "A"|"B"|"TIE"}, "supporting_urls": [...]}`.

### 6. Eval-side variant selection

`evals/run_matrix.py` currently builds a temp instructions dir
(`SUPEREXTRA_INSTRUCTIONS_DIR`) and spawns a child Python process. For
Variant B we need it to import a different `app` object — `app_v3`
instead of `app`. Cleanest path: introduce
`SUPEREXTRA_AGENT_APP=app|app_v3` env var, read in the child where
`from superextra_agent.agent import app` lives, switch to `app_v3` if
set. Minimal touch to existing harness.

## Run procedure

1. **Pre-flight checks** (~5 min):
   - Confirm `agent/.venv/bin/python` works
   - Confirm `agent/.env` has Vertex creds, Places key, etc.
   - Confirm `agent/evals/venues.json` has resolved place_id for monsun
   - `git stash` any in-progress changes; create branch `agent-routing-eval`

2. **Build Variant B pipeline** (~1-2 hours):
   - Create `agent/superextra_agent/agent_v3.py`
   - Adapt `_make_specialist` for AgentTool semantics (include_contents,
     no skip callback)
   - Write production-shape orchestrator prompt at
     `agent/superextra_agent/instructions/research_orchestrator_v3.md`
   - Wire `app_v3` with same plugin set (`ChatLoggerPlugin`,
     `FirestoreProgressPlugin`) but `AgentTool(..., include_plugins=False)`
   - Verify `app_v3` builds without errors:
     `.venv/bin/python -c "from superextra_agent.agent_v3 import app_v3; print(app_v3.name)"`

3. **Modify run_matrix.py** (~15-30 min):
   - Add `--concurrency` flag and `asyncio.gather` + `Semaphore`
   - Add `SUPEREXTRA_AGENT_APP` env var support
   - Verify on a single combo before running the full matrix

4. **Run Variant A baseline** (~3-5 min wall-clock):

   ```
   .venv/bin/python evals/run_matrix.py \
       --variant V_baseline \
       --queries evals/queries_routing_subset.json \
       --venues evals/venues_monsun_only.json \
       --out evals/results/V_baseline/ \
       --concurrency 4
   ```

   Expect: 12 result JSONs (6 queries × 2 trials).

5. **Run Variant B** (~3-5 min wall-clock):

   ```
   SUPEREXTRA_AGENT_APP=app_v3 .venv/bin/python evals/run_matrix.py \
       --variant V_agenttool \
       --queries evals/queries_routing_subset.json \
       --venues evals/venues_monsun_only.json \
       --out evals/results/V_agenttool/ \
       --concurrency 4
   ```

6. **Pairwise judge** (~4-5 min):
   For each (query, trial) pair, run pairwise judge:

   ```
   for q in q1_openings_closings q3_price_comparison q4_sentiment_themes \
            q8_wage_benchmarks qX_quietly_dying qY_what_to_watch; do
     for t in 1 2; do
       .venv/bin/python evals/pairwise.py \
           --a evals/results/V_baseline/monsun__${q}_t${t}.json \
           --b evals/results/V_agenttool/monsun__${q}_t${t}.json \
           --out evals/pairwise_verdicts/agenttool/monsun_${q}_t${t}.json \
           --model claude-opus-4-7
     done
   done
   ```

   Total: 12 pairwise verdicts.

7. **Summarize results** (~10 min): aggregate verdicts into a
   `docs/agent-routing-redesign-eval-results-2026-04-29.md` summary —
   wins/losses/ties per query, latency comparison, dispatched-specialist
   accuracy, surprise observations.

**Total wall-clock estimate:** 3-4 hours including building Variant B
(see Time + cost section below for breakdown). The actual eval runs
(steps 4-6) take ~17 min wall-clock.

## Success criteria

Decided up front so we don't post-rationalize.

Total verdicts in this eval: **12** (6 queries × 2 trials). Each is A,
B, or TIE.

### Quality gate

**B is favored on quality** iff:

- **At least 6 verdicts are decisive** (non-TIE) — i.e. the judge
  took a position on the majority of cases.
- **B wins strictly more decisive verdicts than A** — `wins(B) > wins(A)`
  among the non-TIE verdicts.
- **No category collapse** — B doesn't lose **both** trials of any
  single query (would indicate a routing failure for that pattern).

This formulation closes the original tie-handling bug: an all-TIE
verdict set fails the gate (under-6 decisive); an even split among
decisive verdicts fails too (B doesn't win strictly more).

### Generalization gate (off-matrix)

**B passes generalization** iff B wins on **at least 1 of the 2
off-matrix queries** (across both trials). The redesign's load-bearing
claim is "rich descriptions handle phrasings the floor doesn't
anticipate." If B can't win on either off-matrix query, the
description-quality story doesn't hold up — even if B matches A on
A's home turf.

### Routing accuracy gate

For each query with a defensible expected specialist set (all 4
on-matrix queries; both off-matrix queries get a softer set), compute
**dispatched-set Jaccard** against expected. **B is acceptable on
routing** iff median Jaccard across the 6 queries is ≥ 0.6 (i.e.
B dispatches the right specialists more often than not, even when
floors don't tell it to).

### Latency observation (not a gate)

Report median + p95 latency for both variants. **B-slower-than-A is
itself a finding,** not a failure — the spike showed B was sometimes
faster. We characterize the latency relationship; we don't gate on a
ratio. (Original 1.3× ceiling was pessimistic given spike data.)

### Iterative-dispatch observation (conditional)

The v3 prompt explicitly invites iterative dispatch (Sec 2 above —
"call → read → optionally call more"). Given that, the eval observes
whether the orchestrator actually uses the capability:

- **B exhibits iterative dispatch** iff on **at least 1 query trace,**
  the orchestrator emits a second tool call _after_ receiving the
  response from a first tool call (rather than emitting all calls
  in a single turn).

This isn't a gate — it's an observation that informs the path
decision. If B never iterates despite the prompt inviting it, it
means the model decides upfront dispatch is sufficient on these
queries, which is fine. Iterative dispatch's value shows up on
exploratory or contradiction-driven queries; this matrix may not
exercise that. Future evals should include such queries if iterative
dispatch is a strategic priority.

### Path decisions

- **Path A (full migration) green-lit** iff B passes quality
  gate AND generalization gate AND routing accuracy gate. Iterative
  dispatch observation is **strong supporting evidence** but not a
  hard requirement — the canonical-pattern alignment + simpler code
  - verified routing quality is enough on its own to justify the
    migration if all three gates pass.
- **Path B (description-only) preferred** iff B passes quality gate
  but fails generalization or routing accuracy gates. The routing-
  quality win is real but contained; capture it without architectural
  risk.
- **No path forward** iff B fails the quality gate. Investigate why
  before changing direction.
- **Inconclusive** iff fewer than 6 decisive verdicts, OR a clear
  one-query category collapse. Re-run with 4 trials per cell and a
  second judge (Opus + Gemini, agreement-only verdicts).

## Risks & mitigations

| Risk                                                                                                                          | Likelihood | Mitigation                                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Vertex rate limit at K=4 concurrency                                                                                          | Low        | Drop to K=2 if first parallel run fails; cost stays the same.                                                                                                                                  |
| Variant B's orchestrator emits sequential rather than parallel calls (model choice)                                           | Medium     | Spike already showed it parallelizes when prompted to. Production-shape prompt explicitly instructs parallel emission. If still serial, latency degrades; not a quality issue.                 |
| `include_plugins=False` on AgentTool causes specialists to silently misbehave (e.g. missing geo bias from `_inject_geo_bias`) | Medium     | The spike used `include_plugins=False` and specialists worked fine. Geo-bias callback is `before_model_callback`, which is at the LlmAgent level not the plugin level — propagates regardless. |
| Pairwise judge biased toward verbose/long answers regardless of quality                                                       | Medium     | Use Opus (different model family from the system); add explicit dimension scoring; spot-check 2-3 verdicts manually.                                                                           |
| 2 trials per cell isn't enough to see signal through model variance                                                           | Medium     | This is by design — it's a "directional" eval. Inconclusive 4-4 split is a known possible outcome; we re-run with 4 trials in that case.                                                       |
| Variant B orchestrator times out on multi-specialist queries (more model thinking required)                                   | Low        | The 20-min per-run timeout in run_matrix.py is generous. Spike runs were 90-130s including 2 specialists. Even with 5+ specialists and iterative dispatch, well under timeout.                 |
| Production code accidentally depends on `app` import, breaks when `app_v3` defined alongside                                  | Low        | `app_v3` is a separate name; nothing imports it without the env var override.                                                                                                                  |

## Time + cost estimate

**Build (~3-4 hours):**

- `agent_v3.py` + production-shape orchestrator prompt: 1.5-2 hours
- `EventCapturePlugin` + nested-invocation guard for FirestoreProgressPlugin
  and ChatLoggerPlugin: 30-45 min (10 lines × 2 plugins + verification)
- `run_matrix.py` parallelization (`asyncio.gather` + `Semaphore`,
  `--concurrency` flag, `SUPEREXTRA_AGENT_APP` env var): 30 min
- Pairwise judge Opus adaptation (`_judge_claude` function, dispatch
  in main, `anthropic` package, key check): 30-45 min
- Add hand-crafted off-matrix queries to `queries_routing_subset.json`:
  10 min

**Run (~12-15 minutes wall-clock):**

- 24 production runs at K=4 concurrency: ~12 min (assumes
  ~2-min/run; spike data showed 90-130s for 2-specialist runs;
  full-pipeline runs with 3-5 specialists likely 150-250s, capped by
  parallelism)
- 12 pairwise verdicts via Opus: ~4-5 min sequentially

**Summarize (~45 min):** verdict aggregation, latency tables,
specialist-set Jaccard, write-up at
`docs/agent-routing-redesign-eval-results-2026-04-29.md`.

**Cost: $25-75 for 24 production runs + 12 Opus verdicts.**

Sanity-check: a single full-pipeline run involves (a) enricher with
~3-4 Places API calls (≈$0.01), (b) orchestrator with reconnaissance
google_search calls (≈$0.05-0.10), (c) 3-5 specialists each making
~5-10 LLM calls with HIGH-thinking Gemini 3.1 Pro (~$0.20-0.50 per
specialist; thinking tokens dominate), (d) gap researcher (~$0.05-0.15
when it fires), (e) synthesizer (~$0.05-0.10). Per-run total:
**$0.80-2.50**, dominated by specialist thinking-token cost. 24 runs:
**$20-60**. Plus ~$1 in Opus judge calls (12 × ~$0.10/verdict).
Original $15-30 estimate was on the low end; updated range is
**$25-75** depending on how thinking-heavy specialist runs go and
whether gap researcher fires often.

If we want to be more thorough (4 trials, K=2 to be conservative on
quotas): ~30 minutes wall-clock, ~$50-150.

## Open questions before execution

1. **Which Claude model for the judge?** Opus for quality. Sonnet
   would be ~5× cheaper but the absolute cost is small (~$1 across all
   12 verdicts) and judge accuracy is the highest-leverage variable in
   the eval. Recommend **Opus**.
2. **Cleanup on failure:** if Variant B has a structural bug,
   run_matrix will save error JSONs — fine for diagnosis but pollutes
   `evals/results/V_agenttool/`. Use `--force` semantics (already
   exists) so re-runs replace bad JSONs.
3. **Off-matrix query phrasings:** the two queries in the matrix
   (`qX_quietly_dying`, `qY_what_to_watch`) are illustrative drafts.
   Adam should review/replace before running so they reflect actual
   user phrasings he's seen or expects. Cheap to swap.
4. **Off-matrix expected specialist sets:** less defensible than
   on-matrix because the floors don't define them. Pre-decide an
   acceptable set per query before running, captured in the
   `queries_routing_subset.json` fixture as a `expected_specialists`
   field (not used at runtime, only at scoring).

## What this plan deliberately does NOT do

- Doesn't run the full 8-query × 3-venue grid. That's for a future
  validation pass after a path decision.
- Doesn't fully refactor `FirestoreProgressPlugin` or `ChatLoggerPlugin`
  for AgentTool nesting. We add the minimal nested-invocation guard
  (~10 lines per plugin) to make event capture work for the eval —
  that's the smallest piece of Path A's eventual plugin refactor, but
  not the full lifecycle work (heartbeat consolidation, terminal
  payload coordination across nested invocations, etc.). The full
  refactor is gated on Path A being chosen post-eval.
- Doesn't rebuild the eval scorer beyond plugin-based event capture.
- Doesn't ship anything to production. All work lives on a feature
  branch (`agent-routing-eval`) and in `evals/results/V_agenttool/`.

## What follows from this eval

- If Path A green-lit: separate plan for plugin lifecycle refactor +
  eval scorer move to plugin capture + frontend progress verification +
  full grid validation.
- If Path B preferred: separate plan for catalog templating + rich
  descriptions + count-based floor + pre-dispatch coverage check + full
  grid validation.
- Either way: the eval results doc becomes the canonical artifact for
  the path decision; future questions like "does this regress wage/labor
  coverage?" point back to it.
