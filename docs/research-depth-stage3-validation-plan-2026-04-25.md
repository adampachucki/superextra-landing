# Stage 3 — V2.3 validation plan (amended)

## Plan amendments (post-review)

A second review flagged six issues with the original plan; all verified and accepted. Changes incorporated:

1. **Holdout queries are now freeform, not pill-derived.** Pill phrasing is too close to the design surface V2.3 was tuned around — phrasing differs but query-type signal is the same. Replaced with messy operator-style queries written outside the test fixture by Adam (in this turn). All 5 queries are inherently multi-topic, so a separately-labelled multi-topic query is no longer needed.
2. **Holdout venues go in a separate file.** `venues_holdout.json` instead of modifying `venues.json` — keeps the original benchmark matrix clean.
3. **Scripted Gemini pairwise demoted to diagnostic.** The 23/24 fabricated-URL finding makes its `winner` field a preference signal, not a verification. Used now to _select_ close-call combos for operator review, not as a hard ship gate.
4. **Phase B criterion expanded beyond metrics.** Original monsun q1 issue was faith/spec collapse alongside category drop. Pass criterion now includes operator-subagent review of any rerun showing simultaneous metric collapse.
5. **Berlin reframed as exploratory probe, not validation.** V2.3 is being judged on Polish performance only. Berlin informs future cross-market work but does not gate ship.
6. **Multi-topic stress test is woven into the holdout set.** Adam's 5 freeform queries each combine 2–3 query buckets (pricing + delivery, openings + traffic, competitor + own-venue, etc.), so coverage-floor robustness is tested across every holdout run rather than via a single isolated multi-topic query.

## Context

Stage 2 recommended shipping V2.3 with strong claims (22/24 pairwise wins, dominant on aggregate metrics). Two sets of issues now sit between that recommendation and a final ship decision:

**External reviewer (Codex) findings**, all verified against the artifacts:

