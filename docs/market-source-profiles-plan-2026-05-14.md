# Market Source Profiles — Implementation Plan

Date: 2026-05-14
Scope: Stream 2.3 from `agent-adjacent-streams-plan-2026-05-11.md`, narrowed to per-market profile injection, category taxonomy, and prompting design.
Out of scope: evals, citation plumbing, follow-up retargeting, tool error semantics.

## Goal

Two behavior shifts in specialist research:

1. Use official, statistical, government, and industry-research sources more for numbers, sizing, benchmarks, regulation, and trends.
2. Use named restaurant review sites, critics, and food bloggers more for qualitative sentiment, openings/closures, and concept reception.

Both depend on the agent knowing concrete sources per market — without treating those lists as a fence.

## Key principle — seeds, not limits

Named sources are **search seeds**, not a checklist and not a closed set. They give the agent vocabulary; the agent stays free (and is expected) to discover comparable sources.

This principle is load-bearing. Without it, naming concrete sources actively makes research _worse_: the agent fixates, narrows queries too early, and fabricates access to sources it never fetched. The evidence:

- **Anthropic** explicitly warns against laundry lists of examples; recommends 3–5 "diverse, canonical examples" (`anthropic.com/engineering/effective-context-engineering-for-ai-agents`, `docs.anthropic.com/.../multishot-prompting`).
- **Gemini docs** confirm overfitting risk: "if you include too many examples, the model may start to overfit" (`ai.google.dev/gemini-api/docs/prompting-strategies`).
- **Anthropic multi-agent research learnings**: agents "default to overly long, specific queries that return few results"; fix is "start with short, broad queries" (`anthropic.com/engineering/multi-agent-research-system`).
- **Citation hallucination is measured**: deep-research agents fabricate 3–13% of URLs (arXiv 2604.03173).

Design judgments that follow from this:

- **2–3 seeds per category** — within Anthropic's 3–5 ceiling, leaving headroom for the Lead to add task-specific examples. Exact count is judgment, not proven optimal.
- **Tell the agent to start broad, then drill** — open with category-based queries, use named seeds when narrowing.
- **Cite-only-what-you-checked is a hard rule.** Fabricated access is the most likely failure mode.

## Category taxonomy

Replace the current single "Local qualitative" bucket with eight named categories:

| #   | Category                          | What it covers                                                                     |
| --- | --------------------------------- | ---------------------------------------------------------------------------------- |
| 1   | Official & statistical            | National stats, gov open data, registries, health portals, planning bodies         |
| 2   | Industry research & benchmarks    | Trade associations, market-research firms, industry trade press, published reports |
| 3   | Restaurant review sites & critics | Editorial review platforms, named newspaper/magazine restaurant critics            |
| 4   | Food bloggers & community         | City food bloggers, Reddit/forums, Facebook groups, food newsletters               |
| 5   | Local press                       | Dailies, neighborhood publications, city magazines                                 |
| 6   | Delivery & reservation            | Public listings on platforms when accessible                                       |
| 7   | Jobs, wages & costs               | Job boards, wage surveys, commercial property                                      |
| 8   | Currency & language               | Local currency and language hints for source quality                               |

Why these splits matter:

- **#2 is currently buried** inside "Official and primary" and "Jobs and costs" (UKHospitality/NRA/DEHOGA awkwardly live there). Making it its own category surfaces the user's #1 ask.
- **#3 and #4 are separated** because editorial review platforms carry more research weight than community forums; the agent should treat them differently.

## Per-market profiles

2–3 seeds per category. Starting points for search; the agent finds the rest.

### PL — Poland

| Category                  | Seeds                                                       |
| ------------------------- | ----------------------------------------------------------- |
| Official & statistical    | GUS, CEIDG, KRS                                             |
| Industry research         | PIH, GUS sector reports, Horecanet                          |
| Review sites & critics    | Gault&Millau Polska, Michelin Guide Polska, Time Out Warsaw |
| Food bloggers & community | named city food bloggers, Reddit r/warszawa / r/krakow      |
| Local press               | Gazeta Wyborcza local editions, city magazines              |
| Delivery & reservation    | Pyszne.pl, Wolt, Glovo                                      |
| Jobs, wages & costs       | Pracuj.pl, GUS wage data, Otodom Komercyjne                 |
| Currency & language       | PLN, Polish                                                 |

### UK — United Kingdom

