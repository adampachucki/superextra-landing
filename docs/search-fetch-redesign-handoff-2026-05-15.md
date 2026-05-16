# Search/Fetch Redesign Handoff

Date: 2026-05-15

> Superseded: use `docs/evidence-adjudicator-architecture-2026-05-15.md` for
> the current target architecture. This document is historical context for the
> SerpAPI/Jina pilot and should not be implemented as the active direction.

## Goal

Prepare a cleaner research stack that drops Gemini-native `google_search`, Google grounding, and `url_context` from the specialist research path. Replace them with explicit function tools:

- SerpAPI for source discovery/search results.
- Jina Reader for page reading.
- Existing Google Places tools stay. This is about web research, not venue identity/Places enrichment.

The aim is not to make the prompt louder. The aim is to make research deterministic enough that specialists can search, read pages, refine searches, and cite/use source content without opaque Gemini grounding behavior.

## Why This Is Needed

Recent work tried to nudge agents to fetch more after Google Search grounding. It produced mixed results:

- Prompt pressure made agents "dance": repeated searches, repeated fetch attempts, and visible wasted activity.
- Tight wording around "source cannot be displayed unless fetched" caused source pills to disappear or become underused. Product requirement is the opposite: source pills must continue to surface grounding/search-result sources, fetched-page sources, and provider sources.
- Gemini URL Context was added, but production probes showed it is slow and unreliable in Agent Engine. In `probe-fetch-20260515-131515`, specialists called `read_web_pages` 4 times; 1 succeeded and 3 failed with Vertex `504 DEADLINE_EXCEEDED` after roughly 21-23s. The final answer worked only because specialists fell back to Jina reads.
- `include_server_side_tool_invocations` looked like the native context-circulation switch, but the installed Vertex SDK rejects it before request dispatch: `ValueError: include_server_side_tool_invocations parameter is not supported in Vertex AI.`
- Parallel specialists still duplicate the same searches/reads. Prompt instructions cannot reliably coordinate shared in-flight fetch state across concurrent specialists.

## Relevant Commits

Recent chain to review before changing code:

- `30a134b` - Specialists must fetch sources, not rely on search snippets.
- `7ac2cb4` - Sharpen fetch-required rule in specialist prompts and tool docstrings.
- `6fea319` - Surface fetched URLs as source pills; soften fetch-required rule.
- `f1cbf7b` - Stop the fetch-tool dance: redirect unwrap, per-run cache, sharper guards.
- `78caec2` - Bind citations to fetch tool across prompt and docstring surfaces.
- `1b7ce52` - Add URL Context page reading workflow.
- `4ccc087` - Add native URL Context to research agents.
- `159e2b4` - Log server-side Gemini tool usage tokens.
- `5f68f7d` - Tighten page fetch timeouts and diagnostics.
- `1414f33` - Tune URL Context and Jina page reads.
- `6e9d911` - Log research tool context and tighten URL reads.
- `1f962e8` - Set practical URL Context timeout.

Treat much of this as cleanup debt if the redesign removes Google grounding and URL Context.

## Current Code Surfaces

Start here:

- `agent/superextra_agent/specialists.py`
  - imports `google_search`, `url_context`;
  - `_WEB_RESEARCH_TOOLS` combines Gemini built-ins with `read_web_pages`, `fetch_web_content`, and batch fetch;
  - `_inject_geo_bias` exists only to bias Gemini search retrieval.
- `agent/superextra_agent/agent.py`
  - `research_lead` uses `google_search`, `url_context`, and fetch/read tools;
  - `continue_research` still has `url_context`.
- `agent/superextra_agent/web_tools.py`
  - `read_web_pages` currently means Vertex Gemini URL Context;
  - `fetch_web_content[_batch]` means Jina raw Markdown fallback;
  - redirect unwrap exists only for Vertex grounding URLs.
- `agent/superextra_agent/firestore_events.py`, `firestore_progress.py`, `gear_run_state.py`
  - extract grounding sources/search queries and merge them into source pills/timeline.
- Tests that will need intentional rewrites:
  - `agent/tests/test_agent_config.py`
  - `agent/tests/test_specialist_callbacks.py`
  - `agent/tests/test_web_tools.py`
  - `agent/tests/test_firestore_events.py`
  - `agent/tests/test_firestore_progress_hooks.py`
  - `agent/tests/test_chat_logger.py`
  - instruction-provider tests for `specialist_base.md` and `continue_research.md`.

Existing SerpAPI pattern:

- `agent/superextra_agent/tripadvisor_tools.py`
  - uses `SERPAPI_API_KEY` through `secrets.get_secret`;
  - uses `httpx.AsyncClient`;
  - returns structured dicts with stable `status`;
  - writes provider source pills through `tool_context.state`.

Use that style for generic search tools.

## Proposed Direction

Add a new explicit search module, likely `agent/superextra_agent/search_tools.py`.

Suggested tools:

- `search_web(query, location=None, gl=None, hl=None, num_results=10, freshness=None)`
  - SerpAPI `engine=google`.
  - Return normalized `results`: title, url, domain, snippet, date/source when available, position, result type.
  - Keep raw SerpAPI payload out of the model response except for fields needed by specialists.
- `search_news(query, location=None, gl=None, hl=None, freshness=None, num_results=10)`
  - SerpAPI `engine=google_news`.
  - Use for openings, closures, local press, current events, policy/news signals.
- Optionally later: domain-specific SerpAPI tools, but avoid expanding the first patch into every possible engine.

Then make page reading Jina-first:

