# Research-depth project — final report

Period: 2026-04-23 to 2026-04-25.
Author: Claude (in session with Adam).
Scope: prompt-and-orchestration changes to the Superextra agent pipeline aimed at improving research depth and coverage on real customer queries.
Status: V2.1 is the recommended ship candidate. Awaiting committee review.

---

## TL;DR

A single PM complaint — _"the agent only cites trojmiasto.pl, where are the delivery platforms?"_ — turned into a three-day rebuild of how we evaluate and tune the agent. We:

- Built an end-to-end **eval harness** (subprocess-per-variant runner + ADK event parser + deterministic scorer + Gemini judge) and ran it against 24 query × venue combinations.
- Tested **four prompt variants** (V0 baseline, V1 specialist soft-priors, V2 orchestrator coverage rules, V3 V1+V2 combined, then V2.1 a refined V2).
- Discovered that **specialist dispatch is the highest-leverage knob** — V2 changed which specialists ran on which query types, and the resulting reports were materially better.
- Discovered that **the Gemini-as-judge approach is too noisy** to drive ship decisions; **Claude operator-role subagents** turned out to be the only reliable judging mechanism.
- Recommend **shipping V2.1 as a controlled improvement** — orchestrator-only change, **4 wins / 2 losses across 6 pairwise comparisons** against V0, faster runs, fewer tokens, better deterministic metrics on every aggregate dimension. One pairwise loss is on a targeted query type (`monsun × q2_closures_lessons`) where V2.1 lost V2's free `review_analyst` dispatch — a known, bounded regression worth disclosing to the committee, not a blocker.

The artifacts (eval harness, variant overlay system, scoring CSVs, run logs, three intermediate reports) are committed to the repo and reusable for any future prompt change.

---

## The trigger

A user-facing chat session for **Monsun Gdynia** answering _"What has opened or closed in my area recently?"_ produced a report whose sources drawer cited 8× trojmiasto.pl, 1× ubereats.com, 1× orlygastronomii.pl. The PM read it as monoculture: _"the agent should cross-check delivery platforms, Google Maps, booking sites, social — not lean on one local portal."_

This kicked off the question: is the actual problem source breadth, or something else? And how would we even know without measuring?

---

## Methodology

### Test-drive before the formal harness

Before designing anything, we re-ran the same query against a different Tricity venue (Bar Leon, Gdańsk) on the live production agent. The deltas were striking:

|                       | Monsun (2026-04-15) | Bar Leon (2026-04-24)      |
| --------------------- | ------------------- | -------------------------- |
| Sources cited         | 10                  | 18                         |
| Top-domain share      | 80%                 | 56%                        |
| Category coverage     | 1–2                 | 4–5                        |
| Google Maps in drawer | No                  | **Yes**                    |
| Real-estate sources   | None                | otodom×2, m2bomber, others |

**Two findings shaped the rest of the project:**

1. **Venue variance is a first-order effect** — same code, same query, dramatically different output. A single-venue eval would mislead.
2. **The codebase had moved between the two sessions** — commit `98ee238 feat(sources): one provider pill per API` shipped Google Maps source attribution. The Monsun result was historical, not a fair V0 baseline. We re-baselined.

### Eval harness design

The eval needed to capture more than the user-visible sources drawer because **`sources[]` is the UI drawer, not the research evidence set**. Discovered while reading `worker_main.py:928-1143`: the drawer only holds grounding-metadata URLs and provider-tool pills. Arbitrary `fetch_web_content()` calls are tool activity that never reaches the drawer unless they also came back through grounding. So computing diversity metrics from `sources[]` alone systematically under-counts research breadth.

Solution: capture the raw ADK event stream per run and build the real evidence set from `{grounding URLs} ∪ {fetch_web_content URLs} ∪ {provider pills}`. Phase 1 evidence (everything specialists touched) plus Final evidence (the drawer). The two-layer view shows where diversity drops — specialists vs synthesizer.

**Components built (all in `agent/evals/`):**

