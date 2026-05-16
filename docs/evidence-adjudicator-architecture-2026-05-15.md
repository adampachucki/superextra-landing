# Evidence Adjudicator Architecture

**Date:** 2026-05-15  
**Status:** target architecture after SerpAPI + Jina pilot

This document supersedes `docs/search-fetch-redesign-handoff-2026-05-15.md` as
the target architecture. That earlier handoff is useful historical context for
the SerpAPI/Jina pilot, but its recommendation to replace native
`google_search`/`url_context` in specialists is no longer the chosen direction.

## Problem

The SerpAPI + Jina pilot proved that explicit search/read tools can fetch real
page text and avoid snippet-only grounding, but it also showed that adding a
parallel custom search/read surface creates too much tool surface area. Broad
rollout to every specialist makes each specialist independently search and read
many pages, which duplicates work, increases latency, and makes final source
provenance noisy.

The simpler target is to use the native ADK web tools directly in specialists:
`google_search` for discovery and `url_context` for reading concrete pages.
SerpAPI should not remain in the target architecture. Jina remains useful, but
only as the bounded independent reader for final evidence adjudication.

The opposite extreme, one central search pass, is also wrong. Specialists need
freedom to refine searches from their domain angle. A market specialist, guest
specialist, menu specialist, and dynamic researcher will naturally look for
different evidence.

The target architecture should preserve specialist refinement while centralizing
dedupe, conflict handling, and final source authority.

The core split:

- Specialists discover and reason with native Google tools.
- The adjudicator independently verifies selected URLs with Jina Reader.
- The writer writes without tools.

## Proposed Pipeline

```text
Router
  -> Context Enricher
  -> Research Lead
       -> Specialists use native Google Search + URL Context
       -> Specialists produce claim/source packets
  -> Evidence Adjudicator
       -> re-reads selected URLs with Jina Reader
       -> validates claims, resolves conflicts, emits evidence memo
  -> Report Writer
       -> writes final answer from specialist packets + evidence memo
```

## Agent Responsibilities

### Specialists

Default specialists should have the native ADK web tools:

- `google_search`
- `url_context`
- domain-specific tools such as Google Places, TripAdvisor, Google reviews

They should not get SerpAPI, Jina, custom fetch wrappers, or reader sub-agents
in the target default path. This keeps the specialist implementation close to
the documented ADK/Gemini tool model and removes duplicate read mechanisms.

Each specialist outputs structured material:

- important claims
- source URLs used or requested
- search queries that found those URLs
- confidence / caveats
- source type hints when known, for example official page, local press, review
  page, delivery page, aggregator

Specialists may still refine searches freely. Their job is to find the right
candidate evidence, read the pages that materially affect their report, and
surface the source URLs and claims that need final validation. They should not
try to exhaustively read every result.

### Specialist Packet Contract

The adjudicator gets its normal read queue from specialist outputs. It should
not rediscover sources in the default path.

Every specialist report must include a predictable validation packet with:

- `claims_for_validation`: concrete factual claims that matter to the final
  answer
- `candidate_sources`: concrete URLs the specialist found, read, cited, or wants
  validated
- source priority: `high`, `medium`, or `low`
- source type hint, for example official page, Google Places, local press, menu,
  delivery platform, review page, forum thread, aggregator, registry, PDF
- source-to-claim links so the adjudicator knows which URLs are supposed to
  support which claims
- source limits, for example snippet-only, unreadable, old, duplicate,
  aggregator, conflicting, or indirectly relevant

Example packet shape:

```json
{
	"claims_for_validation": [
		{
			"id": "market-1",
			"claim": "Monsun is listed as a Chinese restaurant at Świętojańska 69b.",
			"claim_type": "venue_fact",
			"confidence": "high",
			"source_urls": ["https://www.trojmiasto.pl/Monsun-o96445.html"],
			"source_notes": "Local listing found during restaurant-specific search."
		}
	],
	"candidate_sources": [
		{
			"url": "https://www.trojmiasto.pl/Monsun-o96445.html",
			"title": "Monsun",
			"domain": "trojmiasto.pl",
			"source_type": "local_listing",
			"priority": "high",
			"supports_claim_ids": ["market-1"],
			"limits": ""
		}
	]
}
```