| Category                  | Seeds                                                         |
| ------------------------- | ------------------------------------------------------------- |
| Official & statistical    | ONS, Companies House, Food Standards Agency                   |
| Industry research         | CGA, UKHospitality, MCA Insight                               |
| Review sites & critics    | Time Out, Hardens, Observer/Guardian/Times restaurant critics |
| Food bloggers & community | London Eats, named city food bloggers, Reddit r/london        |
| Local press               | Evening Standard, neighborhood publications                   |
| Delivery & reservation    | OpenTable, Deliveroo, Just Eat                                |
| Jobs, wages & costs       | Caterer.com, ONS wage data, EG Radius                         |
| Currency & language       | GBP, English                                                  |

### US — United States

| Category                  | Seeds                                                             |
| ------------------------- | ----------------------------------------------------------------- |
| Official & statistical    | Census/ACS, BLS, county health inspection portals                 |
| Industry research         | National Restaurant Association, Technomic, Toast Industry Report |
| Review sites & critics    | Eater, The Infatuation, NYT/LA Times/SF Chronicle critics         |
| Food bloggers & community | city food Substacks, Reddit r/FoodNYC / r/AskNYC                  |
| Local press               | city alternative weeklies, neighborhood papers                    |
| Delivery & reservation    | OpenTable, Resy, DoorDash                                         |
| Jobs, wages & costs       | Poached, BLS wage data, LoopNet                                   |
| Currency & language       | USD, English                                                      |

### DE — Germany

| Category                  | Seeds                                                |
| ------------------------- | ---------------------------------------------------- |
| Official & statistical    | Destatis, regional Statistikamt, Handelsregister     |
| Industry research         | DEHOGA, Allegra DE, gv-praxis                        |
| Review sites & critics    | Michelin Guide DE, Falstaff DE, Mit Vergnügen        |
| Food bloggers & community | named city food bloggers, Reddit r/berlin / r/munich |
| Local press               | city dailies, Stadtmagazine                          |
| Delivery & reservation    | Lieferando, OpenTable, Quandoo                       |
| Jobs, wages & costs       | HOGAPAGE, Gehalt.de, ImmoScout24 Gewerbe             |
| Currency & language       | EUR, German                                          |

### Global (appended to every market)

| Category          | Seeds                                           |
| ----------------- | ----------------------------------------------- |
| Industry research | Statista, Euromonitor, Michelin Guide           |
| Review media      | Eater (international), Time Out (international) |

### Markets outside PL/UK/US/DE

Eight-category structure, no named seeds. The Lead frames the brief in terms of categories; the specialist discovers local equivalents.

## Market detection — code

**Signal**: ISO 3166-1 alpha-2 country code from Google Places `addressComponents` (entry where `types` contains `"country"` → `shortText`). Returns `PL`, `GB`, `US`, `DE` — note `GB` not `UK`.

**Two detection paths, both flowing through the enricher**:

1. **Place ID present** — country comes from the target's `addressComponents`.
2. **No Place ID, geography named** — the enricher already calls `search_restaurants` for a named restaurant + area. Use the first result's country code when no specific restaurant matches but the geography is clear.
3. **Neither** — fall back. Don't guess.

**Code changes**:

- `places_tools.py` — add `addressComponents` to `DETAIL_FIELDS` (and to `SEARCH_FIELDS` if the no-Place-ID path is to read it without a follow-up details fetch).
- `place_state.py:upsert_google_place` — extract country from `addressComponents` and store as `country_code` on the place record. **Do not write `state["target_market"]` here** — this function runs for every fetched place, including competitors, and would race the target's market against competitor countries.
- `place_state.py:set_original_target_once` — when target identity is first established, copy `country_code` from the target's record into `state["target_market"]`. Single-write, target-scoped, matches how `_target_lat`/`_target_lng` are handled.
- `agent.py:_skip_enricher_if_cached` callback or a small enricher post-callback — for the no-Place-ID path, set `state["target_market"]` from the first search result's country if no target Place ID was resolved.
- New `market_profiles.py` — `profile_for(market: str | None) -> str` returns market block + global block; or fallback block + global block if `market` is None or unknown.
- `agent.py:_research_lead_instruction` — read `ctx.state.get("target_market")`, pass through `profile_for(...)` into `.format(market_source_profiles=...)`.

**Storage**: markdown files in `instructions/market_profiles/{pl,gb,us,de,global,fallback}.md`, loaded at import time the way `agent.py` already loads templates. Keeps profile prose next to other instruction files.

**Legacy sessions** (no `target_market` written by the new code) → `profile_for(None)` returns the fallback profile. Graceful degradation. The next enricher run on a continuation will write `target_market` if it has a target.

**Why this fits ADK**: `_research_lead_instruction` is already an `InstructionProvider` (`Callable[[ReadonlyContext], Union[str, Awaitable[str]]]`). When a provider returns a string, ADK sets `bypass_state_injection=True` and skips `{var}` re-substitution — we own templating end-to-end. This is the documented primary pattern for state-driven prompts; `before_model_callback` is for post-render mutation only. (`github.com/google/adk-python/.../llm_agent.py`, `adk.dev/sessions/state/`)