- `parse_events.py` — extracts grounding entries (with real `web.domain` not redirect URLs), fetched URLs, provider pills, `gap_ran`, `synth_outcome`, specialist dispatch, token totals from raw ADK events.
- `run_matrix.py` — subprocess-per-variant runner. Parent builds a temp instructions overlay (default tree + variant-specific overrides) and spawns a child with `SUPEREXTRA_INSTRUCTIONS_DIR` env override. **Zero production code change** beyond a single env-var fallback line in `specialists.py` and `agent.py`.
- `score.py` — deterministic metrics (top-domain share, unique domains, 8-category coverage, marketing-wall overlap with Google Maps auto-write excluded, provider presence, specialists dispatched, runtime, tokens, tool-call counts) on both Phase 1 and Final sets, plus Gemini-as-judge rubric scoring.
- `summarize.py` — reads scored CSV, prints aggregate / per-venue / primary-probe blocks, flags degenerate runs.
- `judge_rubric.md` — four-dimension rubric (faithfulness, completeness, specificity, investigative stance) anchored 0–5.
- `instructions_variants/<V*>/` — per-variant overlay files that get layered on top of the default `instructions/` tree per run.

### Test query set

Eight queries pulled directly from the production chat UI's pill suggestions (`TopicPills.svelte`) — one per pill color category. Three are **primary failure-mode probes** (the original openings/closings, plus closures-lessons and price-comparison). Five are general spread to detect regressions on non-targeted queries.

### Three Tricity venues

- **Monsun**, Świętojańska, Gdynia — high-street retail context
- **Bar Leon**, Stągiewna, Gdańsk — touristy island ("Booking Island")
- **Śliwka w Kompot**, Sopot — resort-town, low-data, summer-seasonal

### Source taxonomy (8 categories)

Grounded in the production landing-page's _"Only credible data sources"_ wall plus Polish-specific knowledge:

1. **Community discussion** — trojmiasto.pl forums, Reddit, Wykop
2. **Local press** — gdynia.naszemiasto.pl, gdansk.naszemiasto.pl, wyborcza.pl, dziennikbaltycki.pl, radiogdansk.pl
3. **Industry sites & reports** — horecatrends.pl, orlygastronomii.pl, foodie.pl, Statista, NielsenIQ
4. **Influencers & blogs** — Polish food bloggers (Dusiowakuchnia, etc.), Instagram, TikTok
5. **Consumer platforms** — Google Maps, Pyszne.pl, Wolt, Glovo, Bolt Food, Uber Eats, TripAdvisor, TheFork
6. **Venue's own channels** — restaurant website, official social, menu PDFs
7. **Official registries & statistics** — CEIDG, KRS, REGON, GUS, Eurostat
8. **Commercial listings & marketplaces** — otodom, gratka, m2bomber, olx

Categories 7 and 8 were split (originally one bucket) after the V0 baseline showed that one OTODOM listing shouldn't count as much as a CEIDG record.

### Multi-judge approach

The Gemini judge produced wildly noisy faithfulness scores — gave faith=0 to a Sopot pricing report where the agent had verifiably fetched real menus, gave faith=5 to a Monsun report we later showed had fabricated "Beggin registered March 4 per CEIDG" claims. The judge also showed obvious rubric bias on `investigative_stance`: 114 of 120 runs across all five variants got 5/5 (95%) — most discrimination came only from V3 and V2.1, where 6 runs scored below 5. **The Gemini judge could not be trusted at the resolution we needed.**

