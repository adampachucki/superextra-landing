# Superextra — data sources & tools research

**Date**: 2026-05-14
**Scope**: What tools and data sources could make Superextra more valuable to restaurant operators — Apify, SerpAPI, public APIs, agent grounding patterns, plus live smoke tests against Monsun (Gdynia) and Umami P-Berg (Berlin).

A walkthrough of everything covered, in the order it happened. Read top-to-bottom; the last sections are what's actionable.

---

## 0. What we set out to figure out

The question: _what tools and data sources could we use to make Superextra more valuable to restaurant operators?_ Specifically — what could we get from Apify and SerpAPI beyond what we use today, what other sources should we look at, and how should we be giving the agent better context.

The work happened in three phases: a wide research sweep (five parallel agents reading docs), an architectural Q&A based on what the team flagged interesting, and ten live smoke tests against real targets — Monsun (seafood, Gdynia) and Umami P-Berg (Vietnamese, Berlin).

---

## 1. Where we started — what the agent uses today

Reading the codebase confirmed a small baseline:

- **Google Places API** (`agent/superextra_agent/places_tools.py`) — restaurant profile, nearby search, basic reviews.
- **Apify**, exactly one actor (`agent/superextra_agent/apify_tools.py`) — `compass/google-maps-reviews-scraper`, used only by the review_analyst.
- **SerpAPI**, exactly three engines (`agent/superextra_agent/tripadvisor_tools.py`) — `tripadvisor`, `tripadvisor_place`, `tripadvisor_reviews`. Capped at 100 reviews per place (10 pages × 10).
- **Jina Reader** (`agent/superextra_agent/web_tools.py`) — generic "fetch URL as clean Markdown."
- **Google Search** (Gemini-native) — geo-biased via `_inject_geo_bias` in `specialists.py:128`.

That's it. The nine specialists answer everything else by free-text web search, which is fine for some questions and a serious bottleneck for others.

The topic-pill questions on the landing page span eight categories: market sales shifts, site selection, concept validation, wage benchmarking, price positioning, sentiment trends, competitor tracking, market shifts. Several of these — foot traffic, wages, delivery-platform pricing — are hard or impossible to answer well from generic search.

---

## 2. Phase 1 — five research streams

Five subagents ran in parallel, each focused on a different angle.

### 2.1 SerpAPI engines beyond TripAdvisor

The catalog showed 10+ engines that map cleanly to our specialists:

- **`google_trends`** — interest-over-time at DMA/region granularity. Demand proxy for cuisines, dishes, formats.
- **`open_table_reviews`** — the only API in market that returns food/service/ambience/value/noise subratings as first-class fields. Genuinely diagnostic.
- **`google_jobs`** + **`google_jobs_listing`** — wage benchmarking.
- **`google_news`** — date-sorted local press for openings/closures.
- **`google_maps`** — exposes popular_times and service options that the Places Web Service doesn't.
- **`google_maps_reviews`** — could replace the Apify GMB reviews path.
- **`google_maps_photos`** with `category_id=menu` — pulls photos Google has tagged as menu.
- **`google_events`** — weekend-of demand spikes near a location.
- **`google_ads_transparency_center`** — when a competitor turns on ads, what creatives, which regions.
- **`yelp` / `yelp_reviews`** — US/CA second axis on competitors and sentiment.
- **`google_forums`** — Reddit + Quora aggregated.
- **`google_maps_posts`** — competitor's Google Business Profile promo calendar.

Pricing is flat: $25/1k searches at the $25 tier, going down per call at higher tiers.

### 2.2 Apify actors beyond the one we use

The catalog identified one obvious upgrade and several useful additions:

