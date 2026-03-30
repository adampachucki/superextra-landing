# Superextra Agent — Plan

_March 2026_

## What We're Building

An AI agent that answers restaurant market questions by researching the web in real time. An operator asks "What cuisines are growing in Mokotów?" or "How does my pricing compare to nearby competitors?" — the agent researches and returns a sourced answer.

## Constraints

- **Gemini models only** on Google Vertex AI (€120K credits, 12 months)
- No scraper data connected initially — web research only
- Must be lean to start, flexible to expand

## Architecture

### Phase 1 — Agent Builder

- Gemini 2.5 Pro as the model
- Google Search grounding for live web research
- Agent instructions define scope: restaurant market intelligence, European markets
- No custom data stores yet — pure research agent
- Test in Agent Builder playground
- Integrate into the /agent page on the SvelteKit site

### Phase 2 — Add Data

- Connect scraper data via BigQuery data stores + Vertex AI Search
- Agent grounds answers in proprietary restaurant database
- Cloud Function tools for structured queries (competitor lookup, area stats)

### Phase 3 — ADK + Multi-Agent

- Migrate to ADK for multi-agent orchestration
- Parallel agents: researcher (gathers data), analyst (synthesizes), reporter (formats with charts)
- Connect restaurant's own data for benchmarking
- Report generation with graphs and charts

## Division of Work

**Claude does:** agent instructions, tool specs, Cloud Functions, BigQuery schemas, SvelteKit chat UI, API integration, debugging

**Adam does:** create agent in Console, connect data stores, test in playground, give feedback on agent quality

## Decisions

- ~~OpenClaw~~ — personal assistant platform, not a product agent framework
- ~~Claude on Vertex~~ — credits limited to Google models
- ~~Raw SDK~~ — too code-heavy right now
- **Agent Builder** for Phase 1 (learn concepts, fast to prototype)
- **ADK** for Phase 3 (multi-agent, full code control)
- **Vertex AI Search** as data grounding layer when scraper data comes in

## Product Context

- Superextra: AI-native market intelligence for restaurants
- Four layers: data sources → platform → AI agents → human experts
- Scope covers 7 intelligence layers (market, menu/pricing, revenue, marketing, guest, location, operations)
- Existing scraper provides structured data per restaurant (Google Maps, OSM, TripAdvisor, Instagram, websites) — available for Phase 2
- SvelteKit landing site on Firebase Hosting, /agent page already exists