We pivoted to **Claude subagents as operator-role judges**: each subagent plays the role of a restaurant operator (with the venue's actual context — name, location, vibe), reads the report, has WebFetch to verify cited claims against live URLs, and renders an actionability-focused verdict. This worked. Operators caught fabrications the Gemini judge missed and validated improvements the Gemini judge ranked as regressions.

For multi-variant comparisons, we used **pairwise judging** rather than absolute scoring. Pairwise A/B is more reliable than 0–5 rubric scoring per Anthropic's published research-system experience.

---

## Variants tested

| variant  | what it changes                                                                                                                                                                                            | where                      |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| **V0**   | nothing — current production                                                                                                                                                                               | baseline                   |
| **V1**   | specialist soft-priors: 8 source categories with examples (incl. municipal authority, culinary blogs explicitly NOT discouraged), plus "verification discipline" rule (no fabricated specifics)            | `specialist_base.md`       |
| **V2**   | orchestrator query-type coverage rules: openings/closings MUST dispatch market_landscape + menu_pricing + marketing_digital; pricing MUST dispatch menu_pricing + review_analyst + marketing_digital; etc. | `research_orchestrator.md` |
| **V3**   | V1 + V2 combined                                                                                                                                                                                           | both files                 |
| **V2.1** | V2 with "MUST include" (additive) instead of "MUST dispatch" (substitutive) — orchestrator may keep its own picks alongside the floor                                                                      | `research_orchestrator.md` |

Each variant was run end-to-end across 24 query × venue combinations, all on Gemini 3.1 Pro Preview via the production agent code with instruction-file overlays.

---

## Results

### Aggregate scorecard

| metric                   | V0    | V1    | V2    | V3    | **V2.1** |
| ------------------------ | ----- | ----- | ----- | ----- | -------- |
| synth_ok                 | 24/24 | 24/24 | 24/24 | 24/24 | 24/24    |
| top-domain share (final) | 0.35  | 0.38  | 0.35  | 0.39  | **0.33** |
| category coverage / 8    | 2.2   | 2.0   | 2.1   | 2.2   | **2.8**  |
| wall-brand overlap / 29  | 0.5   | 0.3   | 0.7   | 0.5   | **0.9**  |
| specificity (judge)      | 3.08  | 2.88  | 3.17  | 2.96  | **3.21** |
| tokens (avg, k)          | 170   | 188   | 172   | 165   | **163**  |
| elapsed (avg, s)         | 275   | 241   | 228   | 213   | **209**  |

V2.1 wins or ties on every dimension, including cost.

### Primary-probe scorecard (q1 openings/closings, q2 closures, q3 pricing)

| metric             | V0   | V1   | V2   | V3   | **V2.1** |
| ------------------ | ---- | ---- | ---- | ---- | -------- |
| top-domain share   | 0.33 | 0.44 | 0.33 | 0.41 | **0.27** |
| category coverage  | 2.2  | 1.9  | 2.7  | 1.4  | 2.7      |
| wall-brand overlap | 0.3  | 0.6  | 1.3  | 0.8  | 1.0      |
| specificity        | 2.78 | 3.33 | 3.11 | 3.11 | 2.78     |

On the queries we explicitly targeted, V2.1 has the lowest top-domain share (best diversity), retains V2's category-coverage gains, and runs faster than V0.

### Pairwise verdicts (operator-role Claude subagents)

Full transcripts at `docs/research-depth-pairwise-verdicts-2026-04-25.md`.

| comparison       | venue    | query        | verdict               | what mattered                                                                                                                                                                                                                                                                                                               |
| ---------------- | -------- | ------------ | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| V0 vs V2         | monsun   | q1 openings  | V2                    | V2 surfaced Bambus Grill Wolt promos, V0's CEIDG claim unverifiable                                                                                                                                                                                                                                                         |
| V0 vs V2         | bar_leon | q1 openings  | V2                    | V0's "56k PLN/100m² per Prestiż" failed verification (real ~18-25k); V2 self-corrected mid-report                                                                                                                                                                                                                           |
| V0 vs V2         | sliwka   | q1 openings  | **V0**                | V2 missed Food Hall Krzywy Domek (200-seat, 100m away) — disqualifying                                                                                                                                                                                                                                                      |
| V2 vs V2.1       | sliwka   | q1 openings  | V2.1                  | V2.1 explicitly catches Food Hall Krzywy Domek — fix verified                                                                                                                                                                                                                                                               |
| V0 vs V2.1       | monsun   | q1 openings  | V2.1                  | retained V2's Bambus Grill / delivery-platform gains                                                                                                                                                                                                                                                                        |
| V0 vs V2.1       | bar_leon | q1 openings  | V2.1                  | caught Cloud One hotel at Stągiewna 27 (next door, 327 rooms) which V0 missed entirely                                                                                                                                                                                                                                      |
| V0 vs V2.1       | bar_leon | q3 pricing   | V2.1                  | marketing_digital surfaced Woosabi's 12-16 Bao Set lunch promo + 0% review-response rate gap                                                                                                                                                                                                                                |
| V0 vs V2.1       | sliwka   | q4 sentiment | **V0**                | non-targeted query; V2.1 missed the "no modifications" kitchen-rigidity finding                                                                                                                                                                                                                                             |
| V0 vs V2 vs V2.1 | monsun   | q2 closures  | **V2.1 ranked worst** | regression check on a targeted query — V2.1 dropped to 1 category / 61.5% top-domain share; V2 freely added `review_analyst` and caught Monsun's own defensive-response review pattern (most actionable finding); V2.1's coverage rule didn't include review_analyst for closures and the orchestrator didn't add it freely |

**V2.1 cumulative: 4 wins, 2 losses.** One loss on a non-targeted query (sentiment), one loss on a targeted query (closures — bounded but real). See the next section for the monsun q2 regression analysis.

---

## Insights

### Specialist dispatch is the highest-leverage knob

The single biggest finding of the project: **the orchestrator's choice of which specialists to dispatch matters more than how the specialists are instructed.** V0 never dispatched `menu_pricing` or `marketing_digital` for any openings/closings query across any venue. V2 forced those dispatches and the resulting reports systematically surfaced delivery-platform listings, social-channel announcements, and price intelligence that V0 was structurally blind to.

The Bambus Grill discovery for Monsun is a clean example: a direct pan-Asian competitor on Świętojańska, with a Wolt-only distribution, 25 PLN Express Box undercutting the lunch market, and 15 PLN acquisition discounts — none of which V0's `{guest_intelligence, location_traffic, market_landscape}` dispatch ever found. V2.1's `{market_landscape, marketing_digital, menu_pricing, location_traffic}` did.

### V1 (soft-priors only) was a mild regression

V1 changed `specialist_base.md` to give specialists a soft-prior list of source types and a verification-discipline rule. On primary probes, V1's top-domain share went _up_ (0.44 vs V0's 0.33) and category coverage went _down_ (1.9 vs V0's 2.2). The exemplar list may have anchored specialists too tightly to the named domains. The verification-discipline rule may have caused them to omit useful specifics they couldn't perfectly source.

V1's effect on faithfulness scores looked positive (Gemini judge), but we know that signal is unreliable.

### V3 (V1 + V2 combined) was _worse_ than V2 alone

Counter-intuitive result: combining the two changes degraded performance. On primary probes, V3 category coverage was 1.4 (worst of any variant). Hypothesis: V1's "don't invent specifics" rule plus V2's mandated extra specialists made each dispatched specialist more conservative — they covered their lane narrowly because they expected others to fill in. V2 alone, without V1's hedging discipline, let specialists be braver about specifics.

This is a real finding: **prompt changes are not additive.** Two independently-good changes can interact destructively.

### V2 had a substitution bug; V2.1 fixed it with one-word change — but introduced a new gap

V2's coverage rule said "MUST dispatch {X, Y, Z}" — the orchestrator interpreted this as the _whole_ dispatch, not a floor. On Sopot openings/closings, V2 swapped V0's `{dynamic_researcher_1, location_traffic, market_landscape}` for the mandated `{market_landscape, marketing_digital, menu_pricing}`. The Food Hall Krzywy Domek — the single biggest local opening event 100m from Śliwka — was caught by V0's `dynamic_researcher_1` and lost in V2's substitution.

V2.1 changed "MUST dispatch" to "MUST include … other specialists may be added" plus added "Also consider" hints. The Sopot dispatch became `{market_landscape, marketing_digital, menu_pricing, location_traffic}` — added without removing — and the Food Hall reappeared.

**However**, V2.1 doesn't list `review_analyst` in the closures rule, and the orchestrator's free choice happens to drop it on `monsun × q2_closures_lessons`. V2 had freely added `review_analyst` on the same combo (5-specialist dispatch, including the analyst) and that's where V2's most actionable finding came from — a review-tone analysis of Monsun's own defensive owner-responses on Google Maps. V2.1's "competently narrower" report on this combo loses that finding entirely. **The fix to one substitution surfaced an absence in another.** Bounded — operator-judge says V2.1 is still useful here, just rank-3 — but a real follow-up item.

### Gemini-as-judge was unreliable; operator agents were not

We tried single-call rubric judging with Gemini 2.5 Pro. The judge:

- Gave `investigative_stance = 5.0` to **114 of 120 runs across V0/V1/V2/V3/V2.1** (95%). The 6 non-5 cases were all in V3 (2) and V2.1 (4). The rubric anchors for that dimension are too lax — it functioned as constant.
- Scored Sopot/q3 V0 at faith=0 when the agent had verifiably fetched real menus from blekitnypudel.pl and confirmed real prices.
- Scored Monsun/q1 V0 at faith=5 when later operator-agent verification showed multiple unverifiable specifics (Beggin CEIDG, fabricated rent figures).
- Did not differentiate V2.1 from V0 in flagged-run counts despite operator agents preferring V2.1 4-2 in the pairwise.

**Conclusion: rubric-based single-call judges produce noise at the resolution we needed for ship decisions.** Multi-step agent-as-judge with WebFetch verification is the only thing that gave usable signal.

### Venue variance is real and important

The same query produces very different reports across venues. Monsun and Bar Leon got 18-40 sources; Śliwka often got 7-13. Faithfulness scores per Gemini ranged from 1.88 (Sopot avg) to 3.25 (Monsun avg). Single-venue evals would have led to wrong conclusions repeatedly.

Implication for any future eval: **always run multi-venue.** The matrix size cost is worth it.

---

## Surprises

### V0 had quietly improved between the trigger session and our baseline run

Commit `98ee238 feat(sources): one provider pill per API` shipped Google Maps source attribution between the original PM complaint and our V0 baseline. Top-domain share on Monsun dropped from 80% (in the trigger session) to 40% (in our V0 baseline) — same query, same venue, no prompt changes, just code that shipped in between. Lesson: **always re-baseline against current code.** The motivating example was historical.

### The marketing wall is not what the agent reaches

The landing page's _"Only credible data sources"_ section advertises 29 brands (TripAdvisor, OpenTable, Yelp, TheFork, Pyszne.pl, Wolt, Glovo, Statista, IBISWorld, NielsenIQ, Eurostat, CEIDG, etc.). On average, **V0 reports touched 0.5 of those 29 brands per run.** V2.1 improved this to 0.9. Either way: the gap between marketing claim and product reality is dramatic. This is a separate issue worth its own conversation.

### V2.1 wasn't strictly dominant — the monsun q2 closures regression

V2.1's deterministic aggregate metrics are better than V0's on every dimension we measured. But on `monsun × q2_closures_lessons` specifically, V2.1's metrics collapsed: 1 source category (vs V0's 3), 61.5% top-domain share (vs V0's 27%), 13 drawer sources (vs V0's 26 and V2's 38). Operator-pairwise confirmed: V2.1 ranked worst of three on this combo, with V2 best because V2 freely added `review_analyst` (which V2.1 didn't list in its closures rule and the orchestrator dropped on this run). Net pairwise tally for V2.1: 4-2 not 4-1. The single most actionable finding in any version of this report — V2's analysis of Monsun's own defensive owner-responses on Google Maps — was lost in V2.1.