### Evidence Adjudicator

The adjudicator has no search tool in the default path. It receives URLs and
claims from all specialists, then:

- dedupes and canonicalizes URLs
- filters bad candidates such as social pages, domain roots, tracking variants,
  obvious junk, and unsupported file types
- re-reads all eligible provided URLs with Jina Reader, appending any packet URLs the model omitted from the tool call
- extracts verified facts from page text
- maps facts back to specialist claims
- marks claims as confirmed, contradicted, unsupported, or unresolved
- records unreadable pages with failure reasons
- emits final source metadata for the UI

The adjudicator builds its read queue by ranking specialist-provided URLs:

1. URLs tied to important claims in `claims_for_validation`.
2. URLs cited by more than one specialist.
3. Direct operator pages, Google Places/provider data, current local press, menu
   pages, and concrete venue/detail pages.
4. Specific pages over search pages, category pages, domain roots, and social
   app pages.
5. Recent sources for time-sensitive claims.
6. Readable-looking pages over paywalled, login-only, app-only, or blocked
   pages.

This should use Jina Reader only. Do not use Jina Search, Jina DeepSearch, or
SerpAPI in the default adjudication path. The adjudicator is a verifier, not a
second research agent.

Jina is preferred here because it gives the validation layer an independent
fetch/extraction path from the specialists' native Gemini URL Context reads. If
specialists and the adjudicator both use the same URL Context path, the
adjudicator is more likely to repeat the same retrieval blind spots.

The adjudicator may get a very small bounded follow-up mechanism only when a
material conflict cannot be resolved from existing evidence. That follow-up
should be explicitly gap-driven, for example: one native `google_search` query
and up to three Jina Reader reads. This should be an exception, not normal
operation.

### Report Writer

The writer has no search or fetch tools.

It receives:

- specialist reports / claim packets
- adjudicator evidence memo
- verified source list
- unresolved source limits

Writer rules:

- Prefer adjudicator-verified evidence over specialist narrative.
- Do not state unsupported specialist claims as facts.
- If verified sources conflict and the adjudicator cannot resolve it, state the
  conflict plainly.
- Do not invent a tie-break.
- Do not cite unread pages as evidence.

## Evidence Memo Shape

The adjudicator output should be structured, not a narrative report.

```json
{
	"confirmed_claims": [
		{
			"claim": "Monsun is located at Świętojańska 69b, Gdynia.",
			"specialists": ["market_landscape", "dynamic_researcher_1"],
			"evidence": [
				{
					"url": "https://www.trojmiasto.pl/Monsun-o96445.html",
					"title": "Monsun",
					"domain": "trojmiasto.pl"
				}
			],
			"confidence": "high"
		}
	],
	"contradicted_claims": [
		{
			"claim": "Monsun offers delivery.",
			"specialists": ["guest_intelligence"],
			"specialist_basis": "delivery-platform listing",
			"contradicting_evidence": "Google Places service options say dine-in only.",
			"resolution": "treat delivery availability as uncertain; mention only as a platform signal"
		}
	],
	"unsupported_claims": [
		{
			"claim": "Monsun is the highest-rated Chinese restaurant in Gdynia.",
			"reason": "no read source contained a ranking comparison"
		}
	],
	"unresolved_conflicts": [
		{
			"topic": "current opening hours",
			"sources": ["Google Places", "aggregator page"],
			"reason": "sources disagree and no official operator page was readable"
		}
	],
	"unreadable_sources": [
		{
			"url": "https://example.com/page",
			"reason": "captcha"
		}
	],
	"sources": []
}
```

## Conflict Policy

The adjudicator owns conflict handling so the final writer is not asked to
choose between competing narratives.

Recommended precedence:

1. Direct operator source or Google Places details for stable venue facts.
2. Current dated local press or article pages for press and trend claims.
3. Specific venue page over category/list/search pages.
4. Read page text over search snippets.
5. Recent source over stale source when the claim is time-sensitive.
6. Aggregators and delivery platforms are signals, not definitive authority,
   unless the claim is specifically about that platform.
7. Unreadable pages do not support claims.

When precedence does not resolve a conflict, mark it unresolved and have the
writer state the limit.

