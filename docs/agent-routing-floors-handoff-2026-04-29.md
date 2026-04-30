# Agent routing — floor experimentation handoff

**Date:** 2026-04-29
**Status:** Open work — handoff to whoever picks up the floor question
**Predecessor:** `docs/agent-routing-rearchitecture-deploy-log-2026-04-29.md` —
the AgentTool migration shipped on 2026-04-29 (commit `a313b50`); this doc
is about the _next_ phase of that work, deliberately deferred.

## What this document is

A self-contained brief for a separate team picking up the floor question.
Written so you don't need to read the prior thread or any companion docs to
start work — but pointers to them are at the end if you want depth.

## What the agent is, in 30 seconds

Superextra runs a multi-agent research pipeline on Google ADK 1.28 +
Vertex AI Gemini 3.1 Pro. Live at `agent.superextra.ai/chat`. For each user
query, the pipeline:

1. **Router** classifies the message and routes to research or follow-up.
2. **Context Enricher** fetches Google Places data for the target restaurant.
3. **Research Orchestrator** picks specialists, calls them as `AgentTool`s
   (parallel, sometimes iterative), produces a research plan.
4. **Specialists** (8 of them, all `AgentTool`-wrapped) each do focused
   research: menus/pricing, reviews, social/digital, foot traffic, etc.
5. **Gap Researcher** is a gated Phase-2 fallback. Its prompt frames it
   as auditing Phase 1 outputs for gaps and contradictions, but in
   current code (`specialists.py:_should_run_gap_researcher`) it skips
   when all called specialists succeeded — it normally runs only when a
   specialist returned an explicit error fallback (e.g. "Research
   unavailable: TimeoutError"). Treat it as failure-recovery, not a
   universal quality auditor.
6. **Synthesizer** writes the final operator-facing report.

Code lives in `agent/superextra_agent/`. Specialists are defined in
`agent/superextra_agent/specialist_catalog.py`. Orchestrator behavior is
prompt-driven — see `agent/superextra_agent/instructions/research_orchestrator.md`.

## What "floors" are

The orchestrator's prompt at `research_orchestrator.md:78-100` contains a
section called **"Query-type coverage requirements"** — five hardcoded
rules of the form:

> **Openings/closings questions** ("what opened/closed recently?") — MUST
> call `market_landscape` + `menu_pricing` + `marketing_digital` +
> `review_analyst`.

The five rules cover:

1. **Openings/closings** → `market_landscape + menu_pricing + marketing_digital + review_analyst`
2. **Pricing-comparison** → `menu_pricing + review_analyst + marketing_digital`
3. **Wage/labor** → `operations + dynamic_researcher_1`
4. **Sentiment/review** → `review_analyst + guest_intelligence`
5. **Market-saturation/concept-validation** → `market_landscape + location_traffic`

These are floors — required tool calls for that query type, additive to
whatever the orchestrator picks otherwise. They exist because each pairing
encodes a specific cross-check or non-obvious data-source role that the
orchestrator wouldn't reliably infer from the specialist's description
alone.

## Why this is even a question

The PM concern that started the whole investigation: **hardcoded
query-type rules don't scale to long-tail phrasings.** Real customer
queries arrive in countless variations. Per-rule maintenance breaks down
once you have 30+ specialists or a wide enough query distribution. The
fundamental question:

> Should we hardcode query-type → specialist mappings, or should the
> orchestrator reason about coverage from rich specialist descriptions?

Anthropic's Research multi-agent system, LangGraph supervisor, Claude
Code, and the Google ADK `LlmAgent` documentation all point in the same
direction: **rich descriptions are the canonical routing primitive.** The
hypothesis: replace floors with descriptions that encode each
specialist's unique capabilities (live data sources, cross-checks,
boundaries with neighbors), and the orchestrator should route correctly
without prescriptive rules.

## What we tried (the 2026-04-29 eval)

We built **Variant B** — descriptions fattened to encode each
specialist's unique signal, query-type-coverage floors _removed_,
replaced with a count-based principle ("≥2 specialists, ideally 3"). Ran
24 production-shape pipeline runs (6 queries × 1 venue × 2 variants × 2
trials), pairwise-judged each pair with both Gemini 2.5 Pro and Claude
Opus 4.7.