1. Five factual errors in `docs/research-depth-stage2-results-2026-04-25.md` — most consequential: V2.2 _did_ dispatch `review_analyst` on monsun q2 (I had reported it didn't), so the "MUST-include is soft" diagnosis is wrong; the win story for V2.3 is V1's source-priors block, not orchestrator obedience.
2. The "don't bundle V2.2's review_analyst mandate" recommendation contradicts V2.3 itself (V2.3 has the mandate).
3. Cost numbers wrong: V2.3 vs V2.1 is +13.7% tokens / +17.0% elapsed (not ~6%).
4. monsun q1 V0 win is a 3-category drop (5→2) plus faith 5→1 — ~2σ outside variance band, NOT comfortably stochastic.
5. 23 of 24 scripted Gemini pairwise verdicts contain at least one fabricated supporting URL. The `winner` field is preference signal; `supporting_urls` is metadata noise. The 22/24 result is therefore pairwise preference, not source-verified judgment.

**User's overfitting concern**: every test query was visible during V2.x design; the scoring metrics (top-domain share, category coverage) align with the changes V2.3 makes; the variants were tuned iteratively against the same 24-combo matrix. Held-out generalization is untested.

This plan does **not** propose a new variant. V2.3 stays the candidate. It proposes a targeted validation pass to confirm or refute the Stage 2 ship recommendation through replication, candidate comparison, and held-out generalization. If V2.3 passes, ship as-tested. If V2.3 fails, document the failure mode and reconsider — do not patch reactively.

## Goals

1. Correct the Stage 2 doc factual errors before committee review.
2. Determine whether the monsun q1 V0 win repeats (signal vs sampling variance).
3. Confirm V2.3 ranks first under operator review on the original failure cases.
4. Test V2.3 on **truly held-out queries** — Adam-written, multi-topic by design, no pill-style phrasing.
5. Test Polish-market generalization on a Warsaw venue (gates ship). Test Berlin behavior **as exploratory probe only** — does not gate ship; informs future cross-market work.

## Phases

### Phase A — Doc corrections (no compute, ~20 min)

Edit `docs/research-depth-stage2-results-2026-04-25.md` only:

1. Replace the "V2.2 ignored its review*analyst mandate on monsun q2" passage. New diagnosis: V2.2 \_did* dispatch review_analyst (verified in `evals/results/V2_2/monsun__q2_closures_lessons.json`); V2.2 still failed because more specialists alone don't guarantee a better answer; V2.3's gain over V2.2 is from V1's source-priors block in `specialist_base.md`, not from any orchestrator-obedience improvement.
2. Remove the recommendation "Don't bundle V2.2's review_analyst mandate." V2.3 already includes it. Replace with: "Ship V2.3 exactly as tested in `evals/instructions_variants/V2_3/`. Do not strengthen or weaken the dispatch rules."
3. Correct the cost section. V2.3 vs V0: +8.8% tokens / −10.9% elapsed. V2.3 vs V2.1: +13.7% tokens / +17.0% elapsed. V2.3 vs V2.2: +3.4% tokens / −8.3% elapsed.
4. Soften "wall overlap is best" to "wall overlap ties V2.2 (1.17 vs 1.21) — both materially better than V0's 0.46."
5. Add a note next to the 22/24 pairwise win stating that the scripted Gemini judge's `supporting_urls` field was found unreliable (23/24 verdicts contain fabricated URLs); the `winner` field is preference signal but not source-verified.
6. Soften the "monsun q1 V0 win is sampling noise" claim. New language: "The monsun q1 V0 win is a 3-category drop (5→2) and faith 5→1 — outside the measured variance band (mean σ=0.76 / max σ=1.53 on category count). Needs replication before dismissed."

Append to `docs/research-depth-pairwise-verdicts-2026-04-25.md`:

- The operator-subagent transcript for V0 vs V2.3 on monsun q2 (the strongest qualitative confirmation of the V2.1 regression fix), currently embedded only in Stage 2 doc as a quote.

### Phase B — Targeted reruns (~12 min wall-clock if parallelized)

Re-run V0 and V2.3 on the two combos where V0 won the V0-vs-V2.3 pairwise:

- `monsun × q1_openings_closings`
- `bar_leon × q2_closures_lessons`

3 reps each × 2 variants × 2 combos = **12 runs**, output to `evals/results/V0_rerun/` and `evals/results/V2_3_rerun/` with rep suffix on filenames or a per-rep subdir. Score deterministically; compute σ across reps to compare against the Stage 2 variance band.

**Pass criteria** (per combo, all required):

- V2.3 wins or ties V0 on category coverage in ≥2 of 3 reps.
- No rep shows V2.3 with cat<2 simultaneous with top-domain share >0.6.
- **No rep shows simultaneous collapse on faith AND specificity (e.g., both ≤2)** — the original monsun q1 V0 win had faith/spec 5→1, not just cat drop. If any V2.3 rerun shows that pattern, trigger an operator-subagent review of that specific report and use the operator verdict as the tiebreaker for that combo.

### Phase C — Candidate showdown (~5 min, no new runs)

Operator-subagent pairwise (Claude via Agent tool, with WebFetch) on already-captured V2.1 / V2.2 / V2.3 outputs:

- `monsun × q2_closures_lessons` — the original failure case
- `sliwka × q1_openings_closings` — the original Food Hall miss
- `bar_leon × q3_price_comparison` — verifies V2.3 hasn't regressed on pricing

3 subagent calls, each ranks "best, middle, worst." Goal: confirm V2.3 ranks 1 or tied-1 on ≥2 of 3.

### Phase D — Held-out queries × held-out venues (~70 min wall-clock)

**Venues** stored in a NEW file `agent/evals/venues_holdout.json` (does NOT modify `venues.json`):

- **Boska Praga, Warsaw** — Polish, non-Tricity. **Gates ship**. Tests whether V2.3's Polish-specific source examples in `specialist_base.md` generalize to a different Polish city.
- **Zeit für Brot, Alte Schönhauser Allee, Berlin** — non-Polish. **Exploratory probe only — does NOT gate ship.** Informs future cross-market work; V2.3's German equivalents aren't named in instructions, so degradation here is expected and acceptable.

The runner already auto-resolves Place IDs via Places API; spot-check that Zeit für Brot resolves to the Alte Schönhauser Allee location specifically (the chain has multiple Berlin sites; the resolver picks by prominence).

**Queries** — 5 truly-held-out queries written by Adam in this planning turn. All are messy, operator-real, and multi-topic to varying degrees, which is exactly what's needed to stress V2.3's coverage rules. Pill text was rejected because the unused pills are still query-type variants of what V2.x targets (phrasing differs but the query-type signal V2.3's coverage rules pattern-match on is the same).

| #   | query                                                                                                                                | query buckets stressed                                                      |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| HQ1 | _"A few places near us seem busy but others keep closing. What is actually separating the winners from the weak spots around here?"_ | openings/closings + thriving formats + competitor analysis                  |
| HQ2 | _"Are nearby restaurants discounting or using delivery apps in ways that make our current pricing look exposed?"_                    | pricing + marketing/digital + delivery platforms                            |
| HQ3 | _"What changed in this neighborhood recently that could affect dinner traffic, not just lunch or tourist traffic?"_                  | openings/closings + location/traffic + daypart-specific framing             |
| HQ4 | _"Which competitors look most vulnerable right now, and what warning signs should we watch for in our own business?"_                | competitor analysis + own-venue forecasting + closure-risk indicators       |
| HQ5 | _"If we had to make one menu or positioning change this month based on the local market, what would the evidence support?"_          | synthesis across pricing + marketing + market — most analytically demanding |

Save as `agent/evals/queries_holdout.json`.

**Run matrix**: 5 queries × 2 venues × 2 variants (V0 + V2.3) = **20 runs**. Output to `evals/results/V0_holdout/` and `evals/results/V2_3_holdout/`. Parallelize by spawning V0 and V2.3 as separate subprocesses simultaneously.

**Scoring**:

- Deterministic via existing `score.py` — primary signal.
- **Scripted Gemini pairwise** via `pairwise.py` on all 10 (V0 vs V2.3) combos — used to **select close-call combos for operator review**, not as a ship gate. Wins/losses informational only.
- **Operator-subagent pairwise** (Claude with WebFetch) on 4 selected combos:
  - The closest call from Gemini pairwise (preference signal but indecisive)
  - The largest deterministic-metric V2.3 loss (if any)
  - **HQ5 × Warsaw** — the most synthesis-heavy / multi-topic-dense query, hardest test of V2.3's coverage robustness
  - 1 Berlin combo, Adam-selected or Claude-selected (informs the exploratory Berlin assessment, not a gate)

### Phase E — Synthesis & decision (~30 min)

Write `docs/research-depth-stage3-validation-2026-04-25.md` covering:

- Phase A: confirmation that doc errors are corrected (with diff summary).
- Phase B: rerun σ + per-combo pass/fail.
- Phase C: candidate-showdown ranks.
- Phase D: held-out aggregate scorecard, pairwise tally, operator verdicts, Berlin-specific observations.
- Decision section evaluating each ship gate explicitly with numbers.
- Final recommendation: ship V2.3, or document failure & next steps.

## Decision criteria — ship V2.3 only if ALL true

Note: scripted Gemini pairwise is **not** a hard gate. Used only to surface close-call combos for operator review.

1. **Monsun q1 rerun**: V2.3 wins or ties V0 on category coverage in ≥2 of 3 reps. No rep shows simultaneous cat<2 AND top-domain >0.6. **And** no rep shows simultaneous faith ≤2 AND spec ≤2 — if it does, an operator-subagent review must rule the rerun "not substantively worse than V0."
2. **Bar Leon q2 rerun**: same thresholds.
3. **Candidate showdown**: V2.3 ranks first or tied-first in ≥2 of 3 contested combos under operator review.
4. **Held-out aggregate (Warsaw venue only)**: V2.3 final top-domain share ≤0.40, final category coverage ≥2.5 averaged across the 5 queries × Warsaw, AND both metrics distinguishably better than V0 on the same Warsaw runs.
5. **Held-out operator pairwise**: of the 3 non-Berlin operator-judged combos (closest call + largest deterministic loss + HQ5 × Warsaw), V2.3 wins or ties ≥2 of 3.
6. **Multi-topic robustness**: V2.3 produces `synth_outcome=ok` on every one of the 10 holdout runs (5 queries × 2 venues). On HQ5 specifically (the most synthesis-heavy query), the orchestrator must dispatch ≥3 specialists spanning at least 2 distinct query buckets, AND the operator review must not call V2.3 substantively worse than V0.

**Berlin (exploratory, not gated)**: produces `synth_outcome=ok` and a non-garbage `final_report`. V2.3 may lose to V0 on Berlin quality without affecting the ship decision. Findings inform a separate future cross-market work item.

If V2.3 passes all 6 gates: replace the two production files with V2.3 versions:

- `agent/superextra_agent/instructions/research_orchestrator.md` ← `evals/instructions_variants/V2_3/research_orchestrator.md`
- `agent/superextra_agent/instructions/specialist_base.md` ← `evals/instructions_variants/V2_3/specialist_base.md`

If V2.3 fails any: document the specific failure mode in the Stage 3 doc; do **not** patch reactively. Convene with the user/committee on whether to (a) ship with documented limitation, (b) build a targeted V2.3.1 patch (limited scope), or (c) hold ship pending further investigation.

## Files that will be modified during execution

- `docs/research-depth-stage2-results-2026-04-25.md` — corrections only (Phase A)
- `docs/research-depth-pairwise-verdicts-2026-04-25.md` — append monsun q2 V2.3 transcript + Stage 3 verdicts (Phase A + E)
- `docs/research-depth-stage3-validation-2026-04-25.md` — new file (Phase E)
- `agent/evals/venues_holdout.json` — **new file**, separate from `venues.json` (Phase D). Original `venues.json` not modified.
- `agent/evals/queries_holdout.json` — new file (Phase D)
- `agent/evals/results/V0_rerun/`, `V2_3_rerun/`, `V0_holdout/`, `V2_3_holdout/` — new dirs (Phases B + D)
- `agent/evals/scores/V0_rerun.csv`, `V2_3_rerun.csv`, `V0_holdout.csv`, `V2_3_holdout.csv` — new (Phases B + D)
- `agent/evals/pairwise_verdicts/V0_vs_V2_3_holdout/` — new dir, 10 verdicts (Phase D)

## Files that will NOT be modified during Stage 3

- `agent/superextra_agent/instructions/research_orchestrator.md` — only updated _after_ Stage 3 passes, not during
- `agent/superextra_agent/instructions/specialist_base.md` — same
- `agent/evals/venues.json` — kept clean; held-out venues go in `venues_holdout.json` instead
- `agent/evals/queries.json` — kept clean; held-out queries go in `queries_holdout.json`
- All other agent code (specialists.py, agent.py, run_matrix.py, parse_events.py, score.py, pairwise.py) — runner needs to accept `--venues` and `--queries` flags pointing at the holdout files; existing `--venues` / `--queries` flags already do this
- All Stage 1 / Stage 2 result/score artifacts other than Phase A doc corrections

## Verification (end-to-end check this plan can be executed)

1. **Place ID resolution sanity check** before kicking off Phase D runs: a quick `search_restaurants` test for both new venues. For Berlin specifically, confirm the resolved Place ID's address matches Alte Schönhauser Allee (street name in formatted address).
2. **Run smoke** on one Phase D combo before launching the full matrix to confirm V2.3's specialist instructions handle a non-Polish venue without `synth_outcome != "ok"`.
3. **Score smoke** on at least one rerun JSON before launching the full Phase B+D scoring to confirm the existing scorer handles new venue keys without crashing on missing taxonomy entries.
4. **Pairwise smoke** via `evals/pairwise.py` on one of the held-out combos before batch-spawning all 12.
5. **Manual eyeball** on the Berlin V2.3 final report — confirm it's not substantively garbage even if it loses pairwise.

## Cost estimate

- Compute: ~2 hours wall-clock if all Phase B + D runs are parallelized 4-way; ~5 hours serial.
- Tokens: ~36 new agent runs × ~180k = ~6.5M Vertex tokens.
- Operator-subagent calls (Claude via Agent tool, with WebFetch): ~7 calls × ~30k tokens = ~210k Claude tokens.
- Real cost: ~$5–15 USD depending on Vertex pricing.
- Adam time: ~30 min reviewing scorecards in Phases B/D, ~30 min reviewing Stage 3 doc and final ship/no-ship decision.

## Risks

1. **Place ID resolution may pick wrong Berlin location.** Zeit für Brot has multiple Berlin sites; the search may resolve to the most-popular rather than Alte Schönhauser Allee. Mitigation: spot-check resolved Place ID's `formattedAddress` field after resolution; if wrong, adjust the secondary text in `venues.json` to be more specific.
2. **V2.3's Polish source examples in `specialist_base.md` may produce off-target Berlin research** (specialist names trojmiasto.pl as a community example). The instructions are language-aware (the prompt has _"If the query is in a specific language … prioritize sources published in that language"_), but the examples are static. Result may be lower quality than ideal on Berlin even if technically functional. This is a known design limitation — acknowledged in the report, not a blocker.
3. **Held-out queries may be too easy** — if all 5 are queries V2.3 also handles well, we won't disambiguate "V2.3 generalizes" from "the test was easy." Mitigation: every Adam-written query stresses ≥2 buckets, several stress 3, and HQ5 is a deliberate synthesis stress test that requires V2.3's coverage rules to compose correctly across pricing + marketing + market. If V2.3 fails on HQ5 specifically, that's a meaningful generalization failure even if the other 4 pass.
4. **Operator-subagent verdicts on contested combos may split across reruns** (e.g., 2 V2.3 wins, 1 V0 win). Decision criterion handles this via "≥2 of 3" thresholds.
5. **Berlin venue may fail to resolve at all** (unlikely with Places API but possible). Mitigation: fall back to coordinates in the Place ID lookup if needed; or substitute a different Berlin venue if Adam picks one.

## Out of scope for Stage 3 (deferred)

- New variants (V2.4, V3.x, etc.) — V2.3 is the candidate; iteration only if V2.3 fails validation.
- Follow-up turn testing — Tier 4 from the next-stage plan; can be a separate Stage 4 if desired.
- Cross-market validation beyond exploratory Berlin probe — V2.3 ship is Polish-market only; non-Polish needs German-specific source priors and a separate validation cycle if and when cross-market becomes a goal.
- Wage-benchmarking capability investigation — flagged as a separate project.
- Marketing-wall delivery audit — flagged as a separate project.
- Calibrated Gemini judge — flagged for later. Gemini scripted pairwise stays as a diagnostic only, not a gate.
- Replay capability for re-scoring — small improvement, defer.

(Multi-topic testing was out-of-scope in the first draft; now in scope and woven through every holdout query, since Adam's 5 freeform queries each combine 2–3 query buckets.)