## Why This Beats The Alternatives

### Compared With SerpAPI/Jina Specialist Reading

The SerpAPI/Jina pilot proved the value of explicit page reading, but making it
the specialist default creates another search stack beside ADK's native tools.
It also encourages broad batch reads from each specialist, which produced too
much fanout in production.

This architecture keeps specialist search refinement but uses native
`google_search` and `url_context` as the normal specialist implementation. The
separate Jina Reader adjudication stage bounds final verification instead of
letting every specialist exhaustively read every candidate.

### Compared With Native URL Context For The Adjudicator

Native URL Context is right for specialists because it sits inside their
Gemini/ADK reasoning loop. It lets them move from discovery to concrete URL
reading while preserving their domain-specific iteration.

For the adjudicator, using native URL Context again is weaker. The adjudicator's
job is not more Gemini-native reasoning; it is independent verification. Jina
Reader gives that stage a separate fetch/extraction path and returns page text
that can be checked against specialist claims.

Use native URL Context for adjudication only if Jina is materially worse in
production on the source classes that matter, such as local press, restaurant
listings, PDFs, menus, and forums.

### Compared With Jina DeepSearch

Jina DeepSearch is the wrong default for adjudication because it performs its own
search/read/reason loop. That duplicates the specialists' work and can turn the
validator into another open-ended researcher.

The adjudicator should receive a URL set and claim set, read a capped subset,
and return a structured evidence memo. It should not independently pursue broad
research.

### Compared With Agent-Tool Search/Reader Wrappers

Wrapping `google_search` and `url_context` in separate sub-agents can enforce a
search-then-read protocol on models that cannot combine the built-in tools
directly. It is not the first target for this codebase because the current
specialist model/tool stack can expose the native tools directly.

Use agent-tool wrappers only if native `google_search + url_context` proves
unreliable in the deployed model/runtime, for example if specialists skip page
reads, tool metadata is unavailable, or Vertex rejects the combined tool setup.

### Compared With One Central Search Pass

One central search pass is cheaper but loses specialist curiosity. It risks
missing domain-specific evidence that only appears after a specialist reframes
the query.

This architecture lets specialists refine searches, then centralizes reading and
verification.

### Compared With Making The Writer Read Pages

If the final writer also reads pages, the slowest and least predictable work
happens at the terminal stage. Failures become harder to diagnose: a bad final
answer could come from poor extraction, poor evidence ranking, unresolved
contradictions, or writing quality.

Separating adjudication from writing creates a clear contract and makes both
stages easier to test.

## Implementation Notes

Near-term implementation can be incremental:

1. Simplify default specialist web tools to native `google_search` and
   `url_context`, plus any domain-specific provider tools.
2. Remove the active SerpAPI/Jina pilot override from specialist configuration.
3. Stop exposing `search_and_read_public_pages`, `search_web`,
   `read_public_page`, `read_public_pages`, `fetch_web_content`, and
   `fetch_web_content_batch` to specialists.
4. Keep the Jina Reader implementation available internally for the adjudicator
   trial.
5. Require specialists to emit source URLs and claims in a predictable section.
6. Add an `evidence_adjudicator` agent after `research_lead` and before
   `report_writer`.
7. Give the adjudicator Jina Reader tools that read all eligible provided URLs, with bounded concurrency. The tool treats model-supplied URLs as ordering hints and appends omitted same-run packet/grounding URLs before reading.
8. Store adjudicator output in session state, for example `evidence_memo`.
9. Update `report_writer.md` to treat `evidence_memo` as authoritative over
   unsupported specialist prose.
10. Keep final writer tool-less.
11. Remove direct source persistence from raw search snippets and native
    grounding redirects; persist only fetched/verified/provider sources.

## Cleanup Plan

Do not keep the pilot tools active while testing adjudication. The trial should
exercise the target architecture, not a mixed system where old specialist tools
can still influence behavior.

Before the adjudicator trial:

1. Specialists use native `google_search + url_context`, plus domain-specific
   provider tools.
2. `dynamic_researcher_1` no longer receives the SerpAPI/Jina pilot tool
   override.
3. SerpAPI search and Jina read tools are not exposed as specialist tools.
4. Jina Reader remains available only behind the adjudicator boundary.