This was caught by external review of the writeup, not by the harness. Lesson: deterministic regressions on individual primary-probe combos deserve their own pairwise check, not just aggregate-level confidence.

### Wage-benchmarking queries are uniformly bad

Across all 24 V0 runs, the three wage-benchmarking runs (one per venue) had the worst Gemini-judge scores: faith=0/0, faith=1/1, faith=1/2. Every variant we tried — V1, V2, V3, V2.1 — had similar profiles. The dispatch was always `{operations, dynamic_researcher_1}`. There's something structurally wrong with how the agent does wage research: probably no good public data source for restaurant wages in Poland that the agent can reach via google_search + fetch_web_content.

### Sopot is the hardest venue

Śliwka w Kompot got the lowest faithfulness scores in V0 (1.88 vs 3.12-3.25 for the other two). Initial hypothesis was supply-side — Sopot has less press coverage. Operator-agent investigation contradicted that: Śliwka has 14,964 Restaurant Guru reviews, presence on TripAdvisor/Yelp/InYourPocket, an Instagram, and is covered in restaurant guides. The data is there; the agent isn't reaching it. That's a different problem than supply-side absence.

### The dynamic_researcher_1 specialist mostly fires for wage queries

In V0, `dynamic_researcher_1` dispatched 4 of 24 times — three of those were wage-benchmark queries. The orchestrator treats it as the wage-specialist gap-filler in practice, even though the catalog presents it as "flexible, for angles outside the 7 domains." This is informal de-facto specialization.

