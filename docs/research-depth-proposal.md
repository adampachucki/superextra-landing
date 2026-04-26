# Improving research depth in the Superextra agent pipeline

## The trigger

A recent session ran the query _"What has opened or closed in my area recently?"_ for a restaurant in Gdynia. The final report cited 10 sources: eight went to trojmiasto.pl (a Polish local news/forum portal), one to ubereats.com, one to orlygastronomii.pl (a restaurant trade site). Google Places data was used under the hood but didn't appear in the sources drawer at all. The report also name-checked Domiporta and Gratka (commercial real estate sites) as if they'd been fetched — neither was actually in the source list, meaning those references are either Gemini filling from memory or rephrased from the forum threads.

The complaint from the PM: this is monoculture research. The expectation for a restaurant-market question is cross-checking across delivery platforms, Google Maps, booking sites, industry press, and social — not leaning on one local portal. The question is _why_ the agents didn't broaden further, and _how_ to change that without over-specifying and anchoring them.

## What the pipeline looks like today

Router → Context Enricher → Research Orchestrator → 2–5 specialists (run in parallel via AgentTool) → Gap Researcher → Synthesizer.

Specialists are pre-specialized and persistent — each has its own handcrafted instruction file (`market_landscape.md`, `menu_pricing.md`, `guest_intelligence.md`, etc.). They share a common tool loadout: `google_search` (Gemini grounding) and `fetch_web_content` (Jina). A few specialized tools exist for reviews (TripAdvisor via SerpAPI, Google Reviews via Apify) and Places (native API). No dedicated tools for delivery platforms, booking sites, or social media.

In the session we audited, the orchestrator dispatched a single specialist — `market_landscape`. That specialist ran Gemini-grounded searches, which returned the 10 trojmiasto-dominated links. No explicit multi-source mandate, no diversity audit, no citation verification.

## Why the obvious fix doesn't work

First instinct was "expand the Places fetch to check `businessStatus` on all nearby venues — that'll give us closures directly." Research killed it. Places is bad at historical closures for three stacking reasons:

1. `CLOSED_PERMANENTLY` only appears during a transitional window. Once Google fully delists a venue its `place_id` returns `NOT_FOUND` and the place drops out of Nearby Search entirely.
2. Nearby Search ranks by prominence and caps at 60 results. Closed places rank lower and fall off.
3. `CLOSED_PERMANENTLY` is also returned for venues that _moved_, so it's ambiguous without checking `movedPlace`.

Third-party scrapers explicitly note Places "doesn't have a filter for closed businesses." So for "what closed in the last 12 months," Places can't be the ground truth — you genuinely do need sources with memory (forums, press, archives). trojmiasto.pl is _a valid source_; the problem is that it's the _only_ source when equivalents exist.

The one Places signal worth surfacing is review-freshness as an opening-date proxy: a venue whose earliest review is ~3 months old is almost certainly new. Openings are well served; closures are not.

## Why the other obvious fix also doesn't work

Second instinct was "build tools for the missing platforms — Pyszne, Wolt, Glovo, booking sites, social — and give the agents country-aware source lists." Pushed back on for two reasons:

1. **It doesn't scale.** Every category (delivery, booking, social, press, real estate) becomes a maintained tool, and coverage varies wildly by country. You end up with an unbounded maintenance surface.
2. **It narrows exploration.** Handing an agent a specific list anchors it to that list. Unguided, agents tend to explore more broadly; given a checklist, they treat the checklist as a ceiling.

The underlying capability already exists — `fetch_web_content` works on any URL. The gap isn't "can the agent reach Pyszne?" — it's "does the agent _think_ to reach Pyszne?"

## The pattern mismatch

A useful insight from reading Anthropic's writeup on their multi-agent Research system: they give specialists source guidance at delegation time, because their specialists are spawned generically per task and have no persistent role. Ours are different — our specialists are pre-specialized, with handcrafted domain instructions. Domain knowledge lives in those files. Which means the question "where does source-category planning belong?" has a different answer for us than for them.

