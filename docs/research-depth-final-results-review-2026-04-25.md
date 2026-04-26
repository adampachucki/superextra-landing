# Research-depth final results review

Date: 2026-04-25
Reviewer: Codex
Scope: review of the research-depth eval documents and local eval artifacts, with emphasis on Stage 2's V2.3 recommendation.

## Executive judgment

V2.3 is the strongest current ship candidate for the stated research-depth problem, but the Stage 2 report overstates the certainty of that conclusion. The deterministic scorecard supports V2.3 as a real improvement in source breadth: aggregate top-domain share improves from V0's 0.350 to 0.262, category coverage improves from 2.17 to 3.17, and wall-brand overlap improves from 0.46 to 1.17. The 22/24 scripted pairwise win rate against V0 is also a meaningful directional signal.

I would not present this as "done, ship with no reservations." Two targeted losses, one factual inconsistency in the Stage 2 writeup, and the judge-methodology mismatch need to be corrected before this goes to the executing team. The path forward should be simple:

1. Treat V2.3 as the candidate, not as fully proven.
2. Run a small targeted validation, not a new variant search.
3. If the validation passes, ship V2.3 exactly as tested: replace only `research_orchestrator.md` and `specialist_base.md`.
4. Do not add stricter orchestration code, more specialists, or a new V2.4 unless the targeted validation shows the same failure twice.

The core improvement appears to be the combination of two simple prompt-level changes:

- query-type coverage floors in the orchestrator
- source-prior/self-audit guidance in the specialist base prompt

That is the right complexity level. The remaining work should increase confidence, not expand the product surface.

## What I verified

I reviewed the six requested docs:

- `docs/research-depth-stage2-results-2026-04-25.md`
- `docs/research-depth-final-report-2026-04-25.md`
- `docs/research-depth-pairwise-verdicts-2026-04-25.md`
- `docs/research-depth-phase-b-baseline.md`
- `docs/research-depth-eval-plan.md`
- `docs/research-depth-next-stage-test-plan-2026-04-25.md`

I also checked the underlying artifacts in `agent/evals/`:

- `scores/*.csv`
- `results/*/*.json`
- `pairwise_verdicts/V0_vs_V2_3/*.json`
- `instructions_variants/V2_1`, `V2_2`, and `V2_3`
- `pairwise.py`, `score.py`, `parse_events.py`, and `run_matrix.py`

I did not rerun live agent evaluations. The review verifies the stored data and methodology, not fresh model behavior.

## Claims that hold

### V2.3 improves aggregate source breadth

The Stage 2 aggregate scorecard matches the CSVs.

| metric                  |     V0 |   V2.1 |   V2.2 |   V2.3 |
| ----------------------- | -----: | -----: | -----: | -----: |
| final top-domain share  | 0.3495 | 0.3267 | 0.2920 | 0.2615 |
| final category coverage | 2.1667 | 2.8333 | 2.5833 | 3.1667 |
| wall-brand count        | 0.4583 | 0.8750 | 1.2083 | 1.1667 |
| faithfulness            | 2.7500 | 2.5833 | 2.4583 | 2.5000 |
| specificity             | 3.0833 | 3.2083 | 3.1667 | 3.0833 |
| tokens avg              | 170.8k | 163.5k | 179.7k | 185.9k |
| elapsed avg             | 275.1s | 209.5s | 267.5s | 245.2s |

V2.3 is the best aggregate variant on top-domain share and category coverage. It is effectively tied with V2.2 on wall-brand overlap, not strictly better. It is not better than V0 or V2.1 on aggregate faithfulness/specificity.

### V2.3 is very strong on the primary probes

For q1/q2/q3 only:

| metric                  |     V0 |   V2.1 |   V2.2 |   V2.3 |
| ----------------------- | -----: | -----: | -----: | -----: |
| final top-domain share  | 0.3273 | 0.2737 | 0.2861 | 0.2877 |
| final category coverage | 2.2222 | 2.6667 | 2.7778 | 3.2222 |
| wall-brand count        | 0.3333 | 1.0000 | 1.5556 | 1.5556 |
| faithfulness            | 2.4444 | 2.1111 | 2.4444 | 3.3333 |
| specificity             | 2.7778 | 2.7778 | 3.5556 | 4.0000 |

