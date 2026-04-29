# Agent routing redesign — eval results

**Date:** 2026-04-29 (Gemini judging) + 2026-04-29 (Opus rejudge)
**Owner:** Adam (PM); execution: Claude
**Status:** Complete — confirmed by independent rejudge
**Companion docs:** `docs/agent-routing-redesign-eval-plan-2026-04-29.md`,
`docs/agent-routing-redesign-context-2026-04-29.md`,
`docs/agent-tool-spike-findings-2026-04-29.md`

## TL;DR

Variant A (current `SequentialAgent` + `ParallelAgent` +
`set_specialist_briefs` production pipeline at commit `dd3abd6`) wins
**11 of 12** pairwise verdicts against Variant B (AgentTool-wrapped
specialists with rich descriptions, no query-type-coverage floors)
under **Claude Opus 4.7** judging. Zero ties. The original Gemini 2.5
Pro judging round had A win 10/12; the Opus rejudge — different model
family, no same-family bias — made the verdict **more** decisive, not
less. **The plan's quality gate fails twice, by two independent judges
from two different model families.** Per the pre-decided path logic,
this means **no path forward on the redesign as designed** — neither
Path A (full migration) nor Path B (description-only retrofit) is
justified by this data, because both rely on the load-bearing claim
that a count-based principle plus rich descriptions can substitute for
the production floors. The eval result says it can't.

Two important secondary findings: B passes the routing-accuracy gate
(median per-query Jaccard 0.75 ≥ 0.6) and the generalization gate (B
wins one of two off-matrix queries — the **same** one under both
judges, `qX_quietly_dying` t2). So the redesign isn't a pure routing
failure — it's a quality failure on the floored on-matrix queries the
redesign was supposed to leave equally well-served.

## Opus rejudge — independent confirmation

After the Gemini judging round, the same 12 pairs were rejudged by 12
parallel Claude Opus 4.7 subagents (one per pair, each running as an
independent Agent tool invocation, no shared context, no chained
reasoning between them). Each agent received exactly the same prompt
the Gemini judge saw — same rubric, same dimensions, same justification
format — and was instructed to apply the rubric literally and not be
charitable to either side. Verdicts saved to
`agent/evals/pairwise_verdicts/agent_routing_opus/`.

**Opus tally: A 11, B 1, TIE 0.**

| Query                | Trial 1 (Gemini → Opus) | Trial 2 (Gemini → Opus) |
| -------------------- | ----------------------- | ----------------------- |
| q1_openings_closings | A → A                   | A → A                   |
| q3_price_comparison  | A → A                   | A → A                   |
| q4_sentiment_themes  | A → A                   | A → A                   |
| q8_wage_benchmarks   | B → A                   | A → A                   |
| qX_quietly_dying     | A → A                   | B → B                   |
| qY_what_to_watch     | A → A                   | A → A                   |

One verdict flipped between judges (`q8_wage_benchmarks` t1: B→A under
Opus). One verdict held identically as B in both judges
(`qX_quietly_dying` t2 — B's only sweep, with B winning all 5 dimensions
under Opus). Ten verdicts agree A in both judges. **Net effect: Opus is
_more_ favorable to A than Gemini was.** The same-family-bias caveat is
no longer load-bearing — the result holds across model families.

