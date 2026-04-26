# Review of `docs/research-depth-proposal.md`

Reviewed on 2026-04-23 against the current repo state and current external documentation.

## Bottom line

The proposal identifies a real failure mode: monoculture sourcing plus unsupported references is a credibility problem for a research product.

The strongest parts are:

- adding a post-synthesis claim/citation verification step
- adding explicit source-diversity evals
- making source-broadening behavior more concrete than "be thorough"

The weakest parts are:

- a few factual overstatements about Google Places
- the assumption that specialist-instruction changes alone are the main missing piece
- an overly absolute rejection of lightweight source priors
- coupling claim verification with Places source-pill attribution, which should be solved lower in the stack

My recommendation is to keep the proposal's direction, but tighten it into a three-part plan:

1. stronger evidence-lane prompts plus light orchestration constraints
2. deterministic or highly constrained claim-support validation before publish
3. telemetry and evals that measure monoculture directly

## What checks out

### 1. The core product diagnosis is valid

A single-domain-heavy answer with unsupported named references is a real quality issue. The current pipeline can produce that shape because:

- most specialists still rely on `google_search` + `fetch_web_content`
- source diversity is encouraged, but not operationalized
- the final synthesizer is told to preserve citations, but there is no final claim-support audit

That is consistent with the current repo structure in:

- `agent/superextra_agent/instructions/specialist_base.md`
- `agent/superextra_agent/instructions/market_landscape.md`
- `agent/superextra_agent/instructions/research_orchestrator.md`
- `agent/superextra_agent/instructions/synthesizer.md`

### 2. Anthropic really does use a citation-verification layer

Anthropic's published multi-agent research architecture includes a final citation-verification stage. That makes the proposal's "CitationAgent-like" step directionally sound. This is the strongest part of the document because it targets a concrete failure mode: unsupported claims introduced late in the pipeline.

### 3. Google Places is weak for closure history

This is directionally correct. Current Google docs support several important caveats:

- `businessStatus` exists, including `CLOSED_PERMANENTLY`
- moved businesses can also surface through `movedPlace` / `movedPlaceId`
- obsolete or invalid place IDs can return `NOT_FOUND`

That means Places is useful as a status signal, but not a reliable historical memory system for "what closed in the last 12 months?"

## Corrections and caveats

### 1. "No explicit multi-source mandate, no diversity audit" is not true in the current repo

As of the current codebase, there is already source-diversity guidance in three places:

- `specialist_base.md` tells specialists to vary query types and reformulate when sources cluster
- `research_orchestrator.md` includes a "Source diversity" principle
- `gap_researcher.md` explicitly audits whether findings rely on one source type and treats monoculture as a gap

So the gap is not "source diversity is absent." The gap is:

- the guidance is generic rather than question-specific
- there is no measurable stop condition
- there is no downstream validator that blocks unsupported synthesis

That matters, because otherwise the proposal sounds greener-field than it actually is.

### 2. The Places result-limit claim is wrong for this codebase

The proposal says Nearby Search ranks by prominence and caps at 60 results. That is not the API path this repo uses.

Current repo state:

- `agent/superextra_agent/places_tools.py` uses Places API (New)
- `find_nearby_restaurants()` calls `places.searchNearby`
- the request hardcodes `maxResultCount: 20`
- the request hardcodes `rankPreference: "DISTANCE"`

Current Google documentation for Places API (New) also documents `maxResultCount` in the `1..20` range for `searchNearby`.

So the correct critique is not "Places caps at 60 and ranks by prominence." It is:

- this implementation currently inspects only up to 20 nearby results per call
- it is distance-ranked, not prominence-ranked
- even if widened, Places is still not a historical closure database

### 3. The closure argument is directionally right but too confident in one spot

The proposal claims that closed places rank lower and fall off. I did not find an official Google source that documents that as a guaranteed ranking behavior.

What the docs do support:

- a place can be `CLOSED_PERMANENTLY`
- a moved venue can also appear closed and point to a new place via `movedPlace`
- an obsolete place ID can become invalid

What the docs do not cleanly support:

- a general ranking rule you can cite as fact for why closed venues disappear from nearby search

Recommendation: keep the high-level conclusion, but narrow the wording. "Places is not reliable as a closure-memory system" is defensible. "Closed venues rank lower and fall off" is too specific unless you have product telemetry proving it.

### 4. "Earliest review ~= opening date" is too weak as written

This is the biggest factual issue in the proposal.

Google's Places resource docs state that Place Details returns at most 5 reviews, sorted by relevance. That makes "earliest review date" from Places a very weak opening-date proxy.