This is the cleanest argument for V2.3. It is not the best primary variant on top-domain share, but it is the best on coverage and has the strongest primary-probe judge scores.

### The variance check is real and important

The documented V2.1 replication numbers are correct:

| metric                 | mean sample stdev | max sample stdev |
| ---------------------- | ----------------: | ---------------: |
| final top-domain share |             0.074 |            0.160 |
| final category count   |             0.760 |            1.528 |
| final URL count        |            12.479 |           22.855 |

Specialist dispatch varied in 4 of 9 primary-probe combos across V2.1 reps. That is enough variance to invalidate confident conclusions from one-off combo losses or wins.

### V2.3 fixes the specific monsun q2 breadth failure

The stored scores support the Stage 2 claim that V2.3 substantially improves the V2.1 monsun q2 failure mode:

| variant | specialists                                                                           | final URLs | top-domain share | categories | faith/spec |
| ------- | ------------------------------------------------------------------------------------- | ---------: | ---------------: | ---------: | ---------- |
| V0      | guest_intelligence, location_traffic, market_landscape                                |         26 |            0.269 |          3 | 2 / 3      |
| V2.1    | location_traffic, market_landscape, marketing_digital, menu_pricing                   |         13 |            0.615 |          1 | 5 / 5      |
| V2.2    | market_landscape, marketing_digital, menu_pricing, operations, review_analyst         |         11 |            0.818 |          1 | 1 / 2      |
| V2.3    | guest_intelligence, market_landscape, marketing_digital, menu_pricing, review_analyst |         52 |            0.462 |          5 | 2 / 3      |

V2.3 is much broader than V2.1 and V2.2 on this combo. It is not cleaner than V0 on top-domain share, but it adds two categories and many more domains.

## Findings that need correction

### 1. Stage 2 incorrectly says V2.2 ignored the review_analyst mandate

The Stage 2 doc says:

> V2.2's "Openings/closings - MUST include `review_analyst`" rule was supposed to fix monsun q2. On the actual V2.2 monsun-q2 run, the orchestrator dispatched `{market_landscape, marketing_digital, menu_pricing, operations}` - no review_analyst.

The artifacts contradict this. `agent/evals/results/V2_2/monsun__q2_closures_lessons.json` and `scores/V2_2.csv` both show:

`market_landscape, marketing_digital, menu_pricing, operations, review_analyst`

So the V2.2 failure was not caused by the orchestrator ignoring the `review_analyst` floor. It failed despite `review_analyst` being dispatched.

That changes the diagnosis:

- The issue is not "MUST include is soft."
- The issue is that adding `review_analyst` alone did not guarantee a better answer.
- V2.3's improvement is more likely from source-priors, different free specialist selection (`guest_intelligence` instead of `operations`), stochastic run variance, or synthesis behavior.

This correction matters because the Stage 2 recommendations currently reason from the wrong failure mechanism.

### 2. The Stage 2 "do not bundle V2.2's review_analyst mandate" advice is internally inconsistent

The recommendation says:

> Don't bundle V2.2's `review_analyst` mandate.

But `agent/evals/instructions_variants/V2_3/research_orchestrator.md` already includes the V2.2 `review_analyst` floor for openings/closings:

`market_landscape + menu_pricing + marketing_digital + review_analyst`

Therefore the actual actionable recommendation should be:

- Ship V2.3 exactly as tested.
- Do not invent a stricter V2.4 enforcement mechanism.
- Do not remove `review_analyst` from the tested V2.3 file unless rerunning the matrix.

### 3. The two V0-over-V2.3 pairwise losses should not be dismissed as harmless noise

The Stage 2 doc says both V0 wins are likely sampling noise. That is too casual.

One of the losses is `monsun x q1_openings_closings`, a primary target query. The deterministic row is meaningfully worse for V2.3:

| metric            |    V0 |  V2.3 |
| ----------------- | ----: | ----: |
| final URLs        |    40 |    25 |
| unique domains    |    19 |    10 |
| top-domain share  | 0.400 | 0.480 |
| category coverage |     5 |     2 |
| wall-brand count  |     1 |     1 |
| faithfulness      |     5 |     1 |
| specificity       |     5 |     1 |

The pairwise verdict also chose V0 because V0 surfaced a stronger parking/accessibility thesis. This is plausibly tied to V0's `location_traffic` and `guest_intelligence` dispatch, while V2.3 dispatched only the openings floor specialists.

Because category coverage drops by 3 categories, this is not comfortably inside the measured category-count variance. It might still be stochastic, but it should be validated before production.

The other V0 win, `bar_leon x q2_closures_lessons`, is less concerning but still useful. V0 won because it surfaced an operational/reputation "forced tip" issue and employee-review/Gowork-style evidence. V2.3 had better category count than V0 but worse top-domain share and weaker judge faithfulness.

### 4. V2.3's 22/24 pairwise win is real signal, but not the same kind of signal as the earlier Claude operator verdicts

The final report says Gemini-as-judge was too noisy to drive ship decisions, and that Claude operator-role subagents with WebFetch were the reliable judging mechanism.

Stage 2 then uses `agent/evals/pairwise.py`, which is a scripted Gemini 2.5 Pro judge. The script explicitly says the judge has no live web access and only reasons about internal consistency. That is a different methodology from the operator-subagent process in the earlier report.

This does not invalidate the 22/24 count. Pairwise judging is better than absolute 0-5 rubric scoring, and 22 wins out of 24 is strong directional evidence. But it should be described as "scripted Gemini pairwise triage," not as equivalent to the earlier verified operator-subagent verdicts.

### 5. The pairwise supporting URLs are not reliable evidence artifacts

I checked the 24 `V0_vs_V2_3` pairwise JSON files against the A/B run evidence. In 23 of 24 files, at least one `supporting_urls` entry is not present in either run's drawer, fetched URLs, or grounding entries as an exact URL.

Some are generic domains. Some are plausible canonical URLs. Some may be judge-generated. Since the judge has no web access, these URLs should not be treated as verification evidence.

The pairwise winner field is still usable as an A/B preference signal. The `supporting_urls` field should be treated as weak metadata until the pairwise harness either constrains URLs to source inputs or performs live verification.

### 6. The operator-subagent confirmation for V2.3 monsun q2 is not separately artifacted

The Stage 2 report contains a useful Claude operator-subagent quote and `VERDICT: V2_3`, but I found no separate transcript or JSON artifact outside `docs/research-depth-stage2-results-2026-04-25.md`.

That means the strongest qualitative confirmation for the V2.3 monsun q2 fix is not independently auditable from the repo. This should be appended to `docs/research-depth-pairwise-verdicts-2026-04-25.md` or stored under a verdict artifact path before committee review.

### 7. The cost summary has one wrong number

The Stage 2 report correctly states in one place that V2.3 is about +10% tokens vs V0 and +14% vs V2.1.

Later it says:

> Token/runtime cost is +10% over V0, ~6% over V2.1.

The actual aggregate ratios are:

| comparison   | tokens | elapsed |
| ------------ | -----: | ------: |
| V2.3 vs V0   |  +8.8% |  -10.9% |
| V2.3 vs V2.1 | +13.7% |  +17.1% |
| V2.3 vs V2.2 |  +3.4% |   -8.3% |

The cost is still acceptable, but the V2.1 comparison should be corrected.

### 8. The category metric undercounts one of V2.3's intended source-prior effects

`score.py` can classify `venue_own`, but only when given a `venue_own` map. The stored score CSVs do not show `venue_own` in any final category list. Competitor-owned domains like `restauracjamalika.pl`, `trafikgdynia.pl`, `restauracjamoon.pl`, and `miwogdynia.pl` are therefore not counted as "venue's own channels" in the category coverage metric.