For our system, the answer is: in the specialist instruction files. That's where every other piece of domain reasoning already lives.

## Proposed solution

Three moves, smallest to largest, in order:

**1. Source-category planning in specialist instructions.**
Each specialist instruction gets a meta-cognition scaffold customized to its domain. Structure:

- Before searching, list 3–5 source _categories_ relevant to this angle (not specific domains — categories).
- Run at least one query per category.
- After round one, audit results: if one domain dominates, intentionally broaden.

`market_landscape`'s categories would differ from `menu_pricing`'s. The orchestrator doesn't hand out categories — its job stays decomposition and brief-writing. Research backing: metacognitive prompting (ACL 2024) and meta-plan optimization frameworks show self-scaffolded category reasoning measurably improves output breadth. Known limitation: LLM self-monitoring is uneven, so this can't stand alone.

**2. Verification / citation pass after the synthesizer.**
Borrowed from Anthropic's `CitationAgent` pattern. After the final report is drafted, a lightweight agent re-reads it, checks every factual claim against the sources that were actually fetched, and flags claims without support. This would have caught the Domiporta/Gratka mentions in the Monsun session. It also gives us a clean place to inject synthetic citations for Places-derived claims — pointing at `googleMapsUri` — so the sources drawer reflects what was actually used, instead of only what came through Gemini grounding.

**3. Source-diversity eval, ~10 canned queries.**
Not a deploy gate — too noisy. A weather station: run it when iterating on prompt changes, track unique domains, top-domain share, category coverage. Adapted from Anthropic's evaluation rubric (factual accuracy, citation accuracy, source quality, completeness, tool efficiency). Its job is to tell us whether move (1) actually worked, because metacognitive prompts can feel right while producing the same monoculture.

## What we're explicitly not doing, and why

- **Not hardcoding delivery/booking/social platform lists.** Anchoring hazard; maintenance unbounded.
- **Not building country-aware source directories.** Same reason.
- **Not mandating N sources per claim.** Rigid, brittle, over-rewards redundant citations.
- **Not adding new scraping tools on day one.** The generic fetch works for most URLs; build specialized tools only when generic fetch demonstrably breaks on a specific target.
- **Not moving source planning into the orchestrator.** Its role stays decomposition + delegation; domain-specific source reasoning belongs with domain-specific specialists.

## Open questions worth outside feedback on

1. **Is the metacognitive-prompting approach enough on its own?** The cited research says it helps measurably but is uneven. Our bet is that (1) + (3) together — prompt + eval feedback loop — catches the unevenness. Is that optimistic?
2. **Should the verification agent actually rewrite unsupported claims, or just flag them?** Flagging is safer but noisier in the UI. Rewriting is cleaner but gives another model a chance to hallucinate.
3. **How should we handle legitimate single-source findings?** Some facts genuinely only exist in one place (a specific forum thread reporting a closure). Downgrading all single-source claims would wrongly penalize this. The verification pass needs to distinguish "unsupported" from "supported by only one place that actually covered it."
4. **Is anyone shipping a better pattern we're missing?** The Anthropic Research architecture is the clearest published reference. Deep Research clones (OpenAI, Perplexity, etc.) are worth surveying for citation-verification and diversity patterns we'd have missed.

## Sources

- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Metacognitive Prompting Improves Understanding in LLMs (ACL 2024)](https://aclanthology.org/2024.naacl-long.106.pdf)
- [Google Places API — businessStatus field](https://developers.google.com/maps/documentation/places/web-service/place-details)
- [Google Places Web Service FAQ — NOT_FOUND / obsolete place IDs](https://developers.google.com/maps/documentation/places/web-service/faq)
- [Scrap.io — "Places API doesn't have a filter for closed businesses"](https://scrap.io/how-to-scrape-closed-businesses)
- [LLM Agents — Prompt Engineering Guide (planning module)](https://www.promptingguide.ai/research/llm-agents)