**Result:** Variant A (with floors) won **10 of 12** under Gemini, **11
of 12** under Opus. Zero ties. Different model families confirmed the
result independently.

Detail in `docs/agent-routing-redesign-eval-results-2026-04-29.md`.

### What B got wrong, specifically

Three concrete failure modes from the eval data:

1. **q1_openings_closings** — Variant B dropped `review_analyst` on
   **both trials**. The production floor mandates it because
   closure-detection needs review-velocity and rating-trajectory analysis
   ("9 reviews in 20 days then flatlined" — that's structured-API data
   that surfaces "this place was dying" patterns before closure). Variant
   B's `review_analyst` description doesn't currently encode this
   closure-detection role.

2. **q3_price_comparison** — Variant B substituted `guest_intelligence`
   for `review_analyst`. Both surface review-related insight, but
   `review_analyst`'s structured-API access (Apify-backed Google
   Reviews + TripAdvisor) catches price-perception patterns
   `guest_intelligence`'s open-web search misses. The boundary between
   the two specialists isn't sharp enough in the descriptions.

3. **q8_wage_benchmarks t2** — Variant B dropped `dynamic_researcher_1`
   and called only `operations`. The production floor mandates the pair
   because there's no dedicated labor specialist; `dynamic_researcher_1`
   fills the gap on job boards and salary aggregators. The
   pair-dispatch rationale isn't currently encoded in either
   specialist's description.

### What B got right (worth preserving)

- B's specialist_set_correctness dimension was **tied or won** in 8 of
  12 pairwise verdicts. Routing decisions weren't catastrophically
  wrong — they were defensible given the rules B was operating under.
  Quality losses came from cumulative under-coverage: coverage,
  specificity, and source diversity all consistently went to A.
- B passed the **routing-accuracy gate** (median Jaccard 0.75 ≥ 0.6).
- B passed the **generalization gate** (B won 1 of 2 off-matrix
  long-tail queries — `qX_quietly_dying` t2). The same one under both
  judges.

So: descriptions are doing real routing work. They just aren't
sufficient on their own for the on-matrix floored cases.

## Why this is open now (and not closed by the eval)

The eval ran B with **all five floors removed at once**. The 11-1 result
tells us "fully replacing floors with descriptions doesn't work" but not
"no description rewrite can replace any floor." It's possible that
**targeted description fixes for the three concrete misses above** would
close the on-matrix gap, in which case some or all floors could be
dropped.

We deferred this work because:

1. The architectural migration (AgentTool) was the foundational change.
   Doing the floor experiment on top of the new substrate is cleaner
   than doing both at once.
2. Production was healthy after the migration. No urgency.
3. Per "complicate later" — wait until production traffic shows whether
   floors are causing real problems before changing them.

It's been ~0 days of production traffic at the time of this handoff,
but waiting isn't the right move: floors are tech debt regardless of
prod health, and the AgentTool migration just made catalog descriptions
the proper routing primitive. The natural next step is to test whether
descriptions can carry the routing without the prescriptive rules.

## The three options

### Option A — leave floors as-is

Cost: zero. Risk: zero. Floors are validated by eval and verified by
post-deploy smoke tests in `docs/agent-routing-rearchitecture-deploy-log-2026-04-29.md`.

When this is right: production traffic shows no floor-related problems
over a ~2-week window, and we don't see specific routing misses on real
queries.

### Option B — targeted description work + re-eval

Cost: ~1 day of work + ~30 min eval (~$25-50).

The hypothesis: the three concrete failures from the prior eval can be
fixed by encoding the specific roles that the floors are doing. If yes,
we can drop the corresponding floors. If not, we keep them — and we've
learned something.

**Concrete description fixes to try:**

- **`review_analyst`** — currently describes "quantitative review
  analysis from structured API sources." Fatten to surface
  closure-detection role: "...includes review-velocity tracking and
  rating-trajectory analysis (catches 'this place was dying' patterns
  before the closure date — review counts that flatline, sudden rating
  drops, defensive owner-responses). Use this any time the question
  touches closure detection or struggling-venue analysis."