This means category coverage is useful but incomplete. It likely understates V2.3's own-channel gains, and it does not fully measure the exact source-prior category V2.3 added.

## Methodology assessment

### What was strong

The eval harness is a meaningful improvement over anecdotal prompt evaluation. The important design choices were correct:

- multi-venue matrix rather than single-example testing
- primary probes plus broader query spread
- capture of ADK events rather than relying only on visible `sources[]`
- deterministic metrics separated from judge metrics
- subprocess-per-variant instruction overlays
- variance check after noticing run-level instability

This is enough to make a responsible prompt-level ship decision, provided the report does not overclaim.

### What remains weak

The evaluation still has four material limitations:

1. Judge inconsistency remains unresolved. Stage 2 relies on Gemini pairwise after Stage 1 found Gemini unreliable. Pairwise helps, but does not solve factual verification.
2. V2.3 was not directly pairwise-compared against V2.1 or V2.2. The 22/24 result is V2.3 vs V0 only.
3. V0 was run on 2026-04-24; V2.2/V2.3 and V2.1 reps were run on 2026-04-25. For time-relative queries like openings/closings, this is a minor but real confound.
4. The strongest V2.3 qualitative confirmation is not separately artifacted.

None of these require a new architecture. They require a smaller, cleaner validation pass.

### Overfitting risk

There is a real test-set-tuning risk in the current result.

The queries were known. The scoring dimensions were known. V2.x explicitly added query-type rules for those known buckets. V2.3 added source-prior language that overlaps with the scoring taxonomy. The scripted pairwise judge prompt also rewards coverage of evidence surfaces. That creates a legitimate concern that V2.3 may be optimized for this eval rather than generally better.

I do not think this invalidates V2.3. The changes are not narrow answer hacks. They do not encode venue-specific facts like "for Monsun mention Malika" or "for Bar Leon mention Cloud One." They encode general behaviors: openings/closings need market, pricing, delivery/social, and review evidence; specialists should avoid source monoculture and deliberately search different source types. Those are product-real evidence surfaces for restaurant market intelligence, not artificial metric artifacts.

The concern should change the confidence claim, not the candidate. V2.3 should be treated as the best candidate from the development set, then validated on a frozen holdout before being called proven.

The validation discipline matters:

- Freeze V2.3 before the holdout.
- Use queries not seen during this project, preferably freeform production-like wording rather than TopicPill text.
- Include multi-topic and follow-up turns because coverage-floor prompts can fail when a user asks for two things at once.
- Include at least a small non-Tricity Polish sample; optionally include Berlin if cross-market confidence matters.
- Judge mostly by operator pairwise review with source checking. Use deterministic diversity metrics as diagnostics, not as the main gate.
- Do not tune V2.3 after seeing holdout failures unless a new holdout is created.

This is the difference between "we improved the eval" and "we improved the product."

## Recommendation

### Recommended path

Run a narrow validation pass, including a small frozen holdout, then ship V2.3 if it passes.

Validation should answer four questions:

1. Does V2.3's `monsun x q1_openings_closings` loss repeat?
2. Does V2.3 still beat V2.1/V2.2 on the q2 closures regression when judged directly?
3. Are the two V0 pairwise losses actually worse under operator review with source checking?
4. Does V2.3 still help on unseen production-like queries, or did we tune to the known eval?

Suggested minimal validation:

| test                 | variants              | combos                                                            | reps | reason                                                            |
| -------------------- | --------------------- | ----------------------------------------------------------------- | ---: | ----------------------------------------------------------------- |
| Targeted rerun       | V0, V2.3              | `monsun q1`, `bar_leon q2`                                        |    3 | tests whether the two V0 wins repeat                              |
| Candidate comparison | V2.1, V2.2, V2.3      | `monsun q2`, `monsun q1`, `bar_leon q2`, `sliwka q1`, `sliwka q3` |    1 | compares candidate variants directly on the known decision points |
| Frozen holdout       | V0, V2.3              | 6-8 unseen freeform queries across 2-4 venues                     |    1 | tests generalization beyond the known eval fixture                |
| Operator review      | V0/V2.3 and V2.1/V2.3 | the same targeted combos                                          |  n/a | source-checks the close or suspicious cases                       |

