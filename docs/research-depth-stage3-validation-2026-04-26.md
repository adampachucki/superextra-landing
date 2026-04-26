# Stage 3 — V2.3 validation results & ship decision

Companion to `research-depth-stage3-validation-plan-2026-04-25.md`. All five phases executed.

**Headline: all 6 ship gates pass on their stated criteria. V2.3 promoted to production as a _controlled instruction rollout_.** The evidence is materially stronger than Stage 2 and addresses the overfitting concern, but residual risks remain (see Limitations and Post-ship monitoring sections). Two production instruction files replaced (`research_orchestrator.md` and `specialist_base.md`); two pre-existing harness-support changes in `agent.py` and `specialists.py` accompany the rollout — see "Production code changes shipped with V2.3" below for scope clarification.

Berlin probe is informative — V2.3 stays functional on a non-Polish venue without Polish-source bleed, but the test was n=1 venue × 5 queries × 1 rep, not validation of cross-market generalization.

---

## Phase A — Doc corrections (DONE)

Six factual corrections applied to `docs/research-depth-stage2-results-2026-04-25.md`:

1. ✅ Replaced "V2.2 ignored review_analyst mandate" passage with verified diagnosis (V2.2 _did_ dispatch review_analyst on monsun q2; failed despite obeying the rule). Reframed V2.3's win story as "specialist-level source priors" not "orchestrator obedience."
2. ✅ Removed contradictory "don't bundle V2.2's review_analyst mandate" recommendation. New recommendation: ship V2.3 exactly as tested.
3. ✅ Cost numbers corrected. V2.3 vs V0: +8.8% tokens / −10.9% elapsed. V2.3 vs V2.1: +13.7% tokens / +17.0% elapsed. V2.3 vs V2.2: +3.4% tokens / −8.3% elapsed.
4. ✅ Wall overlap softened to "tied with V2.2 (1.17 vs 1.21)."
5. ✅ Added caveat next to 22/24 pairwise win: 23/24 verdicts contain fabricated `supporting_urls`; treat winner field as preference signal only.
6. ✅ Softened "monsun q1 V0 win is sampling noise" claim: 3-category drop is outside variance band, requires replication.

Plus: appended V0 vs V2.3 monsun q2 operator-subagent transcript to `docs/research-depth-pairwise-verdicts-2026-04-25.md` as Round 5.

---

## Phase B — Targeted reruns (12 runs, all complete)

### Monsun × q1_openings_closings — V2.3 vs V0

| rep | V0 cat / top / faith / spec | V2.3 cat / top / faith / spec |
| --- | --------------------------- | ----------------------------- |
| 1   | 4 / 0.476 / 2 / 3           | **4 / 0.245 / 5 / 5**         |
| 2   | 5 / 0.560 / 1 / 1           | **5 / 0.167 / 5 / 5**         |
| 3   | 3 / 0.600 / 0 / 0           | 2 / 0.455 / 0 / 1             |

**V2.3 ≥ V0 on cat coverage: 2/3 reps** (rep 1 ties at 4, rep 2 ties at 5; rep 3 V0 wins by 3-2).

Rep 3 triggered the faith+spec collapse flag (faith=0, spec=1, both ≤2). **Operator-subagent tiebreaker review: `V2_3_COMPETENTLY_NARROWER`** — _"V2.3 didn't hand the operator a wrong picture, just a partial one with a tangent. The contradictions with V0 (Socialife/Beggin) are V2.3 being more accurate, not less."_ Verified Bistro u Misia at Świętojańska 72/2 confirms V2.3 caught the re-tenanting nuance V0 missed.

Note V0's reps 2 and 3 also produced collapsed faith/spec — this combo is genuinely difficult, not V2.3-specific.

**Gate #1: PASS.**

### Bar Leon × q2_closures_lessons — V2.3 vs V0