Notable Opus dimensional patterns: B won at least one dimension in 7
of 12 cases. B's specialist_set_correctness dimension was tied or won
on 8 of 12 (so the routing decisions weren't catastrophically wrong),
but A's holistic verdict came from cumulative wins on coverage,
specificity, and source diversity — exactly the qualities the
production floors are designed to enforce. Opus consistently flagged
B's reports as "respectable but systematically softer" — narratively
sophisticated but missing the concrete quantitative anchors A's wider
specialist dispatch produces.

One Opus judgment is worth quoting directly because it isolates the
mechanism: on `q3_price_comparison` t1, Opus wrote that V_baseline
"dispatched the correct specialist set (incl. marketing_digital),
produced verbatim-quoted review evidence, sourced platform-markup math,
and avoided B's internal contradiction where Restauracja Moon tops the
avg-spend chart despite cheaper mains than Monsun in the same report."
That's the failure mode: B's narrower dispatch (substituting
`guest_intelligence` for `review_analyst` and skipping
`marketing_digital`) leaves it without the cross-checks that catch
internal contradictions before they ship to the operator.

## Eval setup (with caveats up front)

The eval ran 24 production-shape pipeline runs on the `monsun` venue
(Świętojańska 49, Gdynia; resolved Place ID `ChIJ48HwEQCn_UYRmVqYQULc9pM`):
6 queries × 2 variants × 2 trials. All 24 runs completed successfully —
`error: null` and `synth_outcome: ok` across the board, as visible in any
result JSON's top-level fields. Wall-clock per run ranged from 174s to 316s
across both variants.

Two queries are deliberately on-matrix and reflect the production floors:
`q1_openings_closings` (4-specialist floor), `q3_price_comparison`
(3-specialist floor), `q4_sentiment_themes` (2-specialist floor), and
`q8_wage_benchmarks` (2-specialist floor). Two are hand-crafted off-matrix
phrasings: `qX_quietly_dying` ("which restaurants are quietly losing
momentum?") and `qY_what_to_watch` ("what should I be watching in the local
food and drink scene over the next 3 months?"). Expected specialist sets
live in `agent/evals/queries_routing_subset.json:9-72`.

Three caveats shape interpretation:

1. **~~Judge is Gemini 2.5 Pro, not Claude Opus.~~** ✅ **Resolved by Opus
   rejudge** — see top of doc. Original Gemini round (judge_model:
   gemini-2.5-pro) had A win 10/12; Opus rejudge (judge_model:
   claude-opus-4-7, run as 12 parallel Agent tool subagents because the
   environment had no `ANTHROPIC_API_KEY` for the SDK path) had A win
   11/12. Same-family bias is no longer a load-bearing concern — the
   result holds across two independent judges from different model
   families.
2. **N=2 trials per cell.** Directional by design. We didn't get a 4-4
   split — 10-2 with no ties — so directional signal is unambiguous.
3. **Single venue (monsun).** Different venues might surface different
   routing patterns. Out of scope per the plan.

One positive technical finding from the run itself: per-specialist event
capture under AgentTool works. Variant B's `authors_seen` field correctly
records per-specialist event counts (e.g. `monsun__q1_openings_closings_t1.json`
shows `{'menu_pricing': 3, 'marketing_digital': 3, 'market_landscape': 1, ...}`),
and `drawer_sources`, `tool_call_counts`, and `token_totals` are all
populated. The `EventCapturePlugin` integration with the nested-invocation
guard pattern is **eval-side technically feasible**; this is one of the
preconditions for Path A and we now have evidence it works.

## Verdict tally + dimensional analysis

The headline tally:

| Query                | Pill                | Trial 1 | Trial 2 |
| -------------------- | ------------------- | ------- | ------- |
| q1_openings_closings | competitor_tracking | A       | A       |
| q3_price_comparison  | price_positioning   | A       | A       |
| q4_sentiment_themes  | sentiment_trends    | A       | A       |
| q8_wage_benchmarks   | wage_benchmarking   | **B**   | A       |
| qX_quietly_dying     | off-matrix          | A       | **B**   |
| qY_what_to_watch     | off-matrix          | A       | A       |

**A: 10 wins. B: 2 wins. TIE: 0.** Verified against the 12 verdict JSONs in
`agent/evals/pairwise_verdicts/agent_routing/`.

A category collapse — B losing both trials of a single query, indicating a
routing failure for that pattern — happens on **four** of the six queries:
`q1_openings_closings`, `q3_price_comparison`, `q4_sentiment_themes`, and
`qY_what_to_watch`. The quality gate's "no category collapse" rider was a
guard for a marginal case; here it's redundant since B already loses on
overall counts.

Dimensional tallies across all 12 verdicts (each verdict scores five
dimensions):

| Dimension                  | A   | B   | TIE |
| -------------------------- | --- | --- | --- |
| coverage                   | 6   | 3   | 3   |
| specificity                | 7   | 3   | 2   |
| source_diversity           | 5   | 3   | 4   |
| actionability              | 8   | 2   | 2   |
| specialist_set_correctness | 8   | 1   | 3   |

The two dimensions where A's lead is largest are **actionability** (8-2)
and **specialist_set_correctness** (8-1). Specialist_set_correctness
matters because it's the dimension most directly tied to the redesign's
core hypothesis ("rich descriptions route as well as floors"). The judge
saw A's dispatched sets as correct for the query 8 times, B's only once.
**Source_diversity** is the closest dimension (5-3 with 4 ties) — B does
roughly hold its own on bringing varied sources, which is consistent with
the spike's observation that orchestrator behaviour over multiple
specialist outputs is similar across variants.

The two B wins are worth examining for what B did right:

- **q8_wage_benchmarks t1**: B won decisively across 4 of 5 dimensions
  (specialist*set_correctness was a tie, since both variants dispatched
  exactly `operations` + `dynamic_researcher_1`). The judge's rationale
  (verdict JSON `raw_response` field) explicitly cited B for going beyond
  job-board data into the "shadow economy" of cash-in-hand wages, citing
  PIE economic reports, the \_Barometr Zawodów*, and Reddit threads — a
  pure synthesis-quality win on the same dispatched set.
- **qX_quietly_dying t2**: B won on coverage, specificity, actionability,
  and specialist_set_correctness (source_diversity tied). This is the
  off-matrix win that lets B clear the generalization gate.

Both B wins are on synthesis quality, not routing. That's the direction
where Path B (description-only retrofit) would in principle be most
helpful — but the on-matrix sweep tells the opposite story.

## Latency analysis

Latency is comparable between variants. Run-to-run variance is large within
each variant, larger than the variant-to-variant difference.

| Statistic      | A (V_baseline) | B (V_agenttool) |
| -------------- | -------------- | --------------- |
| Median elapsed | 254s           | 246s            |
| p95 elapsed    | 313s           | 305s            |
| Min / max      | 174s / 316s    | 198s / 316s     |

Per-query (averaged across trials):

| Query                | A avg | B avg | Δ        |
| -------------------- | ----- | ----- | -------- |
| q1_openings_closings | 272s  | 268s  | −4s      |
| q3_price_comparison  | 298s  | 213s  | **−85s** |
| q4_sentiment_themes  | 197s  | 260s  | +64s     |
| q8_wage_benchmarks   | 197s  | 226s  | +29s     |
| qX_quietly_dying     | 305s  | 259s  | −46s     |
| qY_what_to_watch     | 242s  | 252s  | +10s     |

B is faster than A on three queries, slower on three. The largest swing
(q3_price_comparison, B 85s faster) and the next-largest (q4, B 64s
slower) are within the trial-to-trial variance bands of the spike findings
(`agent-tool-spike-findings-2026-04-29.md:294-298`). Latency is a wash —
not a finding either way. B does not pay a parallelism penalty (Gemini 3.1
Pro consistently emits parallel AgentTool calls, consistent with the spike
result), and B does not deliver a meaningful latency win either.

## Routing analysis

For each query, the dispatched set under both variants per trial, with
Jaccard against the expected set from the fixture:

| Query                | Expected                                                              | A t1                                          | A t2                                                                          | B t1                                                                                               | B t2                                                                           |
| -------------------- | --------------------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| q1_openings_closings | `{market_landscape, menu_pricing, marketing_digital, review_analyst}` | adds `location_traffic` (J=0.80)              | adds `location_traffic` (J=0.80)                                              | drops `review_analyst` (J=0.75)                                                                    | drops `review_analyst` (J=0.75)                                                |
| q3_price_comparison  | `{menu_pricing, review_analyst, marketing_digital}`                   | exact match (J=1.00)                          | adds `guest_intelligence` (J=0.75)                                            | substitutes `guest_intelligence`+`revenue_sales` for `review_analyst`+`marketing_digital` (J=0.20) | drops `review_analyst`+`marketing_digital`, adds `guest_intelligence` (J=0.25) |
| q4_sentiment_themes  | `{review_analyst, guest_intelligence}`                                | exact (J=1.00)                                | exact (J=1.00)                                                                | exact (J=1.00)                                                                                     | exact (J=1.00)                                                                 |
| q8_wage_benchmarks   | `{operations, dynamic_researcher_1}`                                  | exact (J=1.00)                                | adds `market_landscape` (J=0.67)                                              | exact (J=1.00)                                                                                     | drops `dynamic_researcher_1` (J=0.50)                                          |
| qX_quietly_dying     | `{market_landscape, menu_pricing, review_analyst}`                    | adds `marketing_digital` (J=0.75)             | adds `marketing_digital`+`guest_intelligence` (J=0.60)                        | drops `menu_pricing`, adds `marketing_digital` (J=0.50)                                            | adds `marketing_digital` (J=0.75)                                              |
| qY_what_to_watch     | `{market_landscape, marketing_digital, dynamic_researcher_1}`         | drops `dynamic_researcher_1`, adds 3 (J=0.33) | drops `dynamic_researcher_1`, adds `location_traffic`+`menu_pricing` (J=0.60) | exact (J=1.00)                                                                                     | exact (J=1.00)                                                                 |

Per-query mean Jaccard (avg of two trials): A {0.80, 0.88, 1.00, 0.83,
0.68, 0.47}, median **0.82**. B {0.75, 0.23, 1.00, 0.75, 0.62, 1.00},
median **0.75**. B passes the ≥0.6 gate. The interesting structure: B is
**better than A** on the off-matrix `qY_what_to_watch` (B picks the
"correct" 3-specialist set on both trials; A scatters into 4–5 specialists
including weakly-relevant ones), and B is **dramatically worse** on the
floored `q3_price_comparison` (J=0.23 vs A's 0.88). This is the redesign's
hypothesis playing out exactly as advertised in some places and failing
exactly as feared in others.

Three substitutions worth flagging:

- **q3_price_comparison**: A matched the expected set exactly on t1 and
  with one addition on t2. B substituted `guest_intelligence` for
  `review_analyst` and dropped `marketing_digital`. Both `review_analyst`
  and `guest_intelligence` produce review-related insight; one is the
  structured-API specialist, the other is search-based. This is a
  defensible substitution at the _intent_ level, but the judge marked
  specialist_set_correctness for A on both trials — a hint that the
  judge could see the substitution didn't deliver equivalent insight.
  Verdict rationale would confirm this; the dimensional vote already
  signals it.
- **q1_openings_closings**: A correctly included `review_analyst` (the
  production floor expects it for closure signals — rating decline, recent
  complaints). B dropped `review_analyst` on **both** trials. The rich
  description for `review_analyst` evidently doesn't surface its role in
  detecting closure risk; that connection is exactly what the production
  floor encodes. This is a clean example of a description that fails to
  carry a non-obvious capability.
- **q8_wage_benchmarks t2**: B dropped `dynamic_researcher_1`, calling
  only `operations`. The production floor expects both because
  `dynamic_researcher_1` does the broad-web wage-board search that
  `operations` (more structured) doesn't cover. Combined with t1 (where B
  dispatched both correctly), this looks like model-choice variance under
  the count-based principle — the description doesn't make the case for
  _both_ specialists strongly enough to be reliable.

## Iterative dispatch observation

Across the 12 V_agenttool runs, **one run shows iterative-dispatch
evidence**: `monsun__q8_wage_benchmarks_t2.json` records
`tool_call_counts: {'operations': 2, ...}`. Every other B run called each
specialist exactly once. The orchestrator decided one round was sufficient
on 11 of 12 runs.

The captured aggregates don't preserve event ordering, so we can't
distinguish "two `operations` calls in the same turn" (parallel duplicate)
from "one call, read response, then another call" (true iterative
dispatch). Honest observation: **evidence iterative dispatch plausibly
fired once, not proof.** The plan anticipated this matrix may not exercise
iterative dispatch even if wired correctly
(`agent-routing-redesign-eval-plan-2026-04-29.md:387-391`); the data is
consistent with that prediction. Future evals targeting exploratory or
contradiction-driven queries are the right venue to test the capability.

## Applying the success criteria

Each gate is from `agent-routing-redesign-eval-plan-2026-04-29.md:336-409`,
applied literally.

**Quality gate** (≥6 decisive verdicts AND wins(B) > wins(A) AND no category
collapse). Decisive verdicts: 12 of 12 (zero ties). wins(A)=10, wins(B)=2.
wins(B) > wins(A) is **false**. **Quality gate FAILS.** Category collapse
on 4 of 6 queries; not the deciding factor.

**Generalization gate** (B wins ≥1 of 2 off-matrix queries across either
trial). B wins on `qX_quietly_dying` t2. **Generalization gate PASSES.**

**Routing accuracy gate** (median Jaccard across 6 queries ≥ 0.6). Per-query
mean Jaccard medians to **0.75**. **Routing accuracy gate PASSES.**

**Latency observation** (not a gate): A median 254s vs B median 246s —
comparable. Variance dominates. No actionable signal either direction.

**Iterative dispatch observation** (not a gate): one run plausibly
exercised it; can't be confirmed from the captured aggregates. The matrix
was acknowledged not to be the right shape for forcing iterative dispatch.
Inconclusive, in the sense the plan anticipated.

## Path recommendation

Per the plan's pre-decided logic
(`agent-routing-redesign-eval-plan-2026-04-29.md:394-409`):

- **Path A green-lit** iff B passes all three gates → not met (quality
  fails). Path A is **not justified**.
- **Path B preferred** iff B passes quality but fails generalization or
  routing → not met (quality fails again, while the others actually pass).
  Path B is also **not justified**.
- **No path forward** iff B fails quality. **This is the applicable
  outcome.**

The plan's instruction in this branch: "Investigate why before changing
direction." That's the next step — not "do Path B anyway because it's
cheaper" or "do Path A anyway because it's architecturally cleaner." The
hypothesis under test was "rich descriptions plus a count-based floor can
substitute for the production query-type-coverage floors without quality
regression." The data says no, with the caveat that a different judge
might shave one or two verdicts off the margin.

The most plausible mechanism, supported by the routing analysis above, is
that the production floors carry **non-obvious capability information**
that rich descriptions are not currently encoding: `review_analyst` for
closure detection (q1), the `operations`+`dynamic_researcher_1` pair for
wage coverage (q8), and the need for `review_analyst` over
`guest_intelligence` when the query is fundamentally structured-review-API-
driven (q3). Each is a description currently too generic to carry the load
the floor encoded. The redesign's hypothesis was that fixing descriptions
to lead with scope, then live data sources, then boundaries (per
Anthropic's research-agent guidance) would close that gap. On these six
queries, it didn't.

~~What would change the assessment: re-running the 12 verdicts against
Claude Opus to confirm the 10-2 tally isn't substantially judge-biased.~~

✅ **Done.** Opus 4.7 rejudge (12 parallel Agent tool subagents,
different model family, independent reasoning, no shared context)
returned **A 11 / B 1 / TIE 0** — same direction, _larger_ margin than
Gemini's 10-2. The quality-gate-fails finding is no longer provisional;
it holds across two independent judges from two model families. The
"different judge could plausibly reverse 1-2 verdicts" hedge is now
falsified by data.

The next move, then, is the targeted intervention this analysis points
at: **description-quality work focused on the specific failed-routing
cases** — q1's `review_analyst` role in closures, q3's
`review_analyst` vs `guest_intelligence` boundary, q8's pair-dispatch
motivation. Each is a place where the rich description didn't surface a
capability the production floor was encoding by name. That's a tighter
intervention than full Path B (wholesale floor removal), focused on
actual failure modes rather than the entire matrix. Re-running the same
6-query subset after each description fix would give us a fast feedback
loop on whether targeted description work closes the gap.

If targeted description work doesn't recover the on-matrix verdicts,
the fallback is to **leave the production floors as they are** and
treat them as encoding institutional knowledge that doesn't reduce to
description text — accepting that some routing decisions are
imperative rules rather than emergent reasoning, and that the cost of
maintaining ~5 floor entries is lower than the cost of a description-
based system that generalizes worse on the queries we actually serve.

## Caveats — what we'd want to verify

- ~~**Same-family judge bias.**~~ ✅ **Resolved.** Opus 4.7 rejudge of
  all 12 pairs returned A 11 / B 1 / TIE 0 — same direction, larger
  margin. Different model family. Same-family bias is no longer a
  caveat that can move the verdict; the conclusion stands across two
  independent judges.
- **N=2 trials per cell.** Re-running with 4 trials would give per-query
  confidence intervals. Given the no-tie 10-2 headline, the directional
  result is robust; the per-query trial-level breakdowns are noisier.
- **Single-venue eval.** Only `monsun`. Different venues might surface
  different routing patterns, especially for off-matrix queries where
  competitive density and review volume change which specialists have
  the most to say.
- **Per-specialist event capture under AgentTool worked.** Drawer counts,
  authors_seen counts, tool_call_counts, and token_totals are all
  populated under V_agenttool runs. `EventCapturePlugin` and the nested-
  invocation guard pattern integrated successfully. This is the eval-side
  technical feasibility evidence for Path A — should we ever return to
  it, the smallest piece of the plugin refactor is already prototyped
  and works in practice. Note this as a positive finding even though the
  quality gate failed.
- **The captured event stream is aggregated, not ordered.** Iterative-
  dispatch detection is therefore approximate. A future eval focused on
  exploratory/contradiction-driven queries would benefit from preserving
  event ordering in result JSONs — small diff to `evals/run_matrix.py`.

## Files

**Eval result JSONs (24 production runs):**

- `agent/evals/results/V_baseline/monsun__{q1,q3,q4,q8,qX,qY}_t{1,2}.json`
  (12 files)
- `agent/evals/results/V_agenttool/monsun__{q1,q3,q4,q8,qX,qY}_t{1,2}.json`
  (12 files)

**Pairwise verdicts (24 files: 12 Gemini + 12 Opus):**

- `agent/evals/pairwise_verdicts/agent_routing/monsun_{q1,q3,q4,q8,qX,qY}_t{1,2}.json`
  — original Gemini 2.5 Pro round, 10-2-0 verdict
- `agent/evals/pairwise_verdicts/agent_routing_opus/monsun_{q1,q3,q4,q8,qX,qY}_t{1,2}.json`
  — Opus 4.7 rejudge round (12 parallel Agent tool subagents,
  no shared context), 11-1-0 verdict

**Fixture:**

- `agent/evals/queries_routing_subset.json` — 6 queries with
  `expected_specialists` for Jaccard scoring.

**Companion docs:**

- `docs/agent-routing-redesign-eval-plan-2026-04-29.md` — pre-decided
  matrix, success criteria, build estimate. Success criteria literally
  applied above.
- `docs/agent-routing-redesign-context-2026-04-29.md` — motivation and
  background; description-vs-floor framing.
- `docs/agent-tool-spike-findings-2026-04-29.md` — earlier 4-run
  mechanical spike, including the plugin-lifecycle blocker analysis and
  parallelism confirmation.