Run these interleaved on the same day where possible. The current V0/V2.3 comparison crosses 2026-04-24 and 2026-04-25, which is probably not decisive but is avoidable in a final validation.

This is intentionally small. It avoids launching another broad variant search and focuses on the exact places where the current recommendation is vulnerable, plus a holdout check for test-set tuning.

### Ship criteria

Ship V2.3 if:

- `monsun q1` does not repeatedly lose to V0 under direct operator review
- V2.3 beats or ties V2.1/V2.2 on `monsun q2`
- V2.3 wins or ties V0 on the frozen holdout without obvious operator-value regressions
- no new deterministic collapse appears in the targeted reruns
- the team corrects the Stage 2 report's factual inconsistencies before using it as the decision record

If those pass, ship the tested V2.3 files:

- `agent/superextra_agent/instructions/research_orchestrator.md`
- `agent/superextra_agent/instructions/specialist_base.md`

Do not ship any untested modification to those files.

### What not to do

Do not respond to the `monsun q1` loss by adding another hard floor immediately. The obvious temptation is to add `location_traffic` or `guest_intelligence` to the openings/closings floor, but that expands cost and prompt complexity without proof. V2.2 had `location_traffic` on monsun q1 and still produced weak scores, so the root cause is not simply "missing location_traffic."

Do not build a stricter dispatch enforcement mechanism. V2.2 and V2.3 both obeyed the tested coverage floors. The documented "MUST was ignored" diagnosis is false for the stored V2.2 monsun q2 artifact.

Do not reintroduce V1's verification-discipline rule. The Stage 1/2 evidence is consistent that this rule probably made specialists too conservative and interacted badly with coverage floors.

Do not treat V2.3 as solving faithfulness. Aggregate faithfulness is lower than V0 and V2.1. V2.3 is a research-depth improvement, not a factuality fix.

## Root-cause read

The original failure looked like source monoculture, but the better root-cause chain is:

1. The orchestrator did not reliably map certain query types to the evidence surfaces needed to answer them.
2. Specialists often searched from generic/default source priors, so even when the right specialist ran, it could cluster around familiar domains.
3. The evaluator initially overtrusted single runs and noisy judge scores, hiding both false positives and false negatives.

V2.3 addresses the first two with simple prompt changes. The variance check and pairwise harness start to address the third, but the judging stack is not yet strong enough to call the result bulletproof.

The simple production fix is still prompt-only. The deeper process fix is to make future prompt changes pass:

- deterministic aggregate scorecard
- targeted repeated reruns on known failure combos
- operator-reviewed pairwise checks for close calls
- clear artifacting of human/operator verdicts

## Notes for the executing team

Use V2.3 as the base candidate. The evidence does not justify further broad exploration right now.

Before committee review, update `docs/research-depth-stage2-results-2026-04-25.md` to correct:

- V2.2 did dispatch `review_analyst` on monsun q2.
- V2.3 includes the V2.2 review_analyst floor.
- V2.3's wall-brand overlap is a tie/slight loss vs V2.2, not an outright win.
- V2.3's cost vs V2.1 is +13.7% tokens and +17.1% elapsed, not ~6%.
- The scripted pairwise judge is Gemini without live web access; it is not equivalent to the earlier Claude operator-subagent method.

Append or artifact the V2.3 monsun q2 operator-subagent transcript. That quote is too important to exist only as an embedded excerpt.

If the team wants to ship without more testing, the honest recommendation is:

> Ship V2.3 as a controlled research-depth improvement, with known residual risk on `monsun q1_openings_closings` and no claim that faithfulness is solved.

My preferred recommendation is slightly more conservative:

> Run the small targeted validation plus frozen holdout above. If it passes, ship V2.3 exactly as tested.
