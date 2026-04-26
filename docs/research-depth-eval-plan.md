# Research-depth eval plan — test drive before we ship

## Goal

Measure research depth quantitatively on real queries before changing production prompts or orchestration. The plan produces a scorecard per prompt variant — source diversity, specificity, completeness, faithfulness, specialist dispatch patterns — run against a fixed Tricity query × venue matrix. We ship a variant only if the numbers beat V0, with specificity and faithfulness guarded so we don't trade named-and-dated content for breadth, or breadth for fabrication.

Supersedes the "next steps" section of `research-depth-proposal.md`.

## What the test drive taught us

Before designing the harness, we ran the same query (_"What has opened or closed in my area recently?"_) against two Tricity venues and compared.

|                               | Monsun, Świętojańska (2026-04-15) | Bar Leon, Wyspa Spichrzów (2026-04-24)                      |
| ----------------------------- | --------------------------------- | ----------------------------------------------------------- |
| Sources cited (drawer)        | 10                                | 18                                                          |
| Top-domain share              | 80% (8×trojmiasto.pl)             | 56% (10×trojmiasto.pl)                                      |
| Category coverage             | 1–2                               | 4–5                                                         |
| Google Maps in sources drawer | No                                | Yes                                                         |
| Real-estate sources           | None                              | otodom.pl ×2, m2bomber.com, inwestycjewkurortach.pl, olx.pl |
| National press                | None                              | wyborcza.pl, wyborcza.biz, rp.pl                            |
| Delivery platforms            | 1 peripheral (ubereats)           | None                                                        |
| Influencers / blogs           | None                              | None                                                        |
| Venue's own channels          | None                              | None                                                        |
| TripAdvisor                   | None                              | None                                                        |

Five things change how the plan should be built:

1. **Venue variance is a first-order effect.** Same query, same code, dramatically different source shape. Any eval with a single venue would mislead.
2. **The source-pills-per-provider plan shipped between these two sessions** (commit `98ee238`). The Monsun result is historical — Bar Leon is a more accurate V0 snapshot of current code.
3. **`sources[]` is the UI drawer, not the research evidence set.** The drawer only holds grounding-metadata URLs + provider-tool pills (Places / Reviews / TripAdvisor). Arbitrary `fetch_web_content(url)` calls are tool activity that never reaches the drawer unless also cited via grounding. Diversity metrics computed from `sources[]` alone systematically under-count research breadth. We capture raw ADK events per run and build the real evidence set from grounding URLs + `fetch_web_content` URLs + provider pills.
4. **The marketing wall lists 29 data sources; the agent actually reaches a handful.** Some of the "reaches" are plumbing artifacts (Google Maps is auto-written for the target place by the Places enricher regardless of research activity). Wall overlap is useful as a secondary diagnostic, not a primary diversity metric.
5. **Quality is genuinely good in some runs.** Bar Leon's report is specific, dated, named, with rent figures and sentiment quotes — even while 56% of its drawer sources are one domain. Diversity-only metrics would misread this as worse than it is. Specificity needs to be a guarded metric, not a bonus. So does faithfulness.

## Hypotheses