- Either rename `fetch_web_content[_batch]` to the primary reader, or replace `read_web_pages` so it no longer calls Vertex URL Context.
- Prefer one clear reader tool over three overlapping "read/fetch/url context" options.
- Keep a batch form for parallel page reads.
- Return `sources` for every successfully read URL so pills are generated without relying on grounding.
- Keep raw content bounded and predictable. The specialist needs enough page text to reason, but the tool should not dump unlimited pages.

Add run-level reuse:

- Keep the existing per-run cache idea, but make it work for the new architecture.
- Cache by normalized URL for reads and by normalized query/params for searches.
- Consider in-flight dedupe, not just completed-result cache. The production issue is parallel specialists starting the same read at the same time.
- Source registry should merge search-result sources, fetched-page sources, provider sources, and Places sources without depending on Gemini grounding metadata.

## Pilot Before Full Replacement

Before deleting Google grounding everywhere, run one isolated agent pilot.

Recommended pilot:

- Add `search_web` as a SerpAPI function tool.
- Expose it only to one pilot specialist, probably one dynamic researcher.
- Give that pilot specialist `search_web`, Jina page reading, and batch Jina page reading.
- Do not give that pilot specialist `google_search`, `url_context`, or `read_web_pages` if `read_web_pages` still means Vertex URL Context.
- Leave the rest of the research architecture untouched for the pilot.

This tests the real behavior that matters: whether a specialist can search, pick URLs, read pages, refine, and write useful source-backed research without Gemini grounding. A standalone script can test provider latency, but it will not test model tool-use behavior inside the existing multi-agent pipeline.

Pilot success criteria:

- The pilot specialist calls SerpAPI for discovery.
- It reads 2-5 concrete URLs with Jina.
- Source pills appear from SerpAPI/Jina/provider sources, without grounding.
- No URL Context calls happen inside the pilot specialist.
- The specialist report contains page-derived facts, not just search snippets.
- The run has fewer repeated failed reads than recent URL Context sessions.
- Final answer quality is at least comparable to the Google-grounded path for the tested prompt.

If the pilot works, proceed with the full cleanup. If it fails, fix the SerpAPI/Jina tool contract before touching every specialist.

## Prompt/Workflow Shape

Rewrite source instructions once, mainly in `specialist_base.md`.

Desired workflow:

1. Search with SerpAPI when sources are not already known.
2. Pick the strongest concrete URLs from results.
3. Read those pages with Jina.
4. Refine search if the page content changes the hypothesis or exposes a better source.
5. Stop after a bounded number of weak/repeated searches and state the evidence gap.

Keep the Report Writer tool-free. It should synthesize specialist reports and Places context only.

Keep specialists able to iterate. Do not move research only to the writer or to a new global researcher. The point is for each specialist to search/read/refine inside its evidence surface.

## Cleanup Guidance

If this path is chosen, delete obsolete paths in the same change:

- Remove `google_search` and `url_context` imports/tools from `agent.py` and `specialists.py`.
- Remove URL Context client/model/timeouts from `web_tools.py`.
- Remove Vertex grounding redirect unwrap if no remaining path emits those URLs.
- Remove `_inject_geo_bias` if no Gemini retrieval tool remains.
- Remove grounding-specific source extraction/search-query timeline tests if no longer used.
- Remove chat logger fields/tests that only exist for native server-side Gemini tool invocations, unless they still serve another live path.
- Rewrite prompt text that says "Native URL Context", "grounding sources", or "source-pill display" in the old framing.

Do not keep compatibility shims for dead research paths unless an existing live session requires them. The repo guidance is explicit: replace architecture cleanly and delete obsolete docs/tests/comments in the same change.

## Things To Avoid

- Do not add another prompt nudge that still leaves Google grounding as the real source discovery system.
- Do not keep both URL Context and Jina as peer page readers. That created tool ambiguity and timeout waste.
- Do not make automatic "fetch everything from search" broad and hidden. If a convenience `search_and_read` tool is added, keep it bounded and transparent.
- Do not give Report Writer research tools.
- Do not break source pills. If grounding goes away, SerpAPI/Jina/provider tools must explicitly emit pill-ready source objects.
- Do not make duplicate searches the first target unless it falls out naturally from run-level cache/in-flight dedupe. The bigger root cause is the opaque native search/fetch split.

## Documentation Pointers

Official docs to read before coding:

- ADK Function Tools: https://adk.dev/tools-custom/function-tools/
- ADK source for function tool behavior: https://github.com/google/adk-python/blob/main/src/google/adk/tools/function_tool.py
- SerpAPI Google Organic Results: https://serpapi.com/organic-results
- SerpAPI Google News API: https://serpapi.com/google-news-api
- Jina Reader: https://jina.ai/reader/
- Jina Reader repo/docs: https://github.com/jina-ai/reader

Local docs to read:

- `agent/superextra_agent/instructions/AUTHORING.md`
- `docs/deployment-gotchas.md`
- `AGENTS.md` repo instructions in the workspace root.

## First Implementation Slice

A good first slice should be small but architectural:

1. Add `search_tools.py` with `search_web` and focused tests.
2. Replace specialist web tool set with `search_web` plus Jina page reading. No Gemini-native search or URL Context.
3. Update `specialist_base.md` to describe the new search/read workflow.
4. Update source-pill plumbing so SerpAPI/Jina sources appear without grounding.
5. Run agent tests: `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`.
6. Redeploy Agent Engine with `agent/scripts/redeploy_engine.py --yes`.
7. Run one production probe and inspect logs for: search calls, read calls, duplicate reads, source pills, final answer quality, elapsed time.