---

## Discoveries

### Cloud One Hotel next door to Bar Leon

V2.1's pairwise on Bar Leon q1 surfaced a 327-room hotel at Stągiewna 27 — same street as Bar Leon, with hotel-anchored F&B as a structural threat to Bar Leon's lounge positioning. **This was completely absent from V0's report** despite being within 100m of the venue. Marketing_digital + location_traffic together found it.

### Food Hall Krzywy Domek

8-concept food hall opening at Monte Cassino 53 in May 2025, 100m from Śliwka. Single largest opening event in the Śliwka neighborhood. V0's `dynamic_researcher_1` caught it; V2 lost it via substitution; V2.1 caught it back.

### The "scrubbed from delivery" closure signal

V2.1's reports identified a powerful closure-detection technique V0 wasn't using: cross-referencing whether a "temporarily closed" venue still has active Pyszne / Wolt / Glovo / Uber Eats listings. A venue removed from delivery platforms is far more likely permanently closed than one merely flagged "temporarily closed" on Google Maps. This emerged from `marketing_digital` being on the dispatch.

### The Polish food-blog landscape is underused

The user explicitly flagged that "SEO-heavy blogs" warning could discourage culinary blogs (which in Poland are often firsthand primary sources). We rewrote V1's anti-content-farm guidance to target the actual failure mode (listicle aggregators that restate others' work) rather than blogs in general. The V1 specialist instructions explicitly name Polish food bloggers (Dusiowakuchnia, Kotowisko, etc.) as legitimate primary sources. **None of this carried into V2.1** because V2.1 is orchestrator-only — leaving that signal as an obvious next step.