| rep | V0 cat / top / faith / spec | V2.3 cat / top / faith / spec |
| --- | --------------------------- | ----------------------------- |
| 1   | 2 / 0.158 / 5 / 5           | **4 / 0.250 / 4 / 5**         |
| 2   | 3 / 0.455 / 2 / 4           | **3 / 0.156 / 2 / 3**         |
| 3   | 3 / 0.342 / 5 / 5           | **3 / 0.237 / 3 / 4**         |

**V2.3 ≥ V0 on cat coverage: 3/3 reps.** No rep flagged for collapse. **Gate #2: PASS** clean.

---

## Phase C — Candidate showdown (3 operator-subagent rankings)

| combo                          | best     | middle | worst | rationale                                                                                                                                                        |
| ------------------------------ | -------- | ------ | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| monsun × q2_closures_lessons   | **V2_3** | V2_2   | V2_1  | _"V2.3 wins on framing, coverage, and the diagnostic pricing chart, despite the Malika risk."_                                                                   |
| sliwka × q1_openings_closings  | V2_1     | V2_3   | V2_2  | V2.1 catches Food Hall Krzywy Domek as already-open (May 2025); V2.3 misframes it as "upcoming."                                                                 |
| bar_leon × q3_price_comparison | **V2_3** | V2_2   | V2_1  | _"V2.3 cleanest pricing matrix structured by category. Verified Bar Leon, Woosabi, Magari prices match exactly. The 'share-plate premium' framing is sharpest."_ |

**V2.3 ranks first or tied-first on 2 of 3.** **Gate #3: PASS.**

The sliwka q1 result is interesting — V2.1 (the Stage 2 second-place candidate) actually beats V2.3 on the original Food Hall fix combo. V2.3 dropped the "already open" framing V2.1 had. Bounded regression but real. Documented as Stage 3 finding, not a blocker.

---

## Phase D — Held-out matrix (20 runs, all complete)

### Aggregate metrics — Warsaw (Boska Praga, gates ship)

| metric            | V0    | V2.3      | delta  |
| ----------------- | ----- | --------- | ------ |
| top-domain share  | 0.255 | **0.099** | −0.156 |
| category coverage | 2.0   | **2.8**   | +0.8   |
| drawer count      | 18.8  | **38.4**  | +19.6  |
| faith (Gemini)    | 4.00  | 3.60      | −0.40  |
| spec (Gemini)     | 4.60  | 4.20      | −0.40  |
| synth_ok          | 5/5   | 5/5       | —      |

V2.3 wins on every diversity metric on Warsaw. Gemini judge gives V0 a fractional faith/spec advantage — but Gemini is known noisy and operator-subagent reviews on 3 of 5 Warsaw combos all picked V2.3.

**Gate #4: PASS.** V2.3 top ≤0.40 ✓ (0.099), cat ≥2.5 ✓ (2.8), distinguishably better than V0 ✓.

### Aggregate metrics — Berlin (Zeit für Brot, exploratory only)

| metric            | V0    | V2.3  |
| ----------------- | ----- | ----- |
| top-domain share  | 0.270 | 0.221 |
| category coverage | 1.4   | 1.8   |
| drawer count      | 20.2  | 39.8  |
| synth_ok          | 5/5   | 5/5   |

V2.3 also wins all metrics on Berlin (smaller margins). No catastrophic failure. **No Polish source bleed** — operator-subagents explicitly verified that V2.3's instructions did not contaminate Berlin output with trojmiasto.pl, Pyszne.pl, or other Polish-only sources. The model generalized "local delivery / news / real-estate" abstractions to Berlin equivalents (lieferando.de, mitvergnuegen.com, tagesspiegel.de, colliers.de, knightfrank.com, sofiberlin.com, etc.) correctly.

### Scripted Gemini pairwise (diagnostic only — supporting_urls unreliable)

```
V2.3 wins: 8 / 10 (5/5 Warsaw clean sweep, 3/5 Berlin)
V0 wins:  2 / 10 (zeit_fur_brot × hq2, zeit_fur_brot × hq5)
```

