# Next-stage test plan — research depth

Period: 2026-04-25 onwards. Author: Claude (in session with Adam).
Status: **draft for committee review.**

This plan extends the work documented in `research-depth-final-report-2026-04-25.md`. The current ship candidate is V2.1 with a known partial regression on `monsun × q2_closures_lessons`. The committee has authorized additional testing cycles before promotion. This document inventories what's worth testing, ranks by value × cost, recommends a default path, and flags decisions the committee should make.

---

## Summary

Five tiers of additional work, ranging from "ship-blocker fix" to "follow-up project." Recommended default path: **Tier 1 + Tier 2** (~5 hours of compute, 1 calendar day if run sequentially, half a day if parallelized), which gives the committee a clean ship decision plus tests two high-value variant extensions and one robustness test.

If the committee wants maximum confidence: **Tier 1–4** (~12 hours of compute, ~2 calendar days). Tier 5 is a separate scoping exercise.

---

## Goals for the next stage

By the end of testing, the committee should be able to answer:

1. **Can we ship V2.x cleanly?** The monsun q2 regression is the one outstanding risk; we test V2.2 to address it.
2. **Are V1's good ideas worth porting?** V1 alone underperformed; V3 (V1 + V2) was destructive. We don't know whether V1's source-prior framing is _fundamentally_ a regression or just regressed because of V1's verification-discipline rule. Worth isolating.
3. **Does V2.1 hold up on edge cases?** Multi-topic queries, follow-up turns, and non-Tricity venues stress-test the orchestration's robustness.
4. **What's the run-to-run variance of the harness itself?** We've been treating single runs as ground truth; we don't know the noise floor.
5. **Where is the dispatch rule incomplete?** The Monsun q2 case showed `review_analyst` should arguably be in the closures rule. Other rules may have similar gaps.

---

## Tier 1 — Ship-clarity tests (highest priority)

### 1A. V2.2 — V2.1 + `review_analyst` in closures rule