### Municipal/city-authority sources are high-value and underused

The original Monsun report cited `zdiz.gdynia.pl` (Gdynia road authority) and `www.gdynia.pl`, which provided the authoritative basis for the Jan 2026 SPP parking overhaul claim. The user flagged this as a source type to _encourage_. V1 added this as an explicit category, but V2.1 didn't carry V1 forward.

---

## Learnings

### About prompt changes

1. **Dispatch beats wording.** Forcing the orchestrator to add a specialist had a much bigger effect than rewriting how specialists work.
2. **Additive > substitutive rules.** "MUST include" landed; "MUST dispatch" caused regressions through specialist substitution.
3. **Combined changes can interact destructively.** V3 (V1+V2) was worse than V2 alone. Combine cautiously.
4. **The fix for "agent doesn't think to use X" is "tell the orchestrator to dispatch the specialist that uses X" — not "tell the existing specialist to consider X more."** Specialists already had `fetch_web_content` for any URL; they just weren't called for the relevant angle.

### About evaluation

1. **Multi-venue is non-negotiable.** Single-venue eval would have produced wrong conclusions multiple times.
2. **Single-call rubric judges are noise.** They worked as a cheap deterministic reproducible reference, but should not drive ship decisions.
3. **Operator-role agents with WebFetch verification are the gold standard.** Cost ~1 minute per comparison, produced unambiguously useful signal every time.
4. **Pairwise > absolute.** "Is A better than B" is much easier for an LLM to answer than "rate A from 0 to 5."
5. **`sources[]` ≠ research evidence set.** Capture the raw event stream if you want true diversity metrics.
6. **Always re-baseline against current code.** Production moves while you're not looking.

### About measurement design

1. **Top-domain share is the right primary diversity metric**, not unique-domain count. Long tails flatter low-effort answers.
2. **Category coverage with a curated taxonomy** is the highest-signal aggregate measure once domain noise is controlled.
3. **Specialist dispatch should be a captured metric, not a hidden detail.** Tracking which specialists fire per query reveals more about agent behavior than any single output metric.
4. **Marketing-wall overlap is an honesty metric**, not a quality metric. The gap between promised data sources and delivered ones is its own KPI.

---

## Recommendations

### Immediate (ship)