- **`marketing_digital`** — currently describes Instagram/TikTok/Meta
  Ad Library. Add price-positioning role: "...also surfaces price
  positioning via promo activity, discount frequency, and value-prop
  messaging in social posts and ads. For pricing-comparison questions,
  this is the 'how is the price perceived publicly' signal that
  complements `menu_pricing`'s line-item data."

- **`dynamic_researcher_1`** — currently describes itself as flexible
  fallback. Add explicit pair-dispatch rationale with `operations`:
  "...for wage/labor questions specifically, pair with `operations`:
  `operations` covers the salary-as-cost-ratio framing; this specialist
  pulls the actual job-board listings (Pracuj.pl, NoFluffJobs, GoWork)
  with concrete current rates. Neither alone produces a complete wage
  picture."

- **`menu_pricing`** — current description is rich. Verify it surfaces
  the "currently-operating signal" role for openings/closings (delivery
  platforms are the live signal of who's actually serving customers).
  Probably already there; check.

**Then run the same 6-query eval as before but with these floors
removed:**

- Openings/closings floor
- Pricing-comparison floor
- Wage/labor floor

Keep the sentiment/review and market-saturation floors as-is — those
weren't directly tested by the prior eval misses. Could be a follow-up
experiment.

**Use the same harness:** `agent/evals/run_matrix.py` parallelized to
K=4 concurrency, `agent/evals/queries_routing_subset.json` (already has
the 6 queries with `expected_specialists` for Jaccard scoring),
`agent/evals/pairwise.py` with Claude Opus subagent judging pattern (no
ANTHROPIC_API_KEY needed — use the parallel-Agent-tool subagent pattern
from `agent/evals/pairwise_verdicts/agent_routing_opus/` as the
template).

**Pass criterion:** Variant B (with targeted description fixes, floors
removed) wins or ties Variant A on at least 4 of 6 queries. Anything
worse than that means descriptions alone aren't sufficient and floors
stay.

### Option C — softer floors

Cost: ~30 min editing the prompt. Untested.

Convert "MUST call X+Y+Z" to "Strongly consider calling X+Y+Z; the
orchestrator may substitute when the descriptions of available
specialists make a different choice equally well-grounded." Introduces
ambiguity that the model could misuse — and we have evidence (the 11-1
eval) that the model under-covers when given that latitude.

Don't do this unless A and B both prove insufficient. It's a worse
version of B without the empirical validation.

## Recommendation

**Option B — targeted description work + re-eval.** Floors are tech debt
regardless of whether production is currently smooth: they encode
specialist-capability information in the orchestrator prompt instead of
in the specialist descriptions where it belongs (and where the AgentTool
migration just made descriptions properly load-bearing as the routing
primitive). The right time to test whether descriptions can carry the
routing is now, not "later when production surfaces a problem."

The decision is bounded and falsifiable:

- **Cost:** ~1 day of work + ~$25-50 in eval runs.
- **Falsification:** the eval gate (V_targeted ties or wins on ≥4 of 6
  queries against a fresh AgentTool-floored baseline). If it fails, we
  don't ship the change and we've learned that floors are doing
  irreducible work — at which point we move their rationale into
  specialist-description comments and close the question definitively.
- **Either outcome is forward progress.** Best case: drop three floors,
  ~25 fewer lines of prompt, system aligns with description-driven
  routing canon. Worst case: we have a clean documented conclusion that
  this layer of institutional knowledge can't reduce to descriptions and
  needs to live in the prompt.

The case for delay is weak. "Wait for production traffic" sounds like
conservative caution but we already have eval data, which is better
than waiting for incidents. Production health is not an argument for
keeping the fragile abstraction — it's an argument that we have a
stable baseline against which to run the experiment.

### Option B — execution plan

The work splits cleanly into 5 steps:

1. **Description rewrites** (~2 hours). Edit
   `agent/superextra_agent/specialist_catalog.py` for the three named
   specialists. No code changes elsewhere.

2. **Floor-stripped prompt variant** (~30 min). Copy
   `agent/superextra_agent/instructions/research_orchestrator.md` to
   `agent/evals/instructions_variants/V_targeted/research_orchestrator.md`
   and remove only the three relevant floors (openings/closings,
   pricing, wage). Keep the others.

3. **Capture a fresh floored baseline first** (~30 min wall-clock,
   ~$25-50 — **this is required**). The existing
   `agent/evals/results/V_baseline/` results were captured against the
   _pre-AgentTool_ pipeline. They're not a fair baseline for a
   floor-removal decision now: a V*targeted-vs-old-V_baseline
   comparison would mix floor effects with architecture differences.
   Capture a current-architecture floored baseline by running the
   harness against `main` \_as-is*:

   ```
   .venv/bin/python evals/run_matrix.py --variant V_floored_2026 \
       --queries evals/queries_routing_subset.json \
       --venues evals/venues_monsun_only.json \
       --out evals/results/V_floored_2026/ \
       --concurrency 4 --trials 2
   ```

   This is the apples-to-apples comparison set: same architecture, same
   prompt commit, with floors. Don't skip this step.

4. **Run V_targeted** (~30 min wall-clock). Same harness, with the
   floor-stripped prompt variant via the
   `SUPEREXTRA_INSTRUCTIONS_DIR` overlay (run_matrix.py builds the
   overlay automatically when a variant directory exists at
   `evals/instructions_variants/<variant>/`):

   ```
   .venv/bin/python evals/run_matrix.py --variant V_targeted \
       --queries evals/queries_routing_subset.json \
       --venues evals/venues_monsun_only.json \
       --out evals/results/V_targeted/ \
       --concurrency 4 --trials 2
   ```

5. **Pairwise judging V_floored_2026 vs V_targeted** (~5-15 min). Two
   paths, pick one:

   **Gemini via the existing repo command (default, no key needed):**

   ```
   for q in q1_openings_closings q3_price_comparison q8_wage_benchmarks \
            q4_sentiment_themes qX_quietly_dying qY_what_to_watch; do
     for t in 1 2; do
       .venv/bin/python evals/pairwise.py \
           --a evals/results/V_floored_2026/monsun__${q}_t${t}.json \
           --b evals/results/V_targeted/monsun__${q}_t${t}.json \
           --out evals/pairwise_verdicts/floors_2026/monsun_${q}_t${t}.json \
           --model gemini-2.5-pro
     done
   done
   ```

   Same-family bias caveat: Gemini judging Gemini outputs. Acceptable
   for a directional decision; if results are close, fall back to the
   Opus path below.

   **Claude Opus via the SDK (if `ANTHROPIC_API_KEY` is set):** swap
   `--model gemini-2.5-pro` for `--model claude-opus-4-7`. Existing
   `pairwise.py` supports both. If `ANTHROPIC_API_KEY` isn't available
   in the eval environment, the only Opus path is the manual
   Codex/Claude-Code subagent pattern used in the prior eval (each
   verdict run as an independent Agent-tool invocation reading a
   pre-rendered prompt file). That's not a runnable repo command —
   it's an ad-hoc operator process. Reproduce the prior round's
   approach if you go this route, or just run Gemini and accept the
   bias.

6. **Decide.** Apply success criterion: V_targeted wins or ties on ≥4
   of 6 queries. If yes, drop the three relevant floors from production
   and update the catalog descriptions. If no, keep floors and document
   the conclusion in the catalog (each floor's rationale becomes a
   comment on the relevant specialist).

Total: ~1 day of focused work, including write-up.

## Risks

| Risk                                                                                | Likelihood | Mitigation                                                                                                                                                                                                               |
| ----------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Description rewrites accidentally break production                                  | Low        | Catalog descriptions are now consumed at runtime via `AgentTool.description`. Test descriptions feed correctly into orchestrator prompt before running eval. Pytest covers catalog shape (`test_specialist_catalog.py`). |
| Eval flakiness gives a false positive (B looks fine but isn't)                      | Medium     | Run trials=3 instead of 2 for higher signal. Use Opus + Gemini judges and require agreement.                                                                                                                             |
| Eval reveals new failure mode we didn't anticipate                                  | Medium     | The eval _is_ the way to discover this; we accept the cost of finding out.                                                                                                                                               |
| Targeted description work doesn't address the actual mechanism by which floors work | Possible   | Hard to know without trying. If B fails the new gate, we've learned that descriptions alone can't substitute and we don't waste more time on this approach.                                                              |

## What success looks like

**Best case:** descriptions carry the routing work, three floors drop,
prompt simplifies by ~25 lines, system aligns with canonical
description-driven routing pattern. Quality holds.

**Worst case:** B fails the eval, we learn floors are doing irreducible
work. We document the floor decisions in the catalog (each floor's
rationale becomes a comment on the relevant specialist), and we close
the question definitively. Worth ~1 day of work for that level of
clarity.

## What NOT to do

- **Don't drop floors without re-running the eval.** The 11-1 prior
  result is the load-bearing evidence; any floor change should be
  re-validated against it.
- **Don't introduce new specialists** as part of this work. Specialist
  catalog changes are a separate scope (e.g. dedicated labor
  specialist, iterative-dispatch-aware specialist). Keep this scope
  description-only.
- **Don't change the orchestrator's behavioral prompt** beyond removing
  the three relevant floors. Step 6 ("pick by unique signal") and
  step 8 ("pre-dispatch coverage check") and step 10 ("iterative
  dispatch when warranted") all stay.
- **Don't relitigate the AgentTool migration.** That decision is shipped
  and stable. The floor question is downstream of it.

## Source pointers

For depth, in roughly the order they were produced:

- `docs/agent-routing-redesign-context-2026-04-29.md` — the full
  investigation context: motivation, external research, alternatives
  evaluated.
- `docs/agent-tool-spike-findings-2026-04-29.md` — pre-eval spike
  comparing orchestration mechanics.
- `docs/agent-routing-redesign-eval-plan-2026-04-29.md` — eval test
  plan, success criteria, harness details.
- `docs/agent-routing-redesign-eval-results-2026-04-29.md` — the 11-1
  result with full dimensional breakdown + Opus rejudge confirmation.
- `docs/agent-routing-rearchitecture-plan-2026-04-29.md` — Path A1
  migration plan that shipped.
- `docs/agent-routing-rearchitecture-deploy-log-2026-04-29.md` — deploy
  execution log + production smoke test results.

Code:

- `agent/superextra_agent/specialist_catalog.py` — specialist
  descriptions (the routing primitive under AgentTool).
- `agent/superextra_agent/instructions/research_orchestrator.md` —
  orchestrator prompt including the five floors.
- `agent/superextra_agent/agent.py` — pipeline wiring.
- `agent/evals/run_matrix.py` — parallelized eval runner.
- `agent/evals/queries_routing_subset.json` — the 6-query eval set.
- `agent/evals/results/V_baseline/` — Variant A results from the prior
  eval. **Note:** these were captured against the _pre-AgentTool_
  pipeline. They are NOT a fair baseline for a floor-removal decision
  now — capture a fresh `V_floored_2026` baseline against current
  `main` (Step 3 in the Option B plan) so the comparison is
  apples-to-apples.

## Open questions for whoever picks this up

1. Should we expand beyond the 6-query subset for this re-eval? The
   prior eval used 4 on-matrix + 2 off-matrix. For a floor-removal
   experiment, the on-matrix queries are the load-bearing test. 6 is
   sufficient for directional signal; 12 (3 trials each) gives
   tighter confidence.

2. What happens to the catalog comments that describe each floor's
   rationale today (in `research_orchestrator.md:82-96`)? If we drop a
   floor, the rationale should move into the relevant specialist's
   catalog description, otherwise the institutional knowledge is lost.

3. Should we set up periodic eval re-runs as quality monitoring? The
   harness already exists; running the 6-query subset monthly costs
   ~$25-50 and catches description-quality drift before users see it.
   Out of scope for this immediate work but worth considering.