After the adjudicator trial proves the boundary:

1. Delete SerpAPI search tools if no other runtime path uses them.
2. Delete custom fetch wrappers not used by the adjudicator.
3. Keep one clean Jina Reader integration owned by adjudication.
4. Remove stale tests, event labels, docs, and source-persistence handling tied
   only to the pilot.
5. Do not expose Jina Search or Jina DeepSearch as default agent tools.

## Handoff Notes

This section is for a team implementing the architecture without prior context.
It includes only details that affect implementation decisions.

### Current Repo State

Current runtime dependencies:

- `agent/requirements.txt` pins `google-adk==1.28.0`.
- The local venv currently has `google-genai==1.72.0`.

Current tool wiring:

- `agent/superextra_agent/specialists.py` defines `_WEB_RESEARCH_TOOLS` as
  native `google_search` plus `url_context`.
- Dynamic researchers use the same native Google tool surface as other web
  research specialists.
- `review_analyst` is intentionally provider-only: TripAdvisor and Google
  reviews.
- The SerpAPI/Jina pilot search module was removed from the production code.
- `agent/superextra_agent/web_tools.py` keeps the Vertex URL Context wrapper,
  Jina Reader wrappers, and the bounded adjudicator reader.
- `agent/superextra_agent/instructions/specialist_base.md` now describes native
  search/URL Context for specialists and the validation-packet contract.

Relevant commits:

- `4ccc087` added native URL Context to research agents.
- `1414f33`, `6e9d911`, and `1f962e8` tightened URL Context / Jina reads and
  diagnostics.
- `c118498` added the SerpAPI/Jina pilot.
- `eb19f24` narrowed the pilot to `dynamic_researcher_1`.

### Pilot Results

The important trial results:

- The all-specialist SerpAPI/Jina pilot was too slow. Production probe
  `probe-search-read-expanded-20260515-182007` / run
  `b7a7904fa887450981055517d26d36ec` still had the Firestore turn `running`
  when the stream ended after 601s. Logs showed many
  `search_and_read_public_pages` calls across multiple specialists. The failure
  mode was fanout, not a single broken page read.
- The narrowed pilot completed. Production probe
  `probe-search-read-narrow-20260515-183719` / run
  `812e4b46a5ef4f7396d66f544459ab31` completed in 330s with 9 UI sources and
  zero persisted Vertex grounding redirect sources.
- In that narrowed probe, the combined search/read call discovered 32 candidate
  results, attempted 10 reads, read 4 successfully, failed 6, and took about
  25.3s for the combined tool call.
- Earlier URL Context wrapper probing showed timeout risk in Agent Engine:
  `probe-fetch-20260515-131515` had 4 `read_web_pages` calls, 1 success, and 3
  Vertex `504 DEADLINE_EXCEEDED` failures after roughly 21-23s. Do not
  reintroduce `read_web_pages` as a peer specialist reader beside native
  `url_context`.
- Local standalone Jina behavior can look better than Agent Engine behavior.
  Do not treat local read success rates as proof that multi-specialist
  production fanout is acceptable.

Verification already run after the narrowed pilot:

- Agent tests: `294 passed, 18 skipped`.
- Frontend Vitest: `73 passed`.
- Functions tests: passed.
- Firestore rules tests: `22 passing`.
- `npm run check`: passed with existing warnings.
- `npx eslint .`: passed with existing warnings.

### First Implementation Slice

Do this before building the full adjudicator:

1. Simplify specialist tool lists so active specialists no longer see
   SerpAPI/Jina pilot tools or old custom fetch wrappers.
2. Update `specialist_base.md` to require the validation packet and remove
   pilot-tool-specific instructions.
3. Preserve one internal Jina Reader batch function for the future adjudicator.
4. Add tests that assert the specialist tool surface is native
   `google_search + url_context` plus domain provider tools.
5. Run one production prompt, not evals, and inspect whether specialists emit
   usable `claims_for_validation` and `candidate_sources`.

Then build the adjudicator:

1. Add `evidence_adjudicator` after `research_lead`.
2. Feed it specialist reports / packets from state.
3. Give it only bounded Jina Reader access in the default path.
4. Store its structured result as `evidence_memo`.
5. Update `report_writer.md` to treat `evidence_memo` as source-of-truth for
   confirmed, contradicted, unsupported, and unresolved claims.

### Acceptance Criteria

The adjudicator trial succeeds only if:

- Specialists still refine searches from their own evidence surfaces.
- Every specialist report includes parseable claim/source packets.
- The adjudicator reads eligible URLs from specialist packets, not a broad
  self-discovered web set.
- The adjudicator marks claims as confirmed, contradicted, unsupported, or
  unresolved.
- The writer does not use unsupported specialist claims as facts.
- UI sources are fetched/provider/verified sources, not raw snippets or
  `vertexaisearch.cloud.google.com/grounding-api-redirect` URLs.
- A normal production prompt completes within the practical stream window.
- Logs show bounded Jina reads rather than per-specialist batch read fanout.

### Things To Avoid

- Do not leave the `dynamic_researcher_1` pilot override active while testing
  adjudication.
- Do not expose SerpAPI search to specialists in the target architecture.
- Do not expose Jina Search or Jina DeepSearch. DeepSearch duplicates the
  research loop and can turn validation into another open-ended researcher.
- Do not keep native URL Context, Jina Reader, and custom fetch wrappers as peer
  specialist tools. That recreates the tool ambiguity and latency waste from
  the pilot.
- Do not make the adjudicator a second full researcher by default. Its normal
  inputs are specialist URLs and claims.
- Do not give the report writer tools.
- Do not persist raw search snippets or Vertex redirect URLs as final sources.
- Do not add retries, broad fallbacks, or compatibility shims unless tied to an
  observed failure or external API contract.

### References To Read Before Coding

Official / primary:

- [ADK Google Search Grounding](https://adk.dev/grounding/google_search_grounding/)
  - search grounding injects web pages/snippets; this is discovery context, not
    a substitute for final page validation.
- [Gemini API URL Context](https://ai.google.dev/gemini-api/docs/url-context)
  - URL Context can read provided URLs, exposes retrieval metadata, and can
    combine with Google Search on supported model/API combinations.
- [Vertex AI URL Context](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/url-context)
  - verify current Vertex behavior before changing deployed model/tool setup.
- [Google Developers Blog: URL Context GA](https://developers.googleblog.com/en/url-context-tool-for-gemini-api-now-generally-available/)
  - production-readiness, pricing, PDFs/images/web/data-file support.
- [Jina Reader](https://jina.ai/reader/)
  - use `r.jina.ai` Reader only for adjudicator reading; relevant controls
    include timeout, token budget, browser engine, CSS extract/wait/exclude, and
    ReaderLM-v2.
- [Google Cloud Blog: Jina Reader architecture](https://cloud.google.com/blog/products/application-development/how-jina-ai-built-its-100-billion-token-web-grounding-system-with-cloud-run-gpus)
  - useful background for why Jina is appropriate as a dedicated page-text
    extraction layer.
- [ADK Multi-Agent Systems](https://adk.dev/agents/multi-agents/)
  - reference for adding a sequential adjudicator stage.

Community / issue context:

- [python-genai issue #941](https://github.com/googleapis/python-genai/issues/941)
  - historical context for Vertex/tool-combination failures.
- [ADK issue #3857](https://github.com/google/adk-python/issues/3857)
  - similar multiple-tool error context; reinforces verifying the pinned SDK and
    deployed model before assuming tool combinations work.
- [Google AI Developers Forum: URL Context reliability reports](https://discuss.ai.google.dev/t/does-url-context-even-work-can-you-fix-it/91770)
  - not authoritative, but useful reminder to inspect retrieval metadata and
    logs instead of assuming a URL was actually read.

Local:

- `agent/superextra_agent/instructions/AUTHORING.md`
- `docs/deployment-gotchas.md`
- `docs/search-fetch-redesign-handoff-2026-05-15.md` for historical pilot
  context only; do not implement its full replacement direction.
- Root `AGENTS.md`

Open design choices:

- Exact claim packet schema.
- Per-turn read concurrency.
- Whether the adjudicator may perform one bounded follow-up search.
- Source precedence by market and source class.
- UI display for contradicted or unreadable sources.