**Hypothesis.** Adding `review_analyst` to the openings/closings + closures-lessons coverage rule will fix the monsun q2 regression (where V2.1 lost V2's free `review_analyst` dispatch and dropped the most actionable finding) without introducing new regressions elsewhere.

**Change.** Edit `instructions_variants/V2_2/research_orchestrator.md`. The closures rule line becomes:

> _"Openings/closings questions — MUST include `market_landscape` + `menu_pricing` + `marketing_digital` + `review_analyst`."_

**Run.** 24-combo matrix (3 venues × 8 queries), ~70 min wall-clock.

**Pairwise.**

- `monsun × q2_closures_lessons` (the regression case — does V2.2 fix it?)
- `bar_leon × q2_closures_lessons` (no-regression check on different venue)
- `sliwka × q2_closures_lessons` (no-regression check on third venue)
- `sliwka × q1_openings_closings` (does the Food Hall fix still hold with extra specialist?)
- `monsun × q1_openings_closings` (does Bambus Grill finding still surface?)

5 pairwise calls × ~1 min = ~5 min.

**Decision criteria.**

- V2.2 wins or ties V2.1 on monsun q2 → proceed; new ship candidate.
- V2.2 doesn't fix monsun q2 → V2.1 stays the recommendation; investigate why.
- V2.2 introduces new regression elsewhere → reconsider; possibly the closures rule shouldn't be touched.

**Cost.** ~75 min compute, ~10 min analysis.

### 1B. Repeat-run variance check

**Hypothesis.** Single runs may be noisy enough that some of V2.1's "wins" and "losses" are sampling variance, not real differences.

**Change.** None. Re-run V2.1 on the 3 primary-probe queries × 3 venues = 9 combos, **3 times each** (using `--force` to overwrite existing). 27 fresh runs.

**Analysis.** Compute std dev of top-domain share, category coverage, drawer source count per combo. If std dev is high, single-run pairwise verdicts are weak signal.

**Cost.** 27 runs × ~3 min = ~80 min compute.

**Decision criteria.**

- σ < 0.05 on top-domain share → harness is stable; trust single runs.
- 0.05 ≤ σ ≤ 0.15 → moderate noise; require ≥3 wins out of 5 pairwise to call a difference real.
- σ > 0.15 → harness too noisy; evals need 3-run averages going forward.

**Why important.** Without this, we don't actually know how confident to be in any pairwise result. The committee should know.

---

## Tier 2 — High-value next variants

### 2A. V2.3 — V2.2 + V1's "good" source-framing (no verification-discipline rule)

**Hypothesis.** V1's two genuinely good ideas — explicit municipal-authority callout and explicit culinary-blog acknowledgement — can be added to V2.2's foundation without the destructive verification-discipline rule that hurt V3.

**Change.** Take V1's `specialist_base.md`, **remove the "Verification discipline" section** (the one with "if you can't find a source, omit the specific" rule), keep:

- Municipal & city-authority sources callout (the ZDiZ Gdynia / www.gdynia.pl framing the user explicitly asked to encourage)
- Culinary blogs as legitimate primary sources (the rewording targeting content-farms not blogs in general)
- Source-diversity self-audit ("after first round, check if results cluster")

Combine with V2.2's orchestrator file in `instructions_variants/V2_3/`.

**Run.** 24-combo matrix.

**Pairwise.**

- `monsun × q1_openings_closings` (does the municipal-authority callout produce more zdiz.gdynia.pl-class sources?)
- `bar_leon × q3_pricing` (no-regression check)
- `sliwka × q2_closures_lessons` (does the culinary-blog framing help low-data venue?)
- `sliwka × q4_sentiment_themes` (the V2.1 loss case — does V2.3 help?)

**Decision criteria.**

- V2.3 wins or ties V2.2 on aggregates → V2.3 ships instead.
- V2.3 regresses → V2.2 stays; V1's source-framing is genuinely just a wash.

**Cost.** ~75 min compute, ~10 min analysis.

### 2B. Multi-topic query test

**Hypothesis.** Real customer queries often span buckets ("how do my prices compare AND who's opening?"). V2.1's coverage rules trigger on a single query type — the orchestrator might pick rules from one bucket and ignore the other.

**Change.** Add 2 multi-topic queries to a test fixture (don't replace queries.json):

- _"How do my prices compare to nearby competitors and what's opening or closing in my area?"_
- _"What are guests saying about us and how does our pricing compare?"_

Run 2 queries × 3 venues × {V0, V2.1, V2.2} = 18 runs.

**Pairwise.**

- 2 V0 vs V2.2 comparisons on the multi-topic queries

**Decision criteria.**

- V2.2 union-dispatches both rules' specialists → robust framing.
- V2.2 picks one bucket's rule, ignores the other → orchestrator instruction needs explicit "multi-topic queries should union the rules" language.

**Cost.** 18 runs × ~3 min = ~55 min, ~10 min analysis.

---

## Tier 3 — Process improvements (parallel work, no compute cost)

### 3A. Scripted pairwise judging in the harness

**Why.** Pairwise verdicts are currently session-ephemeral or manually transcribed. Reviewer flagged this as under-artifacted.

**Change.** Build `agent/evals/pairwise.py`:

- Inputs: two run JSONs (variant_a, variant_b), venue context, optional WebFetch budget
- Calls Anthropic API directly (not via Claude Code subagent — this is for unattended runs)
- Captures: prompt, full verdict text, structured `winner: "A" | "B" | "TIE"`, supporting URLs
- Output: JSON file alongside run results

**Cost.** ~100 lines of code. ~30-45 min to write + test.

**Why it matters.** Lets us run pairwise on every variant change at scale instead of cherry-picking.

### 3B. Replay capability

**Why.** Currently re-scoring with a different rubric requires re-running the agent (~3 min/run × 24). If we capture raw events to disk, re-scoring is seconds.

**Change.** Modify `run_matrix.py` to also serialize raw ADK events (not just parsed) to `<run>.events.jsonl`. Modify `parse_events.py` to optionally read from a file instead of a live stream.

**Cost.** ~15-30 min implementation.

### 3C. Document V2.x rules in `instructions/AUTHORING.md`

**Why.** Future contributors will edit `research_orchestrator.md` and may not realize the additive-floor framing is load-bearing. Mention in the existing authoring doc.

**Cost.** ~10 min, no compute.

---

## Tier 4 — Robustness and generalization tests

### 4A. Followup-query test

**Hypothesis.** V2.1's coverage rules apply to first-turn queries. The production agent supports follow-up turns via the `follow_up` specialist (no tools, just rephrases the existing report). We don't know how V2.1 affects multi-turn conversations.

**Change.** Define a 2-turn fixture:

- Turn 1: _"What has opened or closed in my area recently?"_ (triggers V2.1 dispatch rule)
- Turn 2: _"Tell me more about [specific competitor mentioned in turn 1]"_ (typically routes to follow_up)

Run on V0 and V2.1, 3 venues × 2 turns × 2 variants = 12 runs.

**What to look for.** Does turn 2 inherit the depth from turn 1's V2.1-mandated specialists, or does it degrade? Does the orchestrator re-trigger if the follow-up hints at a different angle?

**Cost.** ~40 min compute + ~15 min analysis.

### 4B. Non-Tricity Polish market test

**Why.** All testing has been Tricity. The orchestration changes are domain-general but the source taxonomy is Poland-tuned. A Warsaw or Kraków venue tests generalization without changing language/country.

**Change.** Pick 2 Warsaw and 2 Kraków venues we have rough ground truth on (or can verify via WebFetch). Run primary probes (q1, q2, q3) only. 4 venues × 3 queries × 2 variants (V0 vs V2.2) = 24 runs.

**Pairwise.** 4 selected combos.

**Cost.** ~75 min compute + ~15 min analysis + ~30 min venue selection.

### 4C. Non-Polish market test

**Why.** Highest knowledge value. Tests whether the dispatch rules generalize when the source taxonomy must be re-tuned (different press landscape, different delivery platforms).

**Change.** Pick 2 Berlin venues (Handelsregister is on the marketing wall, German press is well-indexed). Add German-specific source taxonomy notes to V2.x's `specialist_base.md`. Run primary probes.

**Cost.** ~90 min compute + ~30 min source-taxonomy authoring + ~30 min venue/ground-truth setup.

**Note.** This is the most cross-cutting test. If V2.x generalizes here, the dispatch thesis is robust beyond the Polish market.

---

## Tier 5 — Methodology investigations (separate project scope)

### 5A. Specialist-isolation test

**Why.** We've been measuring full pipeline output. We don't know whether degraded specialists are the cause of weak outputs, or whether the synthesizer is collapsing breadth that the specialists actually had.

**Change.** Run individual specialists with synthetic briefs (already supported by the existing `_make_specialist` plumbing — would need a small driver). Compare specialist's standalone output to its in-pipeline contribution.

**Cost.** ~2-3 hours setup + 30 min runs. Significant.

### 5B. Calibrated Gemini judge

**Why.** The Gemini judge is unreliable but cheap. If we calibrated it against ~20 human-labeled outputs, it might become useful as a CI gate.

**Change.** Manually label 20 reports across V0/V2.1 along all four rubric dimensions. Compare against Gemini's scores. If correlation is reasonable, refine rubric and re-test.

**Cost.** ~3-4 hours human time (the user, presumably) + harness updates.

---

## Tier 6 — Capability investigations (out of current project scope, flagged for future)

### 6A. Wage-benchmarking capability

The reviewer correctly identified this as a tool gap, not a prompt gap. Would need a Polish-restaurant wage data source (scrape pracuj.pl? CEIDG? buy a dataset?). Separate project.

### 6B. Marketing-wall delivery audit

Each of 29 brands needs an answer: "what would the agent need to actually reach this source?" Some are reachable today via fetch_web_content (Wolt, TripAdvisor); others need API access (Statista, NielsenIQ paywalled); some are dataset-tier (Eurostat APIs exist but are dense). Inventory exercise. Separate project.

---

## Recommended paths

### Path A — minimum viable next stage (~3 hours compute + analysis)

**Tier 1A** (V2.2) + **Tier 1B** (variance check). Gives us: (a) a probable ship-fix, (b) confidence intervals on the harness itself.

### Path B — default recommendation (~5 hours compute + analysis)

Path A + **Tier 2A** (V2.3) + **Tier 3A** (scripted pairwise harness — happens in parallel with compute). Adds: a tested V1-port and a reusable pairwise pipeline.

### Path C — high-confidence stage (~12 hours compute + analysis, 2 calendar days)

Path B + **Tier 2B** (multi-topic queries) + **Tier 4A** (followup test) + **Tier 4B** (non-Tricity Polish). Adds: edge-case robustness and same-language generalization.

### Path D — comprehensive (~20+ hours compute, 3-4 calendar days)

Path C + **Tier 4C** (Berlin generalization) + **Tier 5A** (specialist isolation). Adds: cross-market generalization, deeper diagnosis of where breadth is lost.

---

## Decisions for the committee

1. **Which path?** A, B, C, or D?
2. **Variance check (1B)** — should we do this regardless of path? Strongly recommended; clarifies whether previous wins/losses are real.
3. **Scripted pairwise harness (3A)** — should we build it now or defer to next quarter? It's small but unlocks scale.
4. **Berlin/non-Polish test (4C)** — committee priority? Highest knowledge value but also highest setup cost.
5. **Wage-benchmarking + marketing-wall audit (Tier 6)** — should these be scoped as separate projects now, or revisited later?

---

## Risks and mitigation

| risk                                                                             | likelihood | mitigation                                                                                                                         |
| -------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| V2.2 doesn't fix monsun q2 (review_analyst is dropped despite being in the rule) | low-med    | Path A surfaces this immediately; we'd inspect dispatch behavior and consider why "MUST include" isn't being honored on this combo |
| V2.3 reintroduces V3-style destructive interaction                               | low-med    | Test isolates V1's source-framing from V1's verification-discipline rule, the suspected culprit                                    |
| Variance test (1B) shows σ > 0.15 — harness too noisy                            | low        | If true, all prior pairwise verdicts need re-running with 3-run averages; would be a major finding worth knowing                   |
| Multi-topic test (2B) reveals orchestrator can't union rules                     | medium     | Adds explicit "multi-topic queries union all applicable rules" language to V2.x; cheap fix                                         |
| Berlin test (4C) reveals dispatch thesis is Poland-specific                      | medium     | Real possibility; would reframe the project's contribution as Polish-market-tuning, not domain-general                             |
| Compute budget is 1.5x my estimates due to model latency                         | medium     | Re-baseline timing on first V2.2 run, adjust                                                                                       |

---

## What stays out of scope

- More variants without a hypothesis (no random V2.4, V2.5 exploration)
- Tool-level changes (those are Tier 6)
- Architectural changes to the agent pipeline (router, gap researcher, synthesizer fallback) — different project
- Model upgrades / Gemini snapshot changes — would invalidate our V0 baseline
- UX-level changes to the chat interface — this is an agent quality project, not a UX project

---

## What we'd need to start

If committee approves Path B (default):

- Confirmation to proceed
- ~5 hours of my time (mostly compute idle while runs happen) over 1 day

If committee approves Path C:

- 4 venue picks for non-Tricity test (2 Warsaw, 2 Kraków)
- Same-day operator-style ground truth from someone who knows those markets, OR willingness to live with WebFetch-based verification only
- ~12 hours compute, ~2 calendar days

If committee approves Path D + non-Polish:

- 2 Berlin venue picks
- ~30 min from someone with German-restaurant-market context to flag glaring source-taxonomy gaps
- ~20 hours compute, ~3-4 calendar days

---

## Artifacts on completion

For whichever path is approved, deliverables will include:

- **New variant directories** (e.g., `instructions_variants/V2_2/`, `V2_3/`)
- **Result JSONs** under `evals/results/<variant>/`
- **Scored CSVs** under `evals/scores/`
- **Pairwise verdict transcripts** appended to `docs/research-depth-pairwise-verdicts-2026-04-25.md`
- **Updated final report** reflecting any changes to ship recommendation
- **(if 3A done)** `agent/evals/pairwise.py` as a reusable component
- **(if 4B/4C done)** Country-specific source taxonomy additions in instruction overlays

The eval harness should remain green (deterministic + judge passes) on every shipped variant.