1. **Promote V2.1 to production as a controlled improvement.** Replace `agent/superextra_agent/instructions/research_orchestrator.md` with the V2.1 version at `agent/evals/instructions_variants/V2_1/research_orchestrator.md`. No other file changes. **Acknowledge the known monsun q2 regression** to operations / monitoring — it's bounded (operator-judge: "competently narrower," not wrong) but real.
2. **Decide whether to also add `review_analyst` to the closures-query coverage rule** — single-line addition; would directly address the monsun q2 case but introduces a new untested change. Either ship now and patch later, or build V2.2 (one more 70-min run + pairwise) and ship that. Committee preference.
3. **Keep the eval harness in-tree as a regression check** for any future prompt or model change.
4. **Document V2.1's coverage rules in `instructions/AUTHORING.md`** so future contributors don't accidentally remove the additive framing.

### Short-term (next iteration)

1. **Port V1's good ideas into V2.1 one at a time** — start with municipal-authority and culinary-blog source framing in `specialist_base.md`. The verification-discipline rule was the part of V1 that interacted destructively in V3, so introduce that one cautiously and only after the other two have been validated. Run each through the matrix individually before combining.
2. **Make pairwise judging a first-class artifact in the harness.** Currently pairwise verdicts are session-ephemeral. Build `agent/evals/pairwise.py` that scripts a Claude subagent call with the prompt, captures the verdict + supporting URLs, and stores the result alongside the run JSONs. Use this as escalation for ambiguous/high-impact cases, not as the default gate.
3. **Investigate the wage-benchmarking failure mode separately.** All variants produce poor wage reports — the dispatch is uniform `{operations, dynamic_researcher_1}`, the data simply isn't reachable via google_search + fetch_web_content. This is a capability gap, not a prompt-tuneable problem. Treat it as a separate project.
4. **Consider adding `review_analyst` to the closures-query rule** if not done in the immediate ship. Would address the monsun q2 case while keeping the additive framing.

### Medium-term (follow-on projects)

1. **Marketing-wall delivery audit.** The 29 advertised data sources land 0.9 brands per report on average. Either (a) prune the wall to what's actually delivered, or (b) extend agent capability to reach more of them. Both are honest.
2. **Move pairwise judging into the harness.** The Claude operator-agent approach worked manually. A scripted version (using the Anthropic SDK in `agent/evals/`) would let us run pairwise A/B at scale on any future variant without manual subagent spawning.
3. **Calibrate or replace the Gemini judge.** If we want a cheap deterministic judge for CI, it needs human-anchored calibration — the current rubric produces uniform-5 on investigative_stance and noise on faithfulness.
4. **Expand to non-Polish markets.** All testing was Tricity. The orchestrator coverage rules are domain-general, but the source taxonomy assumed Poland-specific examples. Verify on at least one other market before claiming generality.

### Cross-cutting

1. **Dispatch-as-lever is the project's thesis.** Whenever someone says "the agent doesn't think to do X," the question to ask is "should a specialist that does X be in the dispatch?" — not "should we tell the agent more about X?"
2. **Operator-agents as judges should be the default review pattern** for any prompt or model change going forward.

---

## What we'd do differently

1. **Re-baseline production code first.** We wasted half a day debugging "monoculture" before realizing the source-pills change had already shipped.
2. **Set up multi-judge from the start.** We started with Gemini-only and only pivoted to operator agents after the Gemini judge produced obviously wrong scores. Day-one operator judging would have saved time.
3. **Build the harness before designing variants.** We had three variants drafted before we had a working measurement pipeline — and the harness took longer to build than the variants did.
4. **Test the simplest variant first.** V2 is a smaller change than V1 (one file vs eight) and turned out to be the winner. We could have tested V2-only first, ruled it out or in, then layered V1 if needed.
5. **Don't combine variants prematurely.** V3 was a wasted run; combining V1+V2 destructively was predictable in hindsight.

---

## Open questions for the committee

1. **Do we ship V2.1 today (with the known monsun q2 limitation), build V2.2 first, or wait for the V1-port?** Three options at differing risk/time cost.
2. **What's the budget for the marketing-wall audit?** This is a product positioning question more than a research-depth question, but the gap is real.
3. **Should the eval harness become a CI gate?** Currently it's a manual scaffolding tool. A nightly run on a fixed query set could catch silent regressions.
4. **What's the cost ceiling for pairwise operator-judges?** They cost real Anthropic API tokens. Budget cap matters before scripting it into the harness.
5. **How do we handle the wage-benchmarking failure?** Build a wage data source? Drop wage queries from the pill set? Acknowledge a known limitation in product copy?