## Prompting design

Three locations, each with a distinct audience and decision — not the same rule three times.

### 1. Profile header (injected into Lead via `_research_lead_instruction`)

```
## Source seeds for {market}

These named sources are search seeds, not a closed set and not a checklist.

- Start with broad category-based queries. Use named seeds when narrowing in.
- Discover comparable local sources when better ones exist.
- **Cite only sources you actually checked this turn. Never cite a named source you did not fetch or query.**
- If a named source is blocked or doesn't apply, drop it and move on.
```

The bold line is the most important guardrail. Citation hallucination at 3–13% in deep-research agents makes this load-bearing.

### 2. `research_lead.md` — Specialist Briefs

One added line:

> When a brief calls for numbers, sizing, benchmarks, regulation, or structural claims, ask the specialist to lead with official, statistical, and industry-research sources. When a brief calls for venue sentiment, openings, closures, or concept reception, ask for named review sites, critics, and food bloggers. Source seeds are starting points — encourage broad queries first.

### 3. `specialist_base.md` — Process

Specialists never see the profile directly — only the brief from the Lead. They need one minimal line about how to treat source names that appear in their brief:

> - Treat any named-source examples in the brief as search seeds, not a closed set. **Cite only sources you actually checked this turn.**

Replace the current two "Prefer…" lines with this single bullet. The category/quantitative-vs-qualitative routing now lives in the Lead's brief (location 2), not in the universal specialist contract.

### Anti-patterns to avoid

- No "be exhaustive" wording — amplifies overfitting risk.
- No per-specialist source lists in body files — `AUTHORING.md` forbids this.
- No "verify these sources exist before searching" — cost is high, win is small.

## Tests

Add to `agent/tests/`:

- Country extraction from `addressComponents` — happy path, no-country edge case, malformed response.
- `GB` not `UK` (the input from Places is ISO; the profile filename matches).
- `set_original_target_once` writes `target_market`; subsequent `upsert_google_place` calls for competitors do **not** overwrite it.
- Legacy session (no `target_market` in state) → `profile_for(None)` returns fallback.
- `_research_lead_instruction` returns the right profile block for each market.
- No-Place-ID + named-geography path writes `target_market` from search.

Run with `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` per the existing project test command.

## Shipment

Ship as one change: profile restructure, market resolution code, prompt edits in `research_lead.md` and `specialist_base.md`, tests. Splitting would let profile selection improve without the Lead-brief wording that pushes source expectations to specialists — defeats the point.

## Open decisions

1. **Storage format** — markdown per market (recommended) vs Python dict.
2. **No-Place-ID path** — confirm the enricher's existing search result carries `addressComponents`, or add it to `SEARCH_FIELDS`. Likely the latter.
3. **Naming** — `target_market` as the state key. ISO alpha-2 as the value (`GB`, not `UK`).

## References

ADK / Vertex AI Agent Engine:

- `github.com/google/adk-python/blob/main/src/google/adk/agents/llm_agent.py` — `InstructionProvider` type alias
- `adk.dev/sessions/state/` — state prefixes; `InstructionProvider` for state-driven prompts
- `adk.dev/agents/llm-agents/` — `{var}` interpolation behavior
- `adk.dev/callbacks/` — `before_model_callback` semantics

Gemini / Google Places:

- `ai.google.dev/gemini-api/docs/prompting-strategies` — overfitting warning
- `ai.google.dev/gemini-api/docs/google-search` — grounding cannot be biased toward named domains via prompt
- `developers.google.com/maps/documentation/places/web-service/data-fields` — `addressComponents` field schema

Prompting research:

- `anthropic.com/engineering/effective-context-engineering-for-ai-agents` — "diverse, canonical examples"
- `anthropic.com/engineering/multi-agent-research-system` — "start with short, broad queries"
- `docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/multishot-prompting` — 3–5 examples
- arXiv 2410.01288 — copy bias in ICL
- arXiv 2604.03173 — 3–13% URL fabrication in deep-research agents

Project context:

- `agent/superextra_agent/instructions/AUTHORING.md`
- `agent/superextra_agent/agent.py:51-70` — current `_research_lead_instruction`
- `agent/superextra_agent/places_tools.py:33-58` — current `DETAIL_FIELDS`
- `agent/superextra_agent/place_state.py:147-161` — current `set_original_target_once`
- `docs/agent-adjacent-streams-plan-2026-05-11.md` — parent Stream 2.3
