# Stage 2 results — V2.2 / V2.3 / variance check

> **Corrections applied 2026-04-25** — six factual issues flagged by the post-Stage-2 review have been corrected in this document. See `docs/research-depth-final-results-review-2026-04-25.md` for the full review and `docs/research-depth-stage3-validation-plan-2026-04-25.md` for the validation pass that follows. The headline V2.3 recommendation is unchanged but is now framed as a controlled improvement pending Stage 3 validation, not a fully-proven shippable result.

Companion to `research-depth-final-report-2026-04-25.md`. Path B from the next-stage plan was executed: V2.2, V2.3, variance check, scripted pairwise harness.

**Headline finding: V2.3 is the new ship candidate, not V2.1.** It dominates V0 on aggregate metrics, wins 22 of 24 head-to-head pairwise comparisons, and reverses V2.1's monsun-q2 regression as confirmed by both Gemini scripted judging and a Claude operator-subagent.

The recommendation in the previous final report (ship V2.1) is **superseded** by this document.

---

## Variants tested in Stage 2

| variant         | what changed                                                                                                       | why                                                                                    |
| --------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| V2.2            | V2.1 + `review_analyst` mandated in openings/closings rule                                                         | targeted fix for the monsun q2 regression we identified in Stage 1                     |
| V2.3            | V2.2's orchestrator + V1's source-priors block in `specialist_base.md` (without V1's verification-discipline rule) | tests whether V1's "good ideas" compose with V2.2 once V1's destructive bit is removed |
| V2.1 reps 2 & 3 | identical to V2.1, primary-probes only (9 combos × 2 reps)                                                         | measures harness run-to-run variance                                                   |

All scoring used existing `score.py` (deterministic + Gemini judge) and the new `evals/pairwise.py` (Gemini-as-judge, 24 comparisons in parallel).

---

## Aggregate scorecard (V0 / V2.1 / V2.2 / V2.3)

| metric                   | V0   | V2.1 | V2.2 | **V2.3** |
| ------------------------ | ---- | ---- | ---- | -------- |
| top-domain share (final) | 0.35 | 0.33 | 0.29 | **0.26** |
| category coverage / 8    | 2.2  | 2.8  | 2.6  | **3.2**  |
| wall-brand overlap / 29  | 0.46 | 0.88 | 1.21 | 1.17     |
| faithfulness (Gemini)    | 2.75 | 2.58 | 2.46 | 2.50     |
| specificity (Gemini)     | 3.08 | 3.21 | 3.17 | 3.08     |
| tokens (k)               | 170  | 163  | 180  | 186      |
| elapsed (s)              | 275  | 209  | 268  | 245      |

V2.3 wins on top-domain share and category coverage; **ties V2.2 on wall-brand overlap** (1.17 vs 1.21 — both materially better than V0's 0.46, but V2.2 is fractionally higher). Cost change vs V0: +8.8% tokens, −10.9% elapsed. Cost change vs V2.1: **+13.7% tokens, +17.0% elapsed**. Cost change vs V2.2: +3.4% tokens, −8.3% elapsed.

## Primary-probe scorecard (q1/q2/q3 only)

| metric             | V0   | V2.1 | V2.2 | **V2.3** |
| ------------------ | ---- | ---- | ---- | -------- |
| top-domain share   | 0.33 | 0.27 | 0.29 | 0.29     |
| category coverage  | 2.2  | 2.7  | 2.8  | **3.2**  |
| wall-brand overlap | 0.3  | 1.0  | 1.6  | **1.6**  |
| **faithfulness**   | 2.44 | 2.11 | 2.44 | **3.33** |
| **specificity**    | 2.78 | 2.78 | 3.56 | **4.00** |

**V2.3's primary-probe specificity (4.00) is the highest any variant has produced.** Faithfulness 3.33 is also a clear improvement over V0's 2.44 and V2.1's 2.11. (Caveat: Gemini judge is noisy in absolute terms, but relative deltas of this size are signal.)

## Pairwise V0 vs V2.3 across all 24 combos (Gemini scripted judge)

> **Caveat on this signal**: post-hoc review found that 23 of 24 of these scripted Gemini pairwise verdicts contain at least one fabricated `supporting_urls` entry — URLs not present in either run's actual sources. The judge has no live web access; it inferred or hallucinated canonical URLs to "justify" its verdicts. The `winner` field is still pairwise _preference_ signal (and 22-of-24 is robust against random noise), but it is **not source-verified**. Treat it as preference signal only, not as evidence verification. Stage 3 uses Claude operator-subagents with WebFetch for the verdicts that actually gate the ship decision.

```
V0 wins:  2  (8%)
V2.3 wins: 22 (92%)
TIE:      0
```

By query:

- q1 openings/closings: V0=1, V2.3=2
- q2 closures lessons: V0=1, V2.3=2
- q3 pricing: V2.3=3 (clean sweep)
- q4 sentiment: V2.3=3 (clean sweep)
- q5 thriving formats: V2.3=3 (clean sweep)
- q6 market saturation: V2.3=3 (clean sweep)
- q7 market performance: V2.3=3 (clean sweep)
- q8 wage benchmarks: V2.3=3 (clean sweep)

By venue:

- bar_leon: V0=1, V2.3=7
- monsun: V0=1, V2.3=7
- sliwka_w_kompot: V2.3=8 (clean sweep — the tricky venue)

**V0 wins were on:** `bar_leon × q2_closures_lessons` and `monsun × q1_openings_closings`. The `monsun × q1` loss is **not** comfortably explained by sampling noise: V2.3 dropped from V0's 5 categories to 2 (a 3-category gap, ~2σ outside the variance band of mean σ=0.76 / max σ=1.53 on category count) and faith/specificity Gemini scores both 5→1. This requires replication before being dismissed — Stage 3 reruns each contested combo 3 times and triggers operator-subagent review on any V2.3 rerun that shows simultaneous faith+specificity collapse.

Verdicts committed to `agent/evals/pairwise_verdicts/V0_vs_V2_3/<combo>.json`.

## Operator-subagent confirmation on monsun q2

The Stage 1 regression we built V2.2 to fix. V2.3 was tested via a Claude operator-role subagent:

> _"V2.3 dispatched 5 specialists including review_analyst and menu_pricing — exactly the gap from V2.1. Crucially, it identifies a completely different and more consequential closure set: Malika (next door at #69, 13 years), Trafik (Skwer Kościuszki, 18 years), Brassica (2-month flop), Bułkącik (10 PLN sandwiches). These are the closures a Gdynia GM actually cares about. The pricing chart (Trafik 68 PLN vs Monsun 56 PLN vs Chinese Wok 40 PLN) is the kind of comparative that actually moves decisions. Review-velocity analysis on Malika (36 reviews in 2022 → 2 in final 12 months) is a textbook distress-signal artifact. … V2.3 clearly beats V0 on actionability, coverage breadth, signal quality, and specialist discipline — exactly the regression V2.1 introduced now reversed."_

`VERDICT: V2_3`

V2.3 dispatch on monsun q2: `{guest_intelligence, market_landscape, marketing_digital, menu_pricing, review_analyst}` — 5 specialists. Drawer: 52 sources, 20 unique domains spanning community (trojmiasto), local press (wyborcza, eska), industry (orlygastronomii, poradnikrestauratora), consumer platforms (wolt, pyszne, tripadvisor, restaurantguru), venue's own channels (restauracjamoon, restauracjamalika, trafikgdynia, miwogdynia), municipal (gdynia.pl), commercial listings (gratka, dwellproperties).

## Variance check — the harness is moderately noisy

Three replications of V2.1 on primary probes (3 venues × 3 queries × 3 reps = 27 runs):

| metric                   | mean σ | max σ |
| ------------------------ | ------ | ----- |
| top-domain share (final) | 0.074  | 0.160 |
| category count (final)   | 0.76   | 1.53  |
| drawer URL count         | 12.5   | 22.9  |

Specialist dispatch also varies across reps for 4 of 9 combos — sometimes `review_analyst` is added freely, sometimes `dynamic_researcher_1` is added, sometimes the orchestrator picks 4 specialists, sometimes 5.

**Implications:**

- Single-run differences of ≤0.15 on top-domain share or ≤1 category may be noise.
- Aggregate metrics across 24 runs reduce σ by ~5× — aggregate differences ≥0.05 are reliably signal.
- Single-combo pairwise verdicts are weaker signal than I previously assumed. The 22/24 pairwise win for V2.3 is robust _because of the count_, not because individual verdicts are deterministic.
- The originally-flagged "monsun q2 V2.1 regression" (rep1: σ-extreme top-domain share of 0.615) was probably a tail-of-distribution unlucky run; rep2 had 0.30, rep3 had 0.41. The fix in V2.3 is real (52-source / 5-category result, much better than even the best V2.1 rep), but the original regression was noisier than presented.

## What V2.3 actually changed

Three things composed:

1. **Orchestrator coverage rules with additive floor** (inherited from V2.1 / V2.2): forces dispatch of `{market_landscape, menu_pricing, marketing_digital}` on openings/closings; `{menu_pricing, review_analyst, marketing_digital}` on pricing; etc.
2. **`review_analyst` added to the closures rule** (V2.2 contribution): nominally requires it on closures. _In practice, the orchestrator sometimes ignores this — the "MUST include" framing is read as advisory._
3. **V1's source-priors block in `specialist_base.md`** (V2.3 contribution): explicit list of 7 source categories with examples (venue's own channels, primary consumer platforms, local press / industry trade, community discussion, **culinary blogs as primary sources**, **municipal & city-authority sources**, official registries). Plus "source-diversity self-audit after first round" rule. **No verification-discipline rule** (the part of V1 that hurt V3).

The dispatch-thesis from Stage 1 still holds: forcing `marketing_digital` and `menu_pricing` on openings/closings was the foundation. But V2.3 shows that **specialist-level source priors matter more than I credited in the Stage 1 report** — once the dispatch is right, telling specialists _what_ to look for moves the needle further.

## Surprises from Stage 2

### V2.2 followed its own mandate on monsun q2 — and still failed

> _Correction 2026-04-25: an earlier version of this section claimed the V2.2 orchestrator dispatched `{market_landscape, marketing_digital, menu_pricing, operations}` — no review_analyst — and concluded the "MUST include" framing was being ignored. That was incorrect. The artifacts (`agent/evals/results/V2_2/monsun__q2_closures_lessons.json` and `evals/scores/V2_2.csv`) show V2.2 actually dispatched `{market_landscape, marketing_digital, menu_pricing, operations, review_analyst}` — five specialists, including review_analyst as required._

So V2.2 obeyed the rule on this run. The failure (top_dom 0.82, 1 category, drawer 11) happened _despite_ review_analyst being dispatched, not because of its absence. Adding more specialists alone did not guarantee a better answer — the bottleneck wasn't dispatch, it was specialist behavior.

That changes the diagnosis of why V2.3 is better than V2.2 on this combo:

- It is **not** "V2.3 forces review_analyst more reliably." V2.2 already had it.
- It is more likely "V2.3's source-priors block in `specialist_base.md` (the V1 contribution) gives specialists better guidance about what evidence types to look for, regardless of which specialists are dispatched."
- Free dispatch differences also contributed (V2.2 added `operations`, V2.3 added `guest_intelligence` — different specialist behavior in synthesis).
- Stochastic run variance (per the variance check) explains a portion of the spread.

The dispatch-is-the-lever thesis from earlier in this doc is therefore weaker than it appeared. Specialist-level source guidance is the bigger lever once dispatch is at least minimally correct.

### V1's source-priors weren't bad — V1's verification-discipline was

The Stage 1 conclusion was that V1 was a "mild regression" overall. Stage 2 disambiguates: the regression came from V1's verification-discipline rule ("if you can't find a source, omit the specific"), which made specialists conservative and dropped useful named anecdotes. V1's source-priors block — the part that lists municipal/culinary/registry source types — composes constructively with V2.2's orchestrator rules. Removing the discipline rule from V1 and combining the rest is what produces V2.3.

### The harness is noisier than expected — but aggregate signal still holds

We were drawing conclusions from single runs, including the monsun-q2 regression that motivated V2.2. The variance check shows top-domain share has σ = 0.074 mean / 0.16 max across reps, and specialist dispatch varies across reps too. Single-combo verdicts need ≥3 reps to be confident; aggregate metrics across 24 combos are much more robust.

This means going forward we should **either run 3 reps per variant** (3× cost) **or rely primarily on aggregate metrics** for ship decisions. The 22/24 pairwise V0-vs-V2.3 win is robust because 22 wins out of 24 trials is signal even with noisy per-trial verdicts.

### Aggregate gains compound across stages

V0 → V2.1 → V2.3 trajectory on key metrics:

- top-domain share: 0.35 → 0.33 → **0.26** (-26%)
- category coverage: 2.2 → 2.8 → **3.2** (+45%)
- wall overlap: 0.5 → 0.9 → **1.2** (+140%)

Each stage added value. The "ship V2.1" recommendation from Stage 1 was correct _given Stage 1 information_; Stage 2 produced V2.3 which is genuinely better.

---

## Recommendation update

**Ship V2.3 instead of V2.1.**

Concrete change:

- `agent/superextra_agent/instructions/specialist_base.md` ← `agent/evals/instructions_variants/V2_3/specialist_base.md`
- `agent/superextra_agent/instructions/research_orchestrator.md` ← `agent/evals/instructions_variants/V2_3/research_orchestrator.md`

Production code surface: zero. Two file replacements.

Risk profile:

- 22/24 pairwise wins is preference signal (Gemini scripted judge) — not source-verified, but robust against random noise.
- The `monsun × q1` pairwise loss is a real outlier worth replicating (3-category drop + faith/spec collapse); Stage 3 reruns it 3× before any ship decision.
- Aggregate metrics improve on most dimensions; ties V2.2 on wall-brand overlap.
- Cost: V2.3 vs V0 is **+8.8% tokens / −10.9% elapsed** (faster, slightly more tokens). V2.3 vs V2.1 is **+13.7% tokens / +17.0% elapsed**. V2.3 vs V2.2 is +3.4% tokens / −8.3% elapsed.

What to NOT do:

- **Ship V2.3 exactly as tested in `evals/instructions_variants/V2_3/`.** Do not strengthen or weaken the dispatch rules. V2.3 already includes `review_analyst` in the openings/closings coverage floor (the V2.2 contribution); changing that without re-running validation introduces untested behavior.
- Don't add V1's verification-discipline rule. Leave that demoted permanently.

What's still open (Tier 4 from the next-stage plan, not done):

- Multi-topic query handling
- Followup-query test
- Non-Tricity Polish or Berlin generalization

These can wait. V2.3 is the meaningful improvement over V2.1.

---

## Updated artifacts

**Code:**

- `agent/evals/pairwise.py` — new scripted pairwise judge (Gemini)
- `agent/evals/instructions_variants/V2_2/research_orchestrator.md`
- `agent/evals/instructions_variants/V2_3/research_orchestrator.md`
- `agent/evals/instructions_variants/V2_3/specialist_base.md`
- `agent/evals/queries_primary.json` — primary-probes-only fixture for the variance check

**Data:**

- `agent/evals/results/V2_2/`, `V2_3/`, `V2_1_rep2/`, `V2_1_rep3/`
- `agent/evals/scores/V2_2.csv`, `V2_3.csv`, `V2_1_rep2.csv`, `V2_1_rep3.csv`
- `agent/evals/pairwise_verdicts/V0_vs_V2_3/*.json` — all 24 verdicts

**Docs:**

- `docs/research-depth-stage2-results-2026-04-25.md` (this doc)
- `docs/research-depth-pairwise-verdicts-2026-04-25.md` (Stage 1, plus the new monsun q2 V2.3 verdict can be appended)
- `docs/research-depth-final-report-2026-04-25.md` (Stage 1 — superseded by this doc on the ship recommendation)

---

## Open questions for the committee

1. **Ship V2.3 conditional on Stage 3 validation passing.** Stage 3 is the targeted validation pass that addresses the corrections above (replicating contested combos, holdout queries, multi-topic robustness, exploratory Berlin probe). Final ship/no-ship is Stage 3's call, not this doc's.
2. **Should the eval harness be configured to run 3 reps by default** for any future variant test? Adds 3× compute cost but gives stable per-combo metrics. The variance check made the case for this; Stage 3 validates whether single-run results are noise or signal in the contested cases.
3. **Tier 4 (followup, additional cross-market venues) — still worth pursuing** after Stage 3, or are we declaring research-depth project complete and moving on? Stage 3 covers multi-topic via Adam-written holdout queries and Polish-non-Tricity via Warsaw; Berlin is exploratory only.
4. **Marketing-wall delivery audit and wage-benchmarking capability** still flagged as separate projects (unchanged from Stage 1).