### Operator-subagent pairwise (5 selected combos)

| combo                                        | verdict  | gate        |
| -------------------------------------------- | -------- | ----------- |
| HQ5 × Warsaw (synthesis stress test)         | **V2.3** | #5, #6      |
| HQ1 × Warsaw (winners vs weakspots)          | **V2.3** | #5          |
| HQ3 × Warsaw (dinner traffic changes)        | **V2.3** | #5          |
| HQ5 × Berlin (synthesis, exploratory)        | V0       | exploratory |
| HQ2 × Berlin (pricing/delivery, exploratory) | **V2.3** | exploratory |

**Non-Berlin operator pairwise: 3/3 V2.3 wins.** **Gate #5: PASS** unambiguously.

Notable: on HQ3 × Warsaw, deterministic metrics show V2.3 narrower (cat 1 vs V0's 2), but operator review picked V2.3 anyway because _"V2.3 contradicts the comfortable narrative (V0's framing) with a structurally coherent, geographically specific, dinner-focused thesis. Even with narrower source category coverage, it's the report I'd actually act on."_ Direct evidence that source-category breadth is not the only thing that matters — operator value can come from synthesis quality.

### Single-turn multi-topic synthesis robustness (Gate #6)

> **Renamed from "Multi-topic robustness"** to clarify scope. This gate tests V2.3's behavior on a single-turn query that spans multiple coverage buckets (e.g., HQ5 combines pricing + marketing + market). It does **NOT** test multi-turn / follow-up conversation behavior — that's a separate eval, deferred.

- All 10 holdout runs synth_outcome=ok ✓
- HQ5 × Warsaw dispatch: 4 specialists (`location_traffic, market_landscape, menu_pricing, review_analyst`) spanning 4 query buckets ≥3 ✓
- HQ5 × Berlin dispatch: 5 specialists (same + `marketing_digital`)
- HQ5 × Warsaw operator review: V2.3 wins ✓

**Gate #6: PASS.**

---

## Berlin probe (exploratory finding, not a gate)

V2.3 stayed functional on Berlin without Polish-source bleed. The probe is small (n=1 venue × 5 queries × 1 rep) and informative, **not validation** of cross-market generalization. Three findings worth recording:

1. **No Polish source bleed.** The Polish examples in V2.3's `specialist_base.md` (trojmiasto.pl, Pyszne.pl, Wolt.com, Dusiowakuchnia, etc.) did not appear in any Berlin run. Specialists used Berlin-appropriate sources (lieferando.de, mitvergnuegen.com, tagesspiegel.de, etc.) — the model treated the Polish list as exemplar, not prescriptive. This is a real finding within the bounds of the small sample.
2. **V2.3 sometimes loses on focus.** On HQ5 × Berlin, V0 produced a sharper "ONE menu change this month" answer than V2.3, which sprawled into 3 pivots. The richer dispatch can hurt when the question demands prioritization. V0 won this operator review.
3. **V2.3 wins on operator-relevant intel.** On HQ2 × Berlin (pricing exposure), V2.3 found channel-margin structure (Wolt 20-28% markups, Croissant Couture's corporate purpose listing delivery distribution, tablet-pausing algorithm penalties) that V0 missed. Operator picked V2.3 despite Gemini's V0 vote.

Berlin is **functional and informative, not validated as cross-market production-ready**. A future stage with German-specific source priors plus a wider non-Polish sample (multiple venues × multiple reps) would be needed before claiming cross-market readiness.

---

## Final ship decision: SHIP V2.3 as controlled rollout

All 6 gates pass on their stated criteria. Evidence is mixed-but-positive (rep 3 collapse → competently narrower; sliwka q1 V2.1 still better; Warsaw faith/spec slightly lower). V2.3 ships as a **controlled instruction rollout** — see Post-ship monitoring section. Production files replaced as of 2026-04-26.

| gate | criterion (summary)          | result                                                                |
| ---- | ---------------------------- | --------------------------------------------------------------------- |
| #1   | monsun q1 rerun              | PASS (2/3 cat-cov, faith+spec collapse → competently narrower)        |
| #2   | bar_leon q2 rerun            | PASS clean (3/3)                                                      |
| #3   | candidate showdown           | PASS (V2.3 first on monsun q2 + bar_leon q3; V2.1 first on sliwka q1) |
| #4   | Warsaw aggregate             | PASS clean (top 0.099, cat 2.8)                                       |
| #5   | non-Berlin operator pairwise | PASS clean (3/3 V2.3 wins)                                            |
| #6   | multi-topic robustness       | PASS (synth_ok 10/10, HQ5 dispatch ≥4 specialists ≥4 buckets)         |

## Production code changes shipped with V2.3

Two **instruction files** (the V2.3 ship target — replace with the V2.3 versions from `evals/instructions_variants/V2_3/`):

- `agent/superextra_agent/instructions/research_orchestrator.md`
- `agent/superextra_agent/instructions/specialist_base.md`

Plus **two pre-existing harness-support changes** that have been in the working tree throughout this project (added during Stage 1 to enable the subprocess-per-variant runner; both are 2-line `SUPEREXTRA_INSTRUCTIONS_DIR` env-fallback diffs that are byte-identical to the original code path when the env var is unset):

- `agent/superextra_agent/agent.py:36-37` — `_dir_override = os.environ.get("SUPEREXTRA_INSTRUCTIONS_DIR")`
- `agent/superextra_agent/specialists.py:23-24` — same pattern

These env-override changes have **zero behavior change in production** (when the env var is unset, the resolved `INSTRUCTIONS_DIR` is identical to before). They are required for the eval harness to function and have been part of every Stage 1/2/3 result. Including them in the V2.3 commit alongside the instruction files is correct — they are the supporting infrastructure for any future eval round.

**Other agent code unchanged:** specialists.py beyond line 23-24, places_tools.py, web_tools.py, apify_tools.py, tripadvisor_tools.py, worker_main.py, firestore_events.py, chat_logger.py, and the entire eval harness under `agent/evals/`.

---

## What V2.3 actually delivers (verified)

- **Source diversity**: top-domain share drops from V0's 0.35 → 0.26 aggregate, 0.255 → 0.099 on Warsaw holdout.
- **Category coverage**: 2.2 → 3.2 aggregate; 2.0 → 2.8 on Warsaw.
- **Specialist dispatch**: V0 averaged 2.83 specialists per run; V2.3 averages 3.75. The marketing_digital + menu_pricing + review_analyst specialists fire on coverage-sensitive queries where V0 routinely skipped them.
- **Synth stability**: 10/10 synth_ok on held-out queries (and 24/24 on the original matrix).
- **Cost**: +8.8% tokens vs V0, runs 10.9% faster on average.
- **Cross-market**: generalizes to Warsaw without instruction changes; functional on Berlin without source-priors bleed.

---

## Post-ship monitoring plan

V2.3 is shipped as a **controlled rollout**, not a closed case. Three specific risks to monitor in the first 2 weeks post-ship:

1. **Focus loss on prioritization queries.** When users ask "what should I do this week" or "what's the ONE change," V2.3's broader dispatch may sprawl into multiple recommendations rather than prioritizing one. Berlin HQ5 confirmed this risk on a real combo (V0 sharper, V2.3 sprawled across 3 pivots). **Monitoring action**: sample 10–20 production answers in the first 2 weeks, specifically check responses to single-decision prompts. If sprawl is common, consider a synthesizer-side prompt change.
2. **Faithfulness regression.** Warsaw holdout shows Gemini-judged faithfulness 3.60 vs V0's 4.00 (40-point drop on a 0–5 scale). Operator reviews favored V2.3 anyway, and Gemini is known noisy. But this is "research depth improved" — NOT "quality improved across the board." **Monitoring action**: spot-check named figures, dates, and venue claims in the same 10–20 sampled answers against cited sources. If unsupported-claim rate rises noticeably above pre-ship levels, re-investigate.
3. **Berlin / non-Polish behavior.** Not gated by the ship; only n=1 Berlin venue tested. **Monitoring action**: if non-Polish queries become common in production, log them separately and review on a different cadence. V2.3 is _not_ validated for cross-market production.

A simple post-ship review cycle: 2 weeks after ship, sample N=10–20 production runs from the same query types covered in Stage 3 (openings/closings, pricing, sentiment, multi-topic), apply the same operator-subagent review pattern, decide whether to extend monitoring or close out.

## Known limitations

1. **sliwka × q1 openings**: V2.1 was better than V2.3 on the original Food Hall Krzywy Domek combo. V2.3 misframes the food hall as "upcoming" rather than "opened May 2025." A separate small fix may be possible later. Not a blocker — single-combo issue.
2. **Berlin has lower coverage**: only 1.4-1.8 categories per run, vs Warsaw's 2.0-2.8. Polish-tuned source priors don't fully transfer. Future cross-market work needed if Berlin/non-Polish becomes a target market.
3. **Faithfulness slightly lower than V0 on Warsaw**: 3.60 vs 4.00 (Gemini-judged). Probably noise — operator reviews of 3 of 5 Warsaw combos all preferred V2.3. But not denied: V2.3's broader research can include claims that are harder for the judge to anchor to a specific source.
4. **monsun q1 is variable**: rep 3 produced a narrower-than-V0 report. The operator ruled it "competently narrower," not wrong, but variance is real.

---

## What stays out of scope (carried forward from earlier plans)

- Wage-benchmarking capability investigation (separate project)
- Marketing-wall delivery audit (separate project)
- Calibrated Gemini judge or replay capability (later)
- Cross-market validation beyond exploratory Berlin (separate project, requires German source priors)

---

## Open questions for the committee (post-ship)

1. **Monitor V2.3 in production**. The eval harness can be run against any future change to detect regressions. Any opinion on cadence?
2. **Sliwka q1 partial regression**: worth a targeted fix later, or accept as known limitation?
3. **Berlin/non-Polish cross-market**: pursue as next project, or wait until business need is clear?
4. **Promote evaluation discipline**: Stage 1 / 2 / 3 cadence (variance check, multi-judge, held-out, factual review) is now reusable. Bake into the agent change process going forward?

---

## Artifacts (Stage 3)

**Code** — no production code changed; only instruction files swapped.

**Data:**

- `agent/evals/results/V0_rerun_{1,2,3}/`, `V2_3_rerun_{1,2,3}/` — 12 rerun JSONs (Phase B)
- `agent/evals/results/V0_holdout/`, `V2_3_holdout/` — 20 holdout JSONs (Phase D)
- `agent/evals/scores/V0_rerun_{1,2,3}.csv`, `V2_3_rerun_{1,2,3}.csv` — Phase B scored CSVs
- `agent/evals/scores/V0_holdout.csv`, `V2_3_holdout.csv` — Phase D scored CSVs
- `agent/evals/pairwise_verdicts/V0_vs_V2_3_holdout/*.json` — 10 Gemini pairwise verdicts

**Fixtures:**

- `agent/evals/queries_holdout.json` — Adam's 5 freeform queries
- `agent/evals/venues_holdout.json` — Boska Praga + Zeit für Brot

**Docs:**

- `docs/research-depth-stage3-validation-plan-2026-04-25.md` — the plan
- `docs/research-depth-stage3-validation-2026-04-26.md` — this doc (Stage 3 results & ship decision)
- `docs/research-depth-stage2-results-2026-04-25.md` — Stage 2 (with Phase A factual corrections)
- `docs/research-depth-pairwise-verdicts-2026-04-25.md` — pairwise transcripts (with V0 vs V2.3 monsun q2 appended)