- **`compass/crawler-google-places`** — 405K runs, $2.10/1k places. Returns popular_times histograms + live occupancy + reviews + competitors + ops metadata in one call. Replaces our reviews-only actor and adds three other capabilities. Single highest-leverage swap.
- **`apify/instagram-scraper`** — 127M runs, official Apify. Posts + profile + comments.
- **`clockworks/tiktok-scraper`** — 81M runs, Apify-maintained.
- **`trudax/reddit-scraper-lite`** — 3M runs.
- **`maxcopell/tripadvisor`** + **`maxcopell/tripadvisor-reviews`** — 4.3M + 6.9M runs. The reviews actor reportedly bypasses the SerpAPI 100-review cap.
- **`misceres/indeed-scraper`** — 1.4M runs, covers 60+ Indeed country domains.
- **`easyapi/stepstone-jobs-scraper`** — 54K runs, best volume for DE wages.
- **`easyapi/google-news-scraper`** — duplicate of the SerpAPI engine, pick one.
- **`borderline/uber-eats-scraper-ppr`** — 83K runs, US-dominant.

**Real gaps**: no production-grade Apify actor exists for **Pyszne.pl, Lieferando.de, or Bolt Food** — our three home-market delivery platforms. The deep-research note flagged this as a "build a custom thin scraper" decision.

### 2.3 Public + commercial data APIs by market

The standout findings — sources you can hit directly via REST today, no contracts needed:

- **Statistical offices**: GUS BDL (PL), ONS Beta + Nomis (UK), Census + BEA + BLS (US), Destatis Genesis (DE), Eurostat (cross-EU comparator).
- **Business registries**: Companies House (UK) — free, 600 requests/5min, real-time new restaurant filings. CEIDG v3 + KRS Open API (PL). OpenCorporates (US) as a single facade. OpenRegister (DE) is paid.
- **Weather**: **Open-Meteo** — global, no key, 10k free daily calls, 80-year history. Clear default.
- **Events**: **Ticketmaster Discovery API** — free, 5k/day, covers PL/UK/US/DE. (Eventbrite's search API is deprecated — skip it.)
- **Crime/safety**: data.police.uk (UK) and FBI CDE (US). PL/DE have no equivalent open APIs.
- **Hygiene scores**: FSA FHRS (UK), NYC + Chicago Socrata (US). Not available for PL/DE.
- **Transit + walkability**: Overpass (OpenStreetMap) and Transitland v2 — both free.
- **Property**: HM Land Registry SPARQL (UK). Eurostat NUTS regional income (EU).
- **Foot traffic** — universally gated. BestTime.app ($9–$200/month) is the only cheap path. Placer.ai is $15k+ enterprise; even at that price, PL/DE coverage is thin.

### 2.4 Competitor restaurant-intel tools — where the moats are

Surveyed 15 commercial vendors. Five categories of insight are genuinely hard to recreate from public scraping:

1. **POS transaction data at scale** (Toast, Olo, Square) — bundled with their SaaS, not separately licensable.
2. **Wage/turnover by role × geography** (Black Box Intelligence, 7shifts) — enterprise contracts only.
3. **Consumer-reported occasion data** (Circana CREST) — six-figure subscriptions.
4. **True foot-traffic share-of-visits** (Placer.ai) — has a real API, but enterprise pricing.
5. **Longitudinal menu time-series** (Datassential MenuTrends) — 7-year curves we can't recreate.

A surprise positive: **Tripadvisor Content API gives 5,000 calls/month free**, multi-language, multi-country — best bang-per-buck commercial restaurant API in market, capped at 5 reviews per place.

A pragmatic conclusion: an agent built on public web + the additions above + Tripadvisor Content API + parsed quarterly trade reports (Toast/Square/DoorDash/MRM Research Roundup/CGA/NRA/Technomic) can credibly cover ~70% of operator questions. Site selection and wage benchmarking are the clearest "partner, don't build" cases.

### 2.5 Agent grounding patterns from 2025–2026 literature

The honest TL;DR: a few low-effort architectural changes are higher-leverage than any new data source. Ordered by leverage:

1. Pydantic-typed tool results + structured `claims` blocks (foundation for everything else).
2. Firestore tool cache with TTLs — wraps four call sites, dramatic latency/cost win.
3. Centralized `QueryPlan` from research_lead — ParallelSearch (2025) showed 30% fewer LLM calls and +12.7% on parallelizable questions.
4. Vertex AI's "Grounding with Google Maps" tool — direct POI search against Google's 250M-place index.
5. Structured-data adapters where free-text search currently substitutes (demographics, delivery listings).
6. Pre-run environment snapshot (local news, weather/seasonality, trade-area POI summary).
7. Visual inspect tool (screenshot → Gemini vision) for menu/IG/delivery layouts.
8. Provenance by `evidence_id` — citations the operator can audit.

The citation problem is real: "Cited but Not Verified" (Dec 2025) ran 14 commercial deep-research agents and found citation accuracy in the 39–77% range across every provider.

---

## 3. Phase 2 — architecture questions, answered

Five items from the synthesis (C.1, C.2, C.3, C.7, C.8) plus Placer alternatives (D).

### C.1 — Pydantic-typed tool results + claims block

**Today** every tool returns a free-form dict; the model sees raw JSON each time. **With Pydantic**, the same call returns a typed object — same data, contract enforced. ADK uses Pydantic natively; this is a refactor, not a new dependency.

The claims block is the bigger half. Today a specialist writes prose: _"Monsun has a 4.5 rating from 800 reviews."_ We have no way to know if that came from a tool call or if the model invented it.

With claims, the specialist emits a structured list alongside the prose: each claim has its text plus a list of evidence IDs (e.g. `places.ChIJxyz`) that back it. The report writer renders the prose from these claims; it can't reference an evidence ID that doesn't exist.

**Why bother**: same reason a database schema beats untyped JSON. Field drift caught at the boundary, not three calls deep. And it's the foundation for real citations (C.8).

### C.2 — Firestore tool cache, why

Three concrete wins:

1. **Speed.** Within a session, the same restaurant gets re-fetched many times — router peek, context_enricher, research_lead briefing, several specialists. Each call is 100–500ms (Places) to 30–90s (Apify cold start). Cache hits = free + instant.
2. **Cost.** Apify is metered per result; SerpAPI per call; Places per field-mask combination. Restaurants don't move every 24 hours — re-paying is waste.
3. **Reliability.** When SerpAPI rate-limits or Apify has a slow run, the cache still answers.

TTL keyed to volatility, not source: addresses 30 days, reviews 24h, menu prices 24h, hours 7 days. Firestore has native TTL — set `expiresAt`, Firestore deletes it. Zero ops overhead.

### C.3 — QueryPlan, how it works

**Today** research_lead writes a paragraph brief for each specialist; each specialist reads the paragraph and decides which searches to run. Nine specialists running in parallel = nine independent re-decompositions of the same operator question.

**With a QueryPlan**, research_lead emits a structured plan once: per specialist, a list of `{sub_question, queries, expected_evidence_type}`. Specialists execute the plan rather than re-deciding what to search for. The coverage check becomes mechanical — for each sub-question, is there a citation-backed sentence answering it? Re-dispatch only the missing ones.

Literature behind it (ParallelSearch, GAP, VMAO — all 2025): same quality answers with ~30% fewer LLM calls.

### C.7 — Menu photos via Google Maps

Yes, two clean paths:

- **SerpAPI `google_maps_photos`** with `category_id=menu` — Google already tags photos as menu/food/interior/vibe.
- **Apify `compass/crawler-google-places`** returns all photos with category tags.

Then `visual_inspect(image_url, "extract menu items and prices")` runs the image through Gemini vision. Gemini 3 is genuinely strong at this — chalkboard menus, scanned PDFs, photographed pages.

**Why it matters**: many small independents, especially in PL/DE, never publish their menu online. The only menu that exists publicly is a photo a customer took. Today `menu_pricing` punts on these places.

### C.8 — Provenance / evidence IDs

The setup: every tool result gets a unique ID. Every claim in a report carries a list of evidence IDs it depends on. The report writer renders prose by looking up the ID → source-URL map. It never invents a URL.

**Why operators care**: today they read _"Monsun's most common complaint is slow service (source: google.com/maps)"_ and can't audit it. With evidence IDs, the same line links back to a specific tool call: _"Apify Google Reviews dataset of 50 reviews, 9 of which mention wait time."_ They can click and verify.

**Why we care**: the "Cited but Not Verified" paper found 39–77% citation accuracy across all commercial deep-research agents. Models cite URLs that don't support the claim. The structural fix is to make the model unable to cite anything that wasn't an actual tool result this session.

### D — Placer alternatives under $15k

Honest answer first: **Placer's PL/DE coverage is thin anyway** — even at $15k you'd get great US, decent UK, almost nothing in your home markets. So this isn't "Placer vs. cheaper alternatives", it's "what foot-traffic signal can we get at all in PL/DE/UK at low cost?"

Ranked:

1. **BestTime.app** — $9/month entry, $200/month for serious use. Real REST API. Works globally. Forecasts popular-times curves week-ahead. Realistic cheap path.
2. **Google Popular Times via `compass/crawler-google-places`** — already comes free with the Apify swap. Histograms by hour-of-day plus live occupancy.
3. **OSM Overpass POI density** — proxy: how many anchors (transit, schools, offices) within 500m. Free.
4. **Hystreet.com** (DE only) — physical foot counters on major shopping streets. Public dashboards, no API.
5. **Huq Industries** (UK + EU) — Placer-like but smaller. Enterprise pricing but reportedly lower floor.

For ~80% of foot-traffic questions Superextra would credibly answer, BestTime + Apify popular times + Overpass density covers it. Placer is only worth chasing when an enterprise customer asks for site selection.

---

## 4. Phase 3 — ten live smoke tests

Two real targets, real API calls, raw outputs saved in `/tmp/superextra-tests/`. Results in order:

### 4.1 `compass/crawler-google-places` — ✅ ship

~12s/place at `maxReviews=20`, scales to ~55s/place at `maxReviews=200` ($0.106/place at production scale). Verified both targets returned exactly 200 reviews; we have ~65s headroom on the 120s httpx timeout. **Popular times confirmed live** for both Monsun and Umami — full 7-day × 24-hour histograms. Surprises beyond what the research promised:

- **`reviewsTags`** — Google's pre-aggregated theme counts (Umami: `vegetarian options: 119, terrace: 22, seitan: 20`). Saves a lot of LLM tokens reasoning over raw text.
- **`reviewsDistribution`** — per-star buckets, structured (Umami: 115 / 57 / 170 / 1049 / 3277 across 1–5★).
- **`peopleAlsoSearch`** — 5 competitors per place with ratings.
- **`reviewDetailedRating`** per review — Food / Service / Atmosphere subratings. Same structure we'd flagged OpenTable as uniquely having; turns out Google exposes it just not via Places API.

One actor now feeds three specialists (`review_analyst` + `location_traffic` + `market_landscape`).

**Caveat from bigger test**: the actor returns photos as a flat `imageUrls` array — **NOT categorized by Google's photo tabs (Menu, Food, Vibe, etc.)**. Apify product docs confirm there's no way to filter image scraping by category. So menu photos still need a separate path (SerpAPI `google_maps_photos` — see 4.2). Production defaults: `maxReviews=200, maxImages=20`.

### 4.2 Six SerpAPI engines

| Engine                           | Verdict           | Real result                                                                                                                                                                                                     |
| -------------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `google_trends`                  | ✅ Wire in        | Umami Berlin last 4w: 61, 71, 52, 62 (out of 100). Subregional codes work (`DE-BE`, `PL-PM`).                                                                                                                   |
| `google_news`                    | ✅ Wire in        | Umami: 9 articles incl. "10 Jahre Umami in Berlin" celebratory piece. Independents get 0–3 hits.                                                                                                                |
| `google_maps_photos` (menu)      | ✅ Wire in        | 20 menu photos each, paginated. Two-call pattern: `google_maps` → `data_id` → `google_maps_photos`.                                                                                                             |
| `open_table_reviews`             | 🟡 Wire in, gated | Real subratings (basta-berlin: overall 4.6, food 4.6, service 4.6, ambience 4.7, value 4.1). BUT Monsun, Umami, Rutz, Tim Raue all unlisted on OpenTable. Gate by `reserveTableUrl` containing `opentable.com`. |
| `google_ads_transparency_center` | 🟡 Chains only    | SMB empty. `mcdonalds.pl` 5,000 creatives, `lieferando.de` 50,000, `pyszne.pl` 20,000.                                                                                                                          |
| `google_jobs`                    | ❌ Skip           | **Zero PL coverage**. DE: 10% salary fill rate. Stats portals + Indeed scraper are the path.                                                                                                                    |

### 4.3 `apify/instagram-scraper` — ✅ ship

Monsun: 4,675 followers, 30 posts, avg 43 likes (0.91% engagement). Umami: 12,327 followers, 30 posts, avg 166 likes / 17 comments (1.34% engagement). Schema correction: input is `directUrls`, not `username`. ~$2.30/1k.

### 4.4 `borderline/uber-eats-scraper-ppr` — ✅ ship for PL/DE (surprise)

The deep-research conclusion was wrong. **Gdynia**: 19/20 real restaurants, 83 menu items avg/store, PLN. **Berlin**: 19/20 real restaurants, 64 items avg/store, EUR. **US/UK** controls came back contaminated by Uber Eats' grocery/convenience push (only 2/20 had real menus). PL/DE work _better_ than US/UK with a naive query.

Bolt Food and Pyszne — both confirmed: no Apify actor, both need custom paths (Bolt is pure SPA → headless browser; Pyszne ships parseable `__NEXT_DATA__` JSON but needs proper schema inspection).

### 4.5 BestTime.app — ✅ ship

Both targets forecasted successfully on first try. Full 7-day × 24-hour curves, peak/busy/quiet/surge windows, `venue_dwell_time_avg`. Free tier: 100 forecasts + 100 queries.

Triangulation value: at the same moment, Apify scraped Monsun as "43% busy" while BestTime live said "5" — likely because Monsun is closed Mon/Tue and Apify's widget showed stale weekend data. Having both lets us flag this kind of disagreement.

### 4.6 Public statistical APIs — partially good, one correction needed

- **GUS BDL** (PL) — works fine. Concrete: Gdynia 2024 avg gross monthly wage **8,999.18 PLN**, population **240,084**. Undocumented `unit-parent-id` quirk — using `unit-id` returns the national total instead. Gmina is the floor; Gdynia is one administrative unit.
- **Eurostat** — works. Berlin 2023 GDP/capita **€54,700** vs Tricity **€30,100**, Berlin density 4,343/km² vs Tricity 1,855/km². NUTS 3 floor; cross-EU comparator.
- **Destatis Genesis** (DE) — **deep-research note was wrong about GAST/GAST.** It returns 401 on every data endpoint. A free named-account registration is required. Once registered, Pankow-level Regionalstatistik is reachable. **Action**: register at `https://www-genesis.destatis.de/genesis/online?Menu=Anmeldung` and drop the credentials into `agent/.env`.
- For true neighborhood data (1km radius around the venue): not from REST. Bulk products exist (BDL 1km² grid CSV, German Zensus 2022 100m grid parquet). Defer until neighborhood becomes the wedge.

### 4.7 Vertex AI Grounding with Google Maps — ✅ ship

Works first-try on `gemini-3.1-pro-preview` at `location="global"`. **$25 / 1,000 grounded prompts** (vs $35 for Search grounding). 5,000/day cap on 3 Pro.

Returns the citation surface natively: `grounding_chunks` with stable `places/ChIJ…` IDs, `grounding_supports` mapping every text span to the chunk that backs it, plus `retrieval_queries` showing the model's actual sub-queries. The same `RetrievalConfig.lat_lng` we already inject for `google_search` works here too.

Complementary to `find_nearby_restaurants`, not a replacement: only 2–3 of 20 nearby places overlapped with grounded chunks. Keep both — Places nearby for geometry-bounded census, grounding tool for curated narrative answer.

### 4.8 `maxcopell/tripadvisor-reviews` (post-approval) — ✅ ship as replacement

**300 reviews in one ~55s call** for Umami, 8 years of history (Feb 2018 → Mar 2026). The 100-review SerpAPI ceiling is gone. Cost ~$1.52/1k observed (advertised $0.90/1k). Strict schema superset of SerpAPI's, plus **owner responses, author location, author contribution counts, place histogram bundled**. Input field is `maxReviews`.

**Replace the SerpAPI TripAdvisor path entirely.** Don't keep both — SerpAPI's engine is strictly dominated.

### 4.9 Quandoo + TheFork — 🟡 inconclusive (test killed)

What we learned from the partial data:

- **Quandoo** via `clearpath` actor: returned 50 popularity-sorted Berlin restaurants. **Umami P-Berg was not in the top 50.** Either we needed a name-search input we didn't try, or Quandoo doesn't index Umami.
- **TheFork** via `jdtpnjtp/thefork-restaurant-intelligence-scrapper`: most attempts returned `[]`. One run eventually returned 50 nearby-Berlin records (`Tex Mexico`, `Mizumi`, `Maison Saveur`, ...) — but no Umami match.

Both actors are too flaky to wire in today. For DE booking-platform data, this needs real engineering, not a smoke test.

### 4.10 `easyapi/stepstone-jobs-scraper` — ❌ doesn't deliver wages (test killed)

Real data from the partial run:

| Query                           | Returned            | `salary` field set | Parseable salary        |
| ------------------------------- | ------------------- | ------------------ | ----------------------- |
| Koch, Berlin                    | 0 (stochastic miss) | —                  | —                       |
| Servicekraft Restaurant, Berlin | 50                  | 44/50              | **0/50** (fill rate 0%) |
| Küchenchef, Berlin              | 0 (stochastic miss) | —                  | —                       |

Two fatal problems: the actor is **stochastically empty** (same query, sometimes 50, sometimes 0), and the `salary` field is **decorative** — present but never parseable. StepStone shows salary in free-text descriptions, not structured fields.

Don't wire it in as-is. DE wages need Destatis as the authoritative anchor + LLM-parsed salaries from job-description body text via Indeed scraper.

---

## 5. The integration-ready bundle (revised 2026-05-14 after follow-up tests)

After the bigger crawler test + menu-photo comparison + your pushback, the tier list is sharper:

**Tier 1 — ship the next time there's a sprint slot**

1. **`compass/crawler-google-places`** — replaces existing reviews-only actor. 200 reviews + popular times + reviewsTags + peopleAlsoSearch + per-review subratings + 20 generic hero photos in one ~55s call for ~$0.13. Feeds three specialists. **Photos are NOT categorized** — menu photos need a separate tool (Tier 2).
2. **Pydantic typed tool results + Firestore TTL cache + evidence IDs** — the architectural foundation. ~1 week of work; unlocks everything downstream.
3. **`maxcopell/tripadvisor-reviews`** replaces the SerpAPI TripAdvisor path. Delete `get_tripadvisor_reviews`'s pagination loop while in there. (Plan in `docs/tool-integrations-plan-2026-05-14.md`.)

**Tier 2 — worth doing, lower priority**

4. **SerpAPI `google_trends`** for `market_landscape` demand signals. (Plan ditto.)
5. **SerpAPI `google_maps_photos`** (menu category) — dedicated menu-photo tool. SerpAPI won the head-to-head (4× faster than Apify alternatives). Foundation for menu OCR via `visual_inspect`. (Plan ditto.)
6. **`apify/instagram-scraper`** for `marketing_brand` + competitor cadence.
7. **`borderline/uber-eats-scraper-ppr`** for PL/DE menu pricing (PL/DE return restaurant-first data; US/UK need post-filtering).
8. **Vertex AI Grounding with Google Maps** — wire alongside `find_nearby_restaurants`, let model decide. Three specialists (`context_enricher`, `market_landscape`, `location_traffic`). (Plan ditto.)

**Tier 3 — free public APIs to bundle into a `get_geo_features(lat, lng)` tool**

9. **Open-Meteo** (weather, historical + forecast).
10. **Ticketmaster Discovery** (events, free 5k/day).
11. **Overpass + Transitland** (POI anchors + transit density).
12. **GUS BDL** (PL demographics) + **Eurostat** (cross-EU comparator) + **Destatis Regionalstatistik** once registered.
13. **Companies House** (UK) — separate adapter for restaurant openings/closures + filings.

**Skip outright**

- SerpAPI `google_news` — 70% redundant with the Gemini-native `google_search`; modest upside not worth the wire-in.
- SerpAPI `google_jobs` (zero PL coverage, 10% DE salary fill).
- BestTime.app — adds only `venue_dwell_time_avg` over the crawler's popular times; not worth wiring unless dwell-time questions come up.
- `easyapi/stepstone-jobs-scraper` (stochastic empties, salaries unparseable).
- Quandoo + TheFork actors (too flaky in current state; come back when DE booking-platform data becomes a wedge).
- Placer.ai (enterprise pricing, weak PL/DE coverage anyway).

**Genuine gaps no scraper can fill**

- POS transaction data at scale (Toast/Olo/Square moats).
- Wage/turnover by role × geography from real payroll (Black Box).
- Consumer-reported occasion data (Circana CREST).
- Foot-traffic share-of-visits (Placer's actual product).
- Longitudinal menu time-series (Datassential MenuTrends).

These are all "partner, don't build" if a customer ever needs them.

---

## 6. Open decisions

1. **Destatis Genesis registration** — pending registration at `https://www-genesis.destatis.de/genesis/online?Menu=Anmeldung`. Once done, drop `DESTATIS_USER` + `DESTATIS_PASSWORD` into `agent/.env` and a 5-minute test verifies Pankow-level Regionalstatistik.
2. **Quandoo + TheFork** — out of smoke-test scope. If DE booking-platform data becomes a wedge, this becomes a proper integration project — name-search input on Quandoo + headless-browser scraping for TheFork's per-place pages.
3. **DE wage benchmarking path** — if `operations` pills become a wedge, the path is Destatis (anchor) + `misceres/indeed-scraper` (specific postings) + LLM salary parsing from description body text. Not StepStone.
4. **Custom Pyszne.pl / Bolt Food / Lieferando scrapers** — only if PL/DE menu pricing becomes a wedge. Pyszne's `__NEXT_DATA__` is parseable with proper schema inspection; Bolt needs headless browser.

All artifacts (scripts + raw JSONs) sit in `/tmp/superextra-tests/` if anyone wants to dig in.

**Concrete wiring plans** for Tier 1 + 2 items live in `docs/tool-integrations-plan-2026-05-14.md`:

- `google_trends` — new `trends_tools.py` module, exposed to `market_landscape` + `marketing_brand`
- `google_maps_photos` (menu) — new `serpapi_tools.py` module, exposed to `menu_pricing`
- Maps Grounding + Places — extend `_make_specialist()` with an `enable_maps_grounding` flag, three specialists get it, instructions tell the model which to pick
- `maxcopell/tripadvisor-reviews` — rewrite `get_tripadvisor_reviews()` body, keep `find_tripadvisor_restaurant()`, delete pagination loop

---

## Appendix — file paths and artifacts

**Code referenced**:

- `agent/superextra_agent/apify_tools.py` — current Apify integration (Google reviews actor)
- `agent/superextra_agent/places_tools.py` — Google Places API integration
- `agent/superextra_agent/tripadvisor_tools.py` — SerpAPI TripAdvisor integration
- `agent/superextra_agent/web_tools.py` — Jina Reader integration
- `agent/superextra_agent/specialists.py` — specialist construction + tool wiring
- `agent/superextra_agent/specialist_catalog.py` — specialist roster
- `agent/superextra_agent/instructions/*.md` — per-specialist briefs
- `src/lib/components/restaurants/TopicPills.svelte` — landing page topic pills

**Smoke test artifacts** (in `/tmp/superextra-tests/`):

- `crawler_places.py` + `monsun_crawler.json` + `umami_crawler.json`
- `serpapi_engines.py` + per-engine `0{1..6}*.json`
- `apify_ig_ta.py` + `monsun_ig.json` + `umami_ig.json` + `umami_ta_search.json`
- `ubereats_coverage.py` + `ubereats_{gdynia,berlin,new_york,london}.json`
- `besttime.py` + `besttime_{monsun,umami,keys,search}.json`
- `demographics.py` + `bdl_*.json` + `eurostat_*.json` + `destatis_*.json`
- `vertex_maps_grounding.py` + `vertex_maps_{monsun,umami_pberg}.json`
- `tripadvisor_reviews_verify.py` + `umami_ta_reviews_apify.json`
- `stepstone_wages.py` + `stepstone_*.json`
- Quandoo + TheFork artifacts under `quandoo_*.html`, `*_thefork.json`