---

## Artifacts

**In repo (`agent/evals/`):**

- `run_matrix.py` — subprocess-per-variant runner
- `parse_events.py` — ADK event parser
- `score.py` — deterministic + Gemini judge scorer
- `summarize.py` — scorecard formatter
- `judge_rubric.md` — Gemini judge rubric (now noted unreliable)
- `queries.json`, `venues.json` — fixture
- `instructions_variants/V1/`, `V2/`, `V3/`, `V2_1/` — overlay files

**Run data:**

- `agent/evals/results/V0/`, `V1/`, `V2/`, `V3/`, `V2_1/` — 24 JSONs each, raw run captures
- `agent/evals/scores/V0.csv`, `V1.csv`, `V2.csv`, `V3.csv`, `V2_1.csv` — scored CSVs
- `agent/evals/logs/` — run logs per variant + per scoring pass

**Production change for V2.1 ship:**

- One file: `agent/superextra_agent/instructions/research_orchestrator.md`
- Plus a one-line env-var fallback already shipped in `specialists.py:23-24` and `agent.py:36-37` (zero behavior change in production when the env var is unset)

**Documents:**

- `docs/research-depth-proposal.md` — original proposal (superseded by Phase B)
- `docs/research-depth-proposal-review-2026-04-23.md` — external review of original proposal
- `docs/research-depth-eval-plan.md` — Phase A/B plan (after revisions)
- `docs/research-depth-phase-b-baseline.md` — V0 baseline scorecard
- `docs/research-depth-pairwise-verdicts-2026-04-25.md` — committed pairwise verdict transcripts (all 9 comparisons including the monsun q2 regression check)
- `docs/research-depth-final-report-2026-04-25.md` — this report

---

## Appendix: example findings (excerpts)

### V2.1 surfacing Bambus Grill (Monsun pairwise)

> _"V2.1 also notes the delivery-platform deactivation check (Wolt, Pyszne, Uber Eats, Glovo) as permanent-closure evidence — a verification technique V0 doesn't use. … Bambus Grill & Oriental at Świętojańska 93 — a direct pan-Asian competitor with concrete price deltas (39–44 vs 54–56 PLN), a 25 PLN Express Box targeting Monsun's unaddressed student/lunch segment, Wolt-only vs multi-platform distribution, and 15 PLN acquisition discounts."_

### V2.1 catching Cloud One Hotel (Bar Leon pairwise)

> _"V0 misses the two biggest structural forces on Granary Island — (1) hotel-anchored F&B as the real new competition (Cloud One is literally next door at Stągiewna 27, the same street as Bar Leon; V0 doesn't mention it), and (2) the delivery-platform behaviour of new vs. dying venues."_

### V2.1 fixing the Sopot Food Hall miss

> _"V2.1 explicitly names the Food Hall Krzywy Domek with a dedicated section, pins it to Monte Cassino 53, dates the opening to May 2025, and names vendors (Pizza Mollo, TukTuk Thai Streetfood, Hola Breakfast & Tapas). V2 misses it entirely — worse, it treats SOHOT Tacos & Tequila's 'Temporarily Closed' Google Places flag as a mystery ('lease hurdles... went completely quiet'), when the real cause was the building being gutted for the food hall. That is the exact blind spot the V2.1 change was meant to close."_

### V0 fabrication caught by operator agent (Bar Leon)

> _"V0's '56,000 PLN/100m²' Prestiż citation does not survive verification. Trojmiasto's widely-cited rent article gives 180–250 PLN/m² on Wyspa Spichrzów (so ~18–25k for 100m², not 56k). V0's number looks inflated or fabricated; the '100,000 PLN waterfront' figure is also unsourced."_

### The single V2.1 loss (Sopot sentiment)

> _"V2.1 has one finding V0 lacks (0% TripAdvisor response rate) and tighter demographics. V0 has the expansion-timeline narrative, the dated quote evidence, the kitchen-rigidity insight, and sharper competitor diagnostics. For a 'real sentiment themes' query, V0 delivers more themes that would actually change the operator's operations."_

The single loss was on a non-targeted query, with marginal differences. Not a reason to hold V2.1.
