# Cross-Session Competitive Memory

Status: exploration / not started

## The Idea

Every query enriches a shared knowledge base. Instead of researching from scratch each time, the agent remembers what it already knows about a restaurant and its market, and only researches what's new.

Without memory, every query about Wen Cheng costs the same: 4-5 specialists, 30+ Google searches, 2.5 minutes, same findings as last time. With memory, the agent does differential research — only the delta since the last analysis.

## No User Accounts (Current State)

Users are identified by IP address — volatile and meaningless for memory scoping. The valuable memory isn't "what this user asked" but "what we know about this restaurant and market." This is entity-scoped intelligence, not user-scoped.

## ADK Memory Primitives

### MemoryService (document-based, semantic search)

- Scoped to `app_name` + `user_id` — no cross-user search, no third dimension
- `VertexAiMemoryBankService` for production (semantic similarity, LLM consolidation)
- `InMemoryMemoryService` for dev (keyword matching, no persistence)
- Agent reads via `LoadMemoryTool` (on-demand) or `PreloadMemoryTool` (auto-injected every turn)
- Agent writes via `context.add_memory()` — not automatic, must be explicitly triggered
- Data model: `MemoryEntry` with Content + custom_metadata + author + timestamp

### Session State (key-value, exact lookup)

- `app:key` — shared across ALL users and sessions
- `user:key` — per-user across sessions (useless without accounts)
- `temp:key` — single invocation only
- No prefix — session-scoped, dies when session ends

### The Gap

Neither system natively supports entity-scoped memory (e.g., "everything we know about Wen Cheng, accessible by anyone"). Workarounds:

- MemoryService: use `user_id="place:{placeId}"` — makes the restaurant the "user"
- Session state: use `app:entity:{placeId}:key` — structured facts shared across all users
- Custom tool wrapping Firestore/RAG — most flexible, most work

## Proposed Architecture: Three Layers

### Layer 1: Entity memory via `app:` state (Phase 1 — simplest)

After each research session, the synthesizer writes structured facts:

```
app:entity:{placeId}:competitors → ["Kongfu Chili", "LIU Nudelhaus", ...]
app:entity:{placeId}:last_researched → "2026-04-01"
app:entity:{placeId}:key_findings → "Queue fatigue is primary liability..."
app:entity:{placeId}:price_range → "16.50-18.50 EUR"
```

Context enricher reads these before dispatching. If `last_researched` is recent, the planner focuses on changes instead of full research. Pure key-value, no new infrastructure, works today with ADK 1.28.

### Layer 2: Market intelligence via MemoryService (Phase 2)

Add `VertexAiMemoryBankService` with market-scoped user IDs (e.g., `market:berlin:noodles`). After each session, save full specialist outputs as memories. Before research, `PreloadMemory` injects relevant past findings. Semantic search means a query about "Berlin noodle pricing" finds relevant memories from previous queries about specific restaurants in that market.

### Layer 3: User memory (Phase 3 — when accounts ship)

Personal preferences, conversation continuity, "remind me to check on this next month." Entity and market layers stay shared; user layer is personal.

## Differential Research Flow

1. Context enricher fetches Places data AND loads entity memory from `app:` state
2. Research planner sees: "We already know the competitive set, pricing, and core sentiment themes as of 2 weeks ago"
3. Planner dispatches fewer specialists with targeted briefs: "Check for new reviews since March 15" instead of "analyze all review sentiment"
4. Synthesizer produces a delta report: "Since the last analysis, Mr. Noodle Chen expanded to a second location and Wen Cheng's Google rating dropped from 4.3 to 4.1"
5. Synthesizer writes updated facts back to `app:` state

## The Moat

Every query any user makes enriches the knowledge base for the entire market. A new user asking about Berlin noodles on day one gets the accumulated intelligence of hundreds of previous queries. The more Superextra is used, the richer and faster it gets. No competitor starting from scratch on every request can match that depth.

## Open Questions

- How to handle stale entity data? TTL on `app:` state keys, or let the planner decide based on `last_researched` date?
- How to derive market scope from a restaurant query? Context enricher needs to identify the market (cuisine + geography) to scope MemoryService lookups.
- Should specialist outputs be stored verbatim or summarized before saving to memory? Verbatim is richer but noisier for semantic search.
- How to prevent memory pollution from low-quality or erroneous research? Confidence scoring on findings before persisting?
- When accounts arrive, how to migrate entity memory to coexist with user memory? MemoryService only has two dimensions (app + user).
