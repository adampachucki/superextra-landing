# Phase B — V0 baseline scorecard

24 runs: 8 queries × 3 venues (Monsun Gdynia / Bar Leon Gdansk / Śliwka w Kompot Sopot), all V0 (current production). Captured 2026-04-24 via `agent/evals/run_matrix.py`; scored via `agent/evals/score.py` with Gemini 2.5 Pro as judge.

## Headline

| metric                   | value         | interpretation                                                                |
| ------------------------ | ------------- | ----------------------------------------------------------------------------- |
| synth_ok_rate            | 24/24         | pipeline itself is stable — no fallback stitches, no errors, no timeouts      |
| gap_ran                  | 0/24          | gap researcher never fired (all assigned specialists succeeded on first pass) |
| top_domain_share (final) | 0.35          | not the monoculture we feared                                                 |
| category_count (final)   | 2.2 / 8       | breadth is the real gap — agent hits 2 of 8 source categories on average      |
| wall_brand_overlap       | 0.5 / 29      | marketing wall promises 29 brands; agent reaches <1 on average                |
| **faithfulness**         | **2.75**      | guarded metric, already low — many unsupported claims per report              |
| completeness             | 4.75          | reports do answer the questions asked                                         |
| specificity              | 3.08          | guarded                                                                       |
| investigative_stance     | 5.00          | every single run scored 5 — judge bias, almost certainly                      |
| tokens_avg               | 170k per run  |
| elapsed_avg              | 275 s per run |

## Per-venue

| venue               | faith    | spec | cat_cov | top_dom% | tokens | wall |
| ------------------- | -------- | ---- | ------- | -------- | ------ | ---- |
| **monsun**          | 3.25     | 3.62 | 2.8     | 0.31     | 146k   | 0.9  |
| **bar_leon**        | 3.12     | 3.25 | 2.0     | 0.38     | 179k   | 0.0  |
| **sliwka_w_kompot** | **1.88** | 2.38 | 1.8     | 0.35     | 187k   | 0.5  |

Śliwka w Kompot is materially worse on faithfulness (1.88 vs ~3.2 for the other two). Likely supply-side: less press / forum / industry coverage for a smaller Sopot venue → more room for the model to confabulate. Worth noting for query design — low-data venues reveal hallucination risk that high-data venues mask.

## Primary probes only (q1 / q2 / q3)

| metric                   | value |
| ------------------------ | ----- |
| runs                     | 9     |
| top_domain_share (final) | 0.33  |
| category_count           | 2.2   |
| faithfulness             | 2.44  |
| specificity              | 2.78  |
| completeness             | 4.33  |

Primary probes perform _slightly worse_ than the full set on faith and specificity. Not a major delta, but consistent with the hypothesis that openings/closings and pricing questions are harder for the current pipeline than broader trend questions.

## Flagged runs (faithfulness ≤ 2 or specificity ≤ 2)

13 of 24 runs flagged.

| run                                    | faith | spec |
| -------------------------------------- | ----- | ---- |
| bar_leon / q1_openings_closings        | 1     | 2    |
| bar_leon / q2_closures_lessons         | 1     | 1    |
| bar_leon / q8_wage_benchmarks          | 0     | 0    |
| monsun / q2_closures_lessons           | 2     | —    |
| monsun / q5_thriving_formats           | 1     | 2    |
| monsun / q7_market_performance         | 2     | —    |
| monsun / q8_wage_benchmarks            | 1     | 1    |
| sliwka_w_kompot / q1_openings_closings | 0     | 1    |
| sliwka_w_kompot / q3_price_comparison  | 0     | 0    |
| sliwka_w_kompot / q4_sentiment_themes  | 2     | 2    |
| sliwka_w_kompot / q5_thriving_formats  | 0     | 1    |
| sliwka_w_kompot / q6_market_saturation | 2     | —    |
| sliwka_w_kompot / q8_wage_benchmarks   | 1     | 2    |

Pattern: **wage benchmarking (q8) is bad across all venues** — 3/3 flagged. **Closures queries (q2) are weak** — 2/3 flagged. Śliwka is the hardest venue overall. If the judge is even roughly calibrated, this is real hallucination, not just style variance.

## What this changes for Phase C

The proposal was built assuming monoculture (top-domain share) was the primary defect. The baseline data reframes that:

1. **Top-domain share at 0.35 is acceptable.** Not the 80% Monsun monoculture. This dimension is fine.
2. **Category coverage at 2.2/8 is the real breadth problem.** Agent reliably reaches ~2 of 8 taxonomy categories. H1/H2 both plausibly target this.
3. **Faithfulness at 2.75 is the most urgent problem.** 13/24 reports have claims the judge can't trace. You've explicitly excluded a claim-verification agent, so faithfulness is unlikely to move dramatically in V1/V2 — but it must be guarded so we don't make it worse.
4. **Wall overlap at 0.5/29** — honest delivery is dramatically below marketing claim. This is a company-level concern (promises vs product), not just a research-depth issue.
5. **Investigative_stance is judge-biased.** Perfect scores on every run point to the rubric, not the agent. Drop it from decision gates until recalibrated.

## Operational takeaways

- **The eval harness works as designed.** 24 clean captures, ADK event parsing produces real domains via `web.domain`, per-run JSON rehydrates reliably, scorer + judge run to completion.
- **`gap_ran = 0/24`** is informative in its own right: the gap researcher's `_should_run` gate only fires when a specialist fails, and no specialist failed here. Means gap is not a hidden lever for Phase C — V1/V2 changes will be attributable cleanly.
- **Specialist dispatch varies per query**, not per venue. q4 (sentiment) reliably wakes `review_analyst`; q8 (wages) reliably wakes `operations`; q1/q2 lean on `market_landscape`. The orchestrator is doing real selection — which gives H2 room to move.

## 3 spot-checks for calibration

Before committing to Phase C, Adam to eyeball these reports and tell me whether the Gemini judge's scores match his read. If they do, we trust the judge for Phase C decisions. If they don't, we recalibrate the rubric.

1. **High-faith, high-diversity — `monsun / q1_openings_closings`**
   Judge: faith 5 / spec 5 / comp 5 / inv 5. Is this really top-tier, or is the judge lenient?

2. **Mid-range with faith/spec disagreement — `monsun / q2_closures_lessons`**
   Judge: faith 2 / spec 5 / comp 5 / inv 5. Specific but (per judge) not well-grounded. Does the report have lots of named restaurants/dates that aren't in the cited sources?

3. **Low-faith — `sliwka_w_kompot / q3_price_comparison`**
   Judge: faith 0 / spec 0 / comp 5 / inv 5. Judge says the report is essentially fabricated. Is it, or is it reasonable given Śliwka has almost no publicly-indexed pricing data?

## Next step

After calibration, design V1 (soft-prior specialist instructions) and V2 (orchestrator query-specific coverage constraints) informed by what we've learned: target category coverage not top-domain share, guard faithfulness hard, deprioritize investigative stance in the decision gate. Run V1/V2/V3 end-to-end against the same 24-combo matrix.

## Artifacts

- Per-run JSONs: `agent/evals/results/V0/*.json`
- Scored CSV: `agent/evals/scores/V0.csv`
- Baseline log: `agent/evals/logs/V0_baseline.log`
- Runner: `agent/evals/run_matrix.py`
- Parser: `agent/evals/parse_events.py`
- Scorer: `agent/evals/score.py`
- Judge rubric: `agent/evals/judge_rubric.md`
- Summarizer: `agent/evals/summarize.py`