**H1** — Soft-prior exemplars in specialist instructions (using OpenAI Cookbook's wording pattern) plus a "starting points, not ceilings" self-audit block will reduce top-domain share and increase category coverage without hurting specificity or faithfulness.

**H2** — Orchestrator-level query-specific coverage constraints for coverage-sensitive questions (openings/closings, "what's new," before/after) will further reduce monoculture on those specific query types.

External evidence is slightly stronger for H2 than H1 — Anthropic's published pattern explicitly has the lead agent give subagents "objective, output format, guidance on tools and sources, and clear task boundaries" at delegation. Both are still worth testing; expect H2's effect to be larger and more reliable.

Claim-verification as a separate hypothesis is dropped — not the issue for this project now. Faithfulness is still measured as a rubric dimension to guard against unsupported detail slipping in (specificity without truth).

## Source taxonomy (8 categories, with examples)

Grounded in the landing page's "credible data sources" wall plus Polish-specific knowledge. Examples are illustrative — the agent shouldn't receive them as a checklist.

| #   | Category                               | Examples                                                                                                                                                            |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Community discussion**               | trojmiasto.pl forums, Reddit (r/gdansk, r/trojmiasto), Wykop, local Facebook groups                                                                                 |
| 2   | **Local press**                        | gdynia.naszemiasto.pl, gdansk.naszemiasto.pl, sopot.naszemiasto.pl, wyborcza.pl/trojmiasto, wyborcza.biz, dziennikbaltycki.pl, radiogdansk.pl, rp.pl                |
| 3   | **Industry sites & reports**           | horecatrends.pl, orlygastronomii.pl, foodie.pl, foodfakty.pl, smaki.pl, Statista, IBISWorld, NielsenIQ, Deloitte, Eurostat HORECA datasets                          |
| 4   | **Influencers & blogs**                | Tricity Instagram food accounts, Polish food bloggers, TikTok food creators, YouTube reviewers                                                                      |
| 5   | **Consumer platforms**                 | Google Maps, Pyszne.pl, Wolt, Glovo, Bolt Food, Uber Eats, TheFork, OpenTable, TripAdvisor, Yelp, Zomato, Michelin Guide, Foursquare, Finebite                      |
| 6   | **Venue's own channels**               | The restaurant's own website, official Instagram, official Facebook page, online ordering page, menu PDFs                                                           |
| 7   | **Official registries & statistics**   | CEIDG / KRS / REGON (PL), GUS, Eurostat, OECD, Handelsregister (DE), Companies House (UK), SEC / EDGAR (US), Krajowy Rejestr Długów, Dun & Bradstreet, Creditreform |
| 8   | **Commercial listings & marketplaces** | Commercial real estate (otodom, gratka, domiporta, m2bomber), olx.pl, classifieds, industry job boards                                                              |

Categories 7 and 8 were split from a single "Structured data" bucket because one OTODOM listing shouldn't count toward coverage the same way a GUS dataset does.

## Test query set (8, drawn from `TopicPills.svelte`)

One per pill color category, weighted toward the verified failure mode.

| #   | Pill category              | Query                                                                             | Primary probe                      |
| --- | -------------------------- | --------------------------------------------------------------------------------- | ---------------------------------- |
| 1   | Competitor tracking (cyan) | _"What has opened or closed in my area recently?"_                                | Yes — Monsun/Bar Leon repro        |
| 2   | Market shifts (red)        | _"What has closed nearby recently and what can I learn from it?"_                 | Yes                                |
| 3   | Price positioning (amber)  | _"How does our menu pricing compare to competitors within 1 km?"_                 | Yes — delivery-platform dependency |
| 4   | Sentiment trends (orange)  | _"What are the real sentiment themes across our reviews and competitors?"_        | — wakes review_analyst             |
| 5   | Concept validation (pink)  | _"Which formats and cuisines are thriving in this neighbourhood?"_                |                                    |
| 6   | Site selection (purple)    | _"How saturated is the food and drink market within 1 km of this location?"_      |                                    |
| 7   | Market context (indigo)    | _"How is the local food and drink market performing compared to six months ago?"_ |                                    |
| 8   | Wage benchmarking (green)  | _"What are restaurants near us actually paying for every role?"_                  |                                    |

Query 5 was swapped out of the original "what locals are searching for" wording because that formulation needs search-demand data that the current toolset doesn't have (no Google Trends, no keyword API). Poor results there would be a capability failure, not a prompt failure, and would muddy H1/H2 falsification.

## Venues (3 Tricity)

- **Monsun**, Gdynia (Świętojańska) — high street retail context
- **Bar Leon**, Gdansk (Stągiewna, Wyspa Spichrzów) — touristy island, investment-heavy
- **Śliwka w Kompot**, Sopot — resort-town context

Place IDs to be captured in Phase A.

8 queries × 3 venues = 24 runs per variant. End-to-end each (~3 min × 24 = ~72 min per variant, parallelizable).

## Metrics

Three layers. All except the judge layer are computed from captured ADK events per run.

### Evidence-set capture (foundation for deterministic metrics)

Per run, we build two evidence sets from the raw ADK event stream:

- **Phase 1 evidence set** — union of all URLs the specialists and orchestrator touched: `{grounding-chunk URLs from each specialist} ∪ {fetch_web_content URLs from tool calls} ∪ {provider-tool pills}`. "What the research agents actually reached for."
- **Final evidence set** — the cited URLs in the user-visible drawer (`sources[]`). "What made it into the user's view."

Comparing the two is how we diagnose where diversity drops:

| Pattern                         | What it means               | Where to intervene                          |
| ------------------------------- | --------------------------- | ------------------------------------------- |
| Phase 1 narrow AND Final narrow | Research itself is shallow  | Specialist / orchestrator prompts (V1 / V2) |
| Phase 1 broad BUT Final narrow  | Synth is dropping diversity | Synthesizer prompt                          |
| Phase 1 broad AND Final broad   | Working as intended         | —                                           |

Both sets get their own diversity metrics below.

### Deterministic (code only)

Computed on Phase 1 set AND Final set (two numbers per metric per run):

- **Top-domain share (%)** — primary diversity metric. Monsun drawer was 80%, Bar Leon drawer 56%. Lower is better.
- **Unique domain count** — secondary. Flatters answers with a long tail, but useful as context.
- **Category coverage** — binary per category across the 8-category taxonomy. How many of the 8 are represented?
- **Marketing wall overlap** (Final set only, secondary diagnostic) — of the 29 brands on the landing page's "credible data sources" wall, how many appear in `sources[]`? Auto-written Google Maps entries are excluded to avoid plumbing inflation. Demoted from primary to diagnostic because many wall brands are market-irrelevant for any given query.
- **Provider presence** (Final set only) — does `sources[]` include Places / Google Reviews / TripAdvisor entries where applicable?
- **Specialists dispatched** — which specialists the orchestrator woke up per run. Stored as set, compared across variants. Tells us if V2 actually shifts dispatch patterns.

Run-level telemetry:

- **Runtime** — wall clock, per run.
- **Tokens by model** — LLM prompt + completion tokens (already logged at `chat_logger.py:199-204` via `llm_response.usage_metadata`). We track **total LLM tokens per run** as the cost proxy; exact dollar cost is skipped because it needs a pinned pricing snapshot and splits across Places / Apify / SerpAPI / Jina calls.
- **Per-tool call counts** — how many times each of {Places, Apify, SerpAPI, Jina (`fetch_web_content`), `google_search`} fired. Useful diagnostic for "why did this variant cost 2x."
- **Confound flags per run:**
  - `gap_ran: bool` — did the gap researcher fire? (It fires only when at least one assigned specialist failed; see `specialists.py:254`.) Runs where gap fired get a separate column because gap adds up to 3 extra searches that may mask or inflate V1/V2 effects.
  - `synth_outcome: "ok" | "empty_response" | "no_text_parts" | <error_code>` — did the synthesizer produce a real response or did the fallback stitcher kick in? (See `agent.py:134,156`.) Fallback runs are **excluded from the decision gate** because they didn't go through the synthesis path we're measuring.

### Gemini-as-judge (rubric, scored 0–5)

Per report:

- **Faithfulness** — are the claims grounded in the cited sources? **Guard**: no regression ≥1 point vs V0.
- **Completeness** — does the report answer the question?
- **Specificity** — named restaurants, named streets, dates, figures, vs generic prose. **Guard**: no regression ≥1 point vs V0.
- **Investigative stance** — tests the premise vs confirms it?

Single Gemini 2.5 Pro call per report with a rubric prompt. Anthropic's published experience (their own multi-agent research system) found a single-call single-rubric judge outperformed multi-judge ensembles for their use case; we adopt the same pattern but it's their finding, not a general rule. LLM-judge agreement with humans on rubric tasks generally runs 80–90%.

### Explicitly out of scope (for now)

- Claim atomization / unsupported-claim rate — dropped per earlier decision.
- Per-domain fetch failure / truncation telemetry — requires `web_tools.py` instrumentation, too much lift for Phase A. Revisit if a variant's diversity gains look implausible.

## Prompt variants

- **V0** — current production. Baseline (post-source-pills).
- **V1** — V0 + soft-prior exemplars in each specialist's instruction file + "starting points, not ceilings" self-audit block. Wording is anchored to the OpenAI Cookbook's public Deep Research guidance (verbatim phrase: _"prefer linking directly to official or primary websites (e.g., official brand sites, manufacturer pages, or reputable e-commerce platforms like Amazon for user reviews) rather than aggregator sites or SEO-heavy blogs"_) at `developers.openai.com/cookbook/examples/deep_research_api/introduction_to_deep_research_api`, customized to restaurant context. Example template:
  > _"For restaurant market research, prefer linking directly to primary venue channels (the restaurant's own website, Instagram, Facebook), primary consumer platforms (Google Maps, Pyszne.pl, Wolt, Glovo, TripAdvisor, TheFork), and local-press / industry-trade sources (e.g., gdynia.naszemiasto.pl, horecatrends.pl) rather than aggregator sites or SEO-heavy blogs. If the query is in a specific language, prioritize sources published in that language. Starting points, not ceilings — go beyond these when the question warrants."_
- **V2** — V0 + orchestrator injects query-specific coverage constraints for coverage-sensitive questions. Pattern: orchestrator detects query type, names the evidence surfaces the brief must cover (not domains — surfaces).
- **V3** — V1 + V2 combined.

## Runner — subprocess-per-variant

The agent's instruction files are read into module globals at import time (`specialists.py:85`, `agent.py:40,60,82,205,233`). A mid-process "switch variants" override won't work without refactoring production code. To avoid touching production, the runner spawns a **fresh Python subprocess per variant** with an `INSTRUCTIONS_DIR` env override pointing at that variant's directory.

```
python agent/evals/run_matrix.py \
    --variant V1 \
    --queries agent/evals/queries.json \
    --venues agent/evals/venues.json \
    --out results/V1/
```

What it does per variant:

- Reads `instructions_variants/V1/` (a directory containing only the files that differ from `instructions/` — any unchanged file falls through to the default path).
- Spawns a Python subprocess with `INSTRUCTIONS_DIR=<resolved path>` and the query × venue matrix.
- The subprocess runs the agent pipeline in-process (reusing `phase0_measure.py`'s pattern at `agent/tests/phase0_measure.py`), captures the raw ADK event stream per query/venue, and writes one JSON per run.
- ~10 s spawn overhead per subprocess — negligible next to 3 min pipeline runs.

Per-run JSON contains: `final_report`, `drawer_sources`, `grounding_urls`, `fetched_urls`, `provider_pills`, `specialists_dispatched`, `gap_ran`, `synth_outcome`, `runtime_s`, `tokens_by_model`, `tool_call_counts`.

Scoring pass (reads the JSON, computes metrics, runs the Gemini judge):

```
python agent/evals/score.py --results results/V1/ --out scores/V1.csv
```

Outputs one CSV row per query × venue × variant, with both Phase-1 and Final columns for the deterministic diversity metrics.

### Targeted single-specialist mode

```
python agent/evals/run_specialist.py \
    --specialist market_landscape \
    --brief briefs/openings_closings_monsun.json \
    --variant V1
```

Used for fast iteration on V1 only (specialist-instruction-only changes). Skip for V2 and V3 — orchestrator changes need end-to-end to show interaction effects.

## Decision criteria

Promote V1 / V2 / V3 → production if, vs V0:

- **Top-domain share (Final)** drops ≥15pp on primary probe queries (#1, #2, #3)
- **Category coverage (Final)** +≥1 category on average across all 24 runs
- **Specificity** score holds or improves (**guarded** — no regressions ≥1 point)
- **Faithfulness** score holds or improves (**guarded** — no regressions ≥1 point)
- **Completeness** score holds or improves
- **LLM token total** within 1.5× V0

Runs where `synth_outcome != "ok"` are excluded from the gate (the synth fallback never goes through the path we're measuring). Runs where `gap_ran == true` are kept but flagged separately in the scorecard so we can see whether gap behavior skewed results.

If H1 (V1) and H2 (V2) both contribute independently, ship V3. If only one does, ship that one. If neither, keep digging — the assumption that prompts can fix this was wrong.

## Phasing

**Phase A — harness (no production changes):**

1. Grab Place IDs for the 3 venues.
2. Write `queries.json` and `venues.json`.
3. Build the subprocess-per-variant batch runner.
4. Build the ADK event parser (~50 lines in `agent/evals/`). Extracts grounding URLs, `fetch_web_content` URLs, `_tool_src_*` provider pills, `synth_outcome`, and specialist dispatch from raw events.
5. Build the scorer (deterministic metrics + Gemini-judge rubric).
6. Write the Gemini-judge rubric prompt. Calibrate against 3 hand-scored reports.

**Phase B — baseline:** 7. Run V0 across all 24 combinations. 8. Adam spot-checks 3 outputs (one per venue) to confirm Gemini judge agrees with his sense of "good answer." 9. Review the baseline scorecard together before Phase C. Specifically: does the Phase-1-vs-Final comparison show synth-level diversity drops? If yes, V1/V2 may not be the right intervention.

**Phase C — prompt variants:** 10. Implement V1 — edit specialist instruction files in `instructions_variants/V1/`. Use OpenAI-Cookbook-anchored wording. Cite the URL in each file. 11. Implement V2 — edit orchestrator instruction in `instructions_variants/V2/`. Add the query-type-detection + coverage-constraint block. 12. Run V1 in targeted single-specialist mode first. Iterate on wording. 13. Run V1, V2, V3 end-to-end across all 24 combinations. 14. Compare scorecards.

**Phase D — production cutover:** 15. Promote the winning variant to `instructions/`. Keep the eval harness as a regression guard for future prompt/model changes.

## What Adam's involvement looks like

- Pick Place IDs or confirm mine (5 min).
- Phase B — 3 spot-checks to calibrate the Gemini judge (~15 min total).
- Phase B — review the V0 baseline scorecard before we push variants (15 min).
- Phase C — review the final scorecards before promotion decision (15 min).

Roughly 50 minutes of review, spread across phases.

## What success looks like

At the end of Phase C we have a scorecard like this (one row per query × venue × variant, plus aggregate rows):

```
                        V0     V1     V2     V3
top_dom_phase1%         72     55     60     45
top_dom_final%          68     52     58     44   ← lower is better
cat_cov_phase1          2.5    3.8    3.2    4.5  ← out of 8
cat_cov_final           2.1    3.4    2.9    4.1
faithfulness            4.3    4.2    4.3    4.1  ← 0-5, guarded
specificity             4.1    4.0    4.1    3.8  ← 0-5, guarded
completeness            4.2    4.3    4.2    4.3
wall_overlap%           22     31     26     37   ← secondary diagnostic
tokens_x                1.0    1.1    1.3    1.4
gap_ran_rate            18%    12%    14%    10%
synth_ok_rate           96%    95%    97%    94%
```

(Illustrative. Real numbers TBD.)

The decision ("ship V3? only V1?") becomes a decision against numbers, not vibes. The Phase-1-vs-Final delta in the diversity metrics tells us whether the lever is in the specialists or the synthesizer. And the harness lives on as a regression check whenever we change prompts, models, or add specialists.

## Appendix: Bar Leon baseline detail

The test-drive run (session `a021c2dd-eed4-4411-8d4c-965aa5778821`) produced:

- 18 drawer sources: Google Maps ×1, trojmiasto.pl ×10, wyborcza.pl ×1, wyborcza.biz ×1, rp.pl ×1, inwestycjewkurortach.pl ×1, otodom.pl ×2, m2bomber.com ×1, olx.pl ×1, wzch-trojmiasto.pl ×1
- Top-domain share (Final): 56%
- Category coverage (Final, under the new 8-cat split): Community (trojmiasto forums + text-only mentions of Reddit r/gdansk and Wykop), Local press (wyborcza.pl, wyborcza.biz, rp.pl), Industry sites & reports (inwestycjewkurortach.pl, partial), Consumer platforms (Google Maps — auto-written, so excluded from wall overlap), Commercial listings & marketplaces (otodom ×2, m2bomber, olx). **5/8 categories.**
- Missed categories: Influencers & blogs, Venue's own channels, Official registries & statistics.
- Phase 1 evidence set: **not captured** — the test-drive pre-dated the event-parser build. Phase A of the harness will add this for the real V0 baseline.
- Specialists dispatched: also not captured — will be extracted from ADK events in Phase A.
- Marketing wall overlap: 0 brands (Google Maps excluded as auto-written; nothing else from the wall present).
- Runtime: 3m 8s.
- Qualitative read: high specificity (Miss Hotpot Jan 2025, White Marlin Feb 2025, Fuego Aug 2025, Gyozilla, Chilli Bar transition, Ulu March 2026, rent figures 180–250 PLN/m²). Investigative stance (premise validated, not just confirmed).

This pre-harness run becomes useful as a qualitative reference point for Phase A calibration, not as row 1 of the formal baseline — the real V0 baseline runs in Phase B once the harness exists.