Implications:

- it can be a heuristic
- it should not be treated as a strong signal
- if review chronology is used at all, it should come from the Google Reviews tool or another source with a larger time window

The repo's own current Places usage reinforces this problem:

- `get_restaurant_details()` fetches `reviews`
- but Places review payloads are limited and relevance-sorted
- meanwhile `get_google_reviews()` in `apify_tools.py` can fetch up to 200 reviews, but currently sorts by newest

So the practical recommendation is not "surface review freshness from Places." It is "if opening recency matters, fetch real review history explicitly and label it heuristic."

### 5. The rejection of source priors is too absolute

The document argues that giving source lists or country-aware platform hints would anchor the model and narrow exploration. That risk is real, but the conclusion is too broad.

Two current public references point the other way:

- Anthropic says subagents improved when given more specific prompts, including tool and source guidance.
- OpenAI's deep research guidance explicitly supports prioritizing preferred websites while still searching broadly.

So the better distinction is:

- bad: hardcoded ceilings and exhaustive platform directories
- good: soft priors, seed categories, exemplar domains, and "go beyond this if needed"

For this product and domain, "delivery platforms, booking platforms, local press/community, maps/listings" is not an unbounded ontology. It is a bounded restaurant-research surface with country variation.

That makes a small soft-prior layer practical.

### 6. "Generic fetch works for most URLs" is optimistic

Locally, `fetch_web_content()` is a Jina wrapper with a 15k-character cap. That is a useful generic tool, but not evidence that it works reliably across:

- JS-heavy platform pages
- login-walled content
- anti-bot flows
- highly structured pages where the useful signal is not in the rendered article text

I agree with "do not build a large scraper matrix first." But I would not accept "generic fetch works for most URLs" as a proven premise.

The right pragmatic move is telemetry:

- track fetch failures by domain
- track truncation by domain
- track how often a lane is attempted but unreadable

Only then decide which domains deserve thin adapters.

## Architectural assessment

### The proposal is right about one thing: the current behavior is under-specified

`market_landscape.md` currently says "go deeper: search for recent openings/closings, news coverage, industry reports, local food media." That is directionally fine, but too open-ended for a high-stakes breadth problem.

The model needs a more explicit search pattern.

### But specialist instructions alone are not enough

This is where I disagree most with the proposal.

The document says source-category planning belongs in specialist body files rather than the orchestrator. I think the correct split is:

- specialist files own the default domain logic
- orchestrator briefs own query-specific coverage requirements

Why:

- the orchestrator knows this query is specifically about recent openings/closures
- the orchestrator already decides how many specialists to call and what each one should exclude
- recent-opening/closure questions are special enough to justify extra coverage constraints

So I would not move source planning entirely into one layer. I would split responsibility.

### Recommended pattern: evidence lanes, not just source categories

Source categories are useful, but claim quality improves more if the model reasons in evidence lanes.

For "what opened or closed nearby recently?", I would define lanes like:

1. local memory sources
   - local press
   - local food media
   - forums / community threads

2. active consumer-platform presence
   - Google Maps
   - delivery apps
   - booking/listing platforms
   - official website/social presence

3. status-change signals
   - `businessStatus`
   - `movedPlace`
   - site gone / booking disabled / delivery listing removed

This is better than generic "3-5 source categories" because it maps directly to claim quality.

Example rule:

- do not label a venue "closed" from one forum thread alone
- require either:
  - one memory source plus one status/source-of-truth signal, or
  - one official/direct closure announcement

That is more operational than "broaden if one domain dominates."

### Recommendation: separate discovery, validation, and attribution

The proposal currently uses the citation-verification step to also justify Places source injection. I would split those concerns:

### Discovery breadth

Solve in prompts plus orchestration plus evals.

### Claim support validation

Solve with a conservative validator after synthesis.

### Source-pill attribution

Solve at the tool boundary.

That last point matters because the repo already has `_tool_src_<uuid>` plumbing in:

- `apify_tools.py`
- `tripadvisor_tools.py`
- `worker_main.py`

There is already an active lower-change path for adding Google Maps / Places provider pills directly from tool output. That is cleaner and lower risk than piggybacking Places attribution on a verifier agent.

## Recommended rollout

### Phase 1. Tighten prompts and orchestration, do not add a new agent yet

Update `market_landscape.md` and relevant orchestrator briefing rules so that recent-opening/closure queries must:

- plan 3 evidence lanes before first search
- spend the first pass on different lanes, not just different phrasings
- detect domain monoculture after 4 fetched URLs
- spend the next query on an uncovered lane if top-domain share is too high
- explicitly label each closure/opening as `confirmed`, `probable`, `rumor`, or `moved`

This is a prompt-only change, but it is concrete enough to test.

### Phase 2. Add a conservative claim-support validator

Do this after synthesis, but do not let it rewrite freely.

Safer behavior:

- mark unsupported claims
- mark claims supported by only one weak lane
- mark claims contradicted by tool state
- either drop unsupported spans or regenerate only those spans from an evidence manifest

Riskier behavior:

- letting a second model rewrite the whole report from scratch

I would start with "flag and delete or downgrade," not "flag and rewrite."

### Phase 3. Add source-diversity and support evals

The eval harness is a good idea, but broaden the metrics beyond domain count.

Track:

- top-domain share
- unique domains
- lane coverage
- percent of claims with at least one explicit supporting source
- unsupported-claim rate after validation
- fetch failure rate by domain
- fetch truncation rate by domain
- provider coverage in final `sources[]`

This turns monoculture from a vibe into a regression metric.

### Phase 4. Add thin adapters only where telemetry justifies them

Do not build a country-by-country scraper directory first.

But also do not assume generic fetch is enough forever.

If telemetry shows repeated failures on a small number of high-value domains, add thin adapters only for those domains. In this product, likely candidates are exactly the domains where restaurant-market signal is valuable and generic article extraction is weak:

- delivery platforms
- booking/listing platforms
- structured social/listing pages

That is still a bounded surface.

## Specific recommendations I would make to this document

### Keep

- the diagnosis that source monoculture is the real issue
- the citation/claim verification idea
- the eval harness idea
- the rejection of a giant hardcoded scraper matrix as a first move

### Change

- replace the "no explicit diversity audit" claim with "existing diversity prompts are too weak and unmeasured"
- replace the Places "60 results" claim with the current API facts
- downgrade the "earliest review" claim from signal to heuristic
- soften the anti-prior stance from "don't provide source lists" to "use soft priors, not hard ceilings"
- split source planning responsibility between specialist defaults and orchestrator query-specific requirements

### Add

- evidence lanes for opening/closure research
- typed confidence labels for findings
- telemetry for fetch failures and truncation
- a small soft-prior registry by country/market, with exemplar domains only

## Suggested revised thesis

If I rewrote the proposal's core thesis, I would make it:

> The current issue is not lack of web reach but lack of explicit coverage control. The fix is not a giant new tool matrix; it is a combination of evidence-lane planning, conservative claim validation, and measurable source-diversity telemetry. Domain defaults should live in specialist instructions, while query-specific coverage constraints should be added by the orchestrator. Use soft source priors where they improve recall, and build domain adapters only when telemetry shows generic fetch is failing on high-value targets.

## Sources used for this review

External:

- Anthropic, "How we built our multi-agent research system"  
  https://www.anthropic.com/engineering/multi-agent-research-system
- Google Maps Platform, Places API (New) `places.searchNearby` reference  
  https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places/searchNearby
- Google Maps Platform, Places API REST `Place` resource (`businessStatus`, `movedPlace`, reviews behavior)  
  https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places
- Google Maps Platform, Place IDs overview / obsolete IDs  
  https://developers.google.com/maps/documentation/places/web-service/place-id
- OpenAI platform docs, deep research guide  
  https://platform.openai.com/docs/guides/deep-research
- Wang and Zhao, "Metacognitive Prompting Improves Understanding in Large Language Models"  
  https://aclanthology.org/2024.naacl-long.106.pdf
- Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet"  
  https://arxiv.org/abs/2310.01798
- Wu et al., "Large Language Models Can Self-Correct with Key Condition Verification"  
  https://aclanthology.org/2024.emnlp-main.714/
- DRACO: A Cross-Domain Benchmark for Deep Research Accuracy, Completeness, and Objectivity  
  https://arxiv.org/abs/2602.11685

Local repo files reviewed:

- `docs/research-depth-proposal.md`
- `agent/superextra_agent/instructions/market_landscape.md`
- `agent/superextra_agent/instructions/specialist_base.md`
- `agent/superextra_agent/instructions/research_orchestrator.md`
- `agent/superextra_agent/instructions/gap_researcher.md`
- `agent/superextra_agent/places_tools.py`
- `agent/superextra_agent/web_tools.py`
- `agent/superextra_agent/apify_tools.py`
- `agent/superextra_agent/tripadvisor_tools.py`
- `agent/worker_main.py`
- `docs/source-pills-per-provider-plan-2026-04-23.md`
