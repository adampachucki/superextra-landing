# Specialist Source Reading Architecture

**Date:** 2026-05-17

## Current Shape

The research pipeline is:

```
Router
  -> Context Enricher
  -> Research Lead
       -> specialists through AgentTool
  -> Report Writer
```

There is no separate evidence adjudication stage.

Specialists own source reading for their evidence surface. The writer owns
final synthesis from specialist reports and must carry each specialist's
evidence limits into the user-facing answer.

## Source Flow

1. Specialists search with `search_public_web`, which returns exact public
   result URLs, marks them as `public_search` provenance, and records them per
   run and per specialist.
2. Search/source metadata is captured as source-drawer provenance.
3. `read_discovered_sources(urls)` reads exact concrete public URLs the
   specialist passes directly.
4. `read_discovered_sources([])` lets the same specialist read captured same-run
   search result URLs without copying or reconstructing URLs. Empty reads
   prioritize the latest search result batch, then older unread candidates.
5. Successful reads return page content and read metadata to the specialist.
6. The specialist report states what was read, what was only a search or
   grounding signal, what came from structured provider tools, and what remains
   weak or inaccessible.
7. Source pills remain discovery/provider display provenance: `public_search`
   result sources, native grounding sources when present, and structured
   provider sources. Read/fetched pages are measured in evals, not added as
   separate source pills.

## Why This Replaced Adjudication

The adjudicator added a late verifier that could not search broadly enough to
resolve many specialist claims. It also created extra prompt and runtime cost,
plus a second source representation that confused read observability.

Keeping reading inside specialists is simpler:

- the agent that discovers a source can read it while the research context is
  fresh;
- source failures are handled inside the evidence surface that needs them;
- the writer receives richer plain-language evidence notes instead of a second
  claim-status artifact;
- evals can measure the actual funnel from search/source discovery to
  specialist reads.

## Observability

`agent/evals/parse_events.py` reports the discovery-to-read funnel with
`specialist_read_*` metrics:

- search/captured source URL counts;
- read calls by specialist;
- requested, attempted, successful, failed, skipped, rejected, invalid, omitted,
  and auto-appended URLs;
- failed read reasons;
- search/captured URLs not attempted.

This replaces packet-to-adjudicator metrics. The source drawer remains a
separate discovery/provider provenance surface and should not be interpreted as
read coverage.
