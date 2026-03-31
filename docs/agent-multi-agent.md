# Multi-Agent Architecture

_March 2026_

## Goal

Replace the single generic research agent with 7 specialist agents (one per intelligence layer) that work in parallel, then a synthesizer combines their findings into one cohesive report. A single agent diving into multiple topics at once dilutes quality. Parallel specialists each go deep, then synthesis connects the dots.

## The 7 Layer Agents

Each agent covers one intelligence layer, has its own instructions, model, and tools.

| # | Agent | Covers | Example question it handles |
|---|-------|--------|-----------------------------|
| 1 | Market Landscape | Openings, closings, competitor activity, cuisine trends, saturation | What new restaurants opened nearby recently? |
| 2 | Menu & Pricing | Competitor menus, price positioning, delivery markups, promotions | How does our pricing compare to competitors within 1 km? |
| 3 | Revenue & Sales | Market-wide performance, seasonality, channel splits, benchmarks | Was last month slow for everyone or just us? |
| 4 | Guest Intelligence | Review sentiment, guest expectations, complaints/praise patterns | What are the recurring themes across competitor reviews? |
| 5 | Location & Traffic | Foot traffic, demographics, purchasing power, trade area analysis | What does the foot traffic and competition look like in Mokotów? |
| 6 | Operations | Labor availability, salary benchmarks, rent, supplier pricing | What are restaurants near us paying line cooks? |
| 7 | Marketing & Digital | Social media activity, ad platforms, delivery platform performance | How are competitors marketing on Instagram and delivery apps? |

## How It Works

```
User question
    ↓
Orchestrator (Gemini Pro)
  - Analyzes question
  - Identifies which 2-3 layers are needed
  - Optionally asks clarifying questions
    ↓
Parallel Research (activated layers only)
  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │ Market      │ │ Pricing     │ │ Operations  │
  │ Agent       │ │ Agent       │ │ Agent       │
  │ (Flash)     │ │ (Flash)     │ │ (Flash)     │
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         ↓              ↓              ↓
    market_data    pricing_data    ops_data
                   ↓
Synthesizer (Gemini Pro)
  - Reads all layer outputs
  - Connects findings across layers
  - Structures final report
  - Suggests follow-up questions
    ↓
Final answer to user
```

Model allocation: **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`) for all agents. Costs don't matter — best reasoning = best research quality. Fallback: `gemini-2.5-pro` (GA, stable until Jun 2026).

Not all 7 agents run every time. The orchestrator activates only the relevant 2-3 based on the question.

## Use Case → Layer Mapping

Most real questions span multiple layers. That's where the value is — combining different intelligence areas into one cohesive answer.

| Use case (from /agent page) | Layers activated |
|-----------------------------|-----------------|
| Down month — us or everyone? | Revenue & Sales + Market Landscape |
| Expansion gamble | Location & Traffic + Market Landscape + Operations |
| New concept, no proof | Market Landscape + Guest Intelligence |
| Staffing squeeze | Operations |
| Pricing in the dark | Menu & Pricing + Market Landscape |
| Review noise | Guest Intelligence |
| Competitor blind spot / Slow to react | Market Landscape + Menu & Pricing |
| Competitor marketing (new, not yet on page) | Marketing & Digital |

## Implementation Options

### Option A: Agent Designer (Console)

Use the visual Agent Designer in Vertex AI Studio — the tool we already use. Create 7 sub-agents in the console, each with own instructions + Google Search + MCP tools.

**What we know:**
- Each sub-agent gets its own name, description, instructions, model, tools
- Available tools: Google Search, URL context, Vertex AI Search data stores, MCP servers
- "Get code" exports ADK Python code for further development
- We already have the console set up with the existing agent

**Now known (from docs research):**
- Sub-agents execute **sequentially via LLM delegation** (coordinator pattern) — no parallel execution
- Parent agent delegates based on **LLM reasoning** about sub-agent descriptions — not explicit rules
- "Get code" exports **LlmAgent with sub_agents** (coordinator pattern), not ParallelAgent
- You cannot instruct the parent to consult multiple sub-agents simultaneously

**Verdict:** Agent Designer is ruled out for our parallel fan-out architecture. Useful only for single-agent prototyping.

### Option B: ADK Code (Python)

Write the agent system in Python using ADK. Full control over orchestration.

**What we know (verified from ADK docs):**
- `ParallelAgent` runs sub-agents concurrently — each writes to a separate `output_key` in shared `session.state`
- `SequentialAgent` chains steps — research phase then synthesis phase
- Fan-out/gather pattern is explicitly supported:
  ```python
  research = ParallelAgent(sub_agents=[agent1, agent2, agent3])
  pipeline = SequentialAgent(sub_agents=[research, synthesizer])
  ```
- Each agent can have different model, tools, instructions
- `AgentTool` wraps an agent as a callable tool (alternative to transfer)
- Deploys to Agent Engine, Cloud Run, or GKE
- 60+ pre-built tool integrations (BigQuery, Google Search, Google Maps MCP, etc.)

**Now known (from docs research):**
- Agent Engine **does support** ParallelAgent — no restrictions on workflow agent types in AdkApp
- **No TypeScript ADK** — ADK supports Python, Java, Go only. Code samples in all three.
- Latency still unknown — needs benchmarking

**Trade-off:** Introduces Python into a JS/TS stack. More powerful but more infrastructure.

### Option C: DIY in Cloud Function (Node.js)

Keep the existing Cloud Function. Use `Promise.all()` to run parallel Gemini calls via the Vertex AI SDK.

```js
const plan = await orchestrator.generateContent(...);  // decompose question
const results = await Promise.all(                      // parallel research
  plan.layers.map(layer => specialists[layer].generateContent(...))
);
const report = await synthesizer.generateContent(...);  // combine results
```

**What we know:**
- Already have the Vertex AI SDK set up in the Cloud Function
- `Promise.all` gives true parallel execution
- No new framework, language, or deployment target
- Each specialist is just a different system prompt + Google Search grounding

**What we don't know:**
- Whether this approach scales well beyond Google Search (when data stores come in Phase 2)
- How to handle streaming with this pattern (SSE from Cloud Function)

**Trade-off:** Simplest to build now. Less structured than ADK. Harder to extend with MCP tools, data stores, etc. in Phase 2.

## Alignment Needed on Frontend

The site has 6 different lists (pills, prompts, use cases, memo questions, layers, main-page use cases) that don't map consistently to the 7 layers. Before building the agents:

- **Marketing & Digital** has no use case on /agent page and no dedicated pill
- **Revenue & Sales** is underrepresented (only "down month")
- "Competitor blind spot" and "Slow to react" overlap — could merge into one
- Animated prompts in chat should mirror the 7 layers
- Topic pills should cover all 7 layers (currently 6 pills for 6 of 7 layers)

## Research Findings (March 2026)

Researched via Google Cloud documentation. Answers to the open questions:

### 1. Agent Designer does NOT support parallel sub-agent execution

Agent Designer uses the **coordinator pattern** — LLM-based sequential delegation. The docs describe multi-step agents as "complex tasks that can be broken down into a sequence of smaller steps." The parent agent uses the Gemini model to analyze which subagent to delegate to, one at a time.

The **parallel pattern** is a separate concept that explicitly requires ADK's `ParallelAgent` workflow agent, which "operates on predefined logic without consulting an AI model to orchestrate its subagents." This is code-only — not available in the visual designer.

**Verdict:** Agent Designer cannot do what we need. A coordinator pattern would call our 7 agents sequentially via LLM delegation, defeating the purpose of parallel research.

### 2. "Get code" exports coordinator-style ADK Python

Agent Designer exports ADK Python code with `LlmAgent` sub-agents using model-driven delegation. It does not export `ParallelAgent` or `SequentialAgent` workflow agents. The docs position Agent Designer explicitly as a prototyping step: "Experiment with your agent in Agent Designer before transitioning development to code using ADK."

**Verdict:** Even if we prototype in Agent Designer, we'd need to rewrite the orchestration in ADK code to get parallel execution.

### 3. ADK supports Python, Java, Go — no TypeScript

ADK provides code samples in Python, Java, and Go. There is no TypeScript/JavaScript SDK. Agent Engine deployment uses the Python Vertex AI SDK (`AdkApp` class). The alternative for JS/TS stacks is using the REST API or going DIY (Option C).

**Verdict:** Option B (ADK code) means Python. Option C (DIY Cloud Function) stays in Node.js.

### 4. Agent Engine supports ParallelAgent

No documented restrictions on deploying `ParallelAgent` to Agent Engine. Agent Engine runs any ADK agent wrapped in `AdkApp`. The deployment uses `client.agent_engines.create(agent=AdkApp(agent=root_agent))` — the internal agent structure (parallel, sequential, etc.) is transparent to the runtime.

### 5. Streaming is supported on Agent Engine

`AdkApp.async_stream_query` works both locally and deployed, returning event dictionaries as they're produced. The deployed version uses the `:streamQuery` REST endpoint with `alt=sse`. Bidirectional streaming is also available (preview) for real-time use cases.

**Verdict:** Streaming the multi-step pipeline is feasible. The orchestrator → parallel research → synthesis flow can emit progress events at each stage.

### 6. Architecture pattern mapping

Google Cloud docs define these relevant patterns:

| Pattern | Orchestration | ADK class | Our fit |
|---------|--------------|-----------|---------|
| Coordinator | LLM decides which subagent | `LlmAgent` with sub_agents | Bad — sequential, LLM overhead |
| Parallel | Deterministic fan-out | `ParallelAgent` | Good — all layers run at once |
| Sequential | Deterministic chain | `SequentialAgent` | Good — research then synthesis |
| Hierarchical | Multi-level LLM decomposition | Nested `LlmAgent` | Overkill for us |

Our ideal pattern is **Sequential(Parallel(researchers), synthesizer)** — deterministic, no LLM orchestration overhead. The orchestrator deciding *which* layers to activate could be either an LLM step (smart routing) or hardcoded mapping (simpler).

## Decision: Agent Designer → ADK Python

**Phase 1: Agent Designer (prototyping)**
- Build the 7 specialist sub-agents in Agent Designer console
- Iterate on instructions, tools, and model selection visually
- Test with multi-layer questions in Preview
- Execution will be sequential (coordinator pattern) — that's fine for prototyping
- Focus: get the specialist instructions right, not the orchestration

**Phase 2: ADK Python (production)**
- "Get code" to export the agent definitions as ADK Python
- Rewrite orchestration from coordinator → `ParallelAgent` + `SequentialAgent`
- Deploy to Agent Engine (managed sessions, memory, tracing, streaming)
- Python in the stack is fine

**Why this path:**
- Agent Designer is the fastest way to iterate on 7 sets of specialist instructions
- The instructions, tools, and model choices transfer directly to ADK code
- Only the orchestration layer needs rewriting (coordinator → parallel fan-out)
- ADK gives us everything for Phase 2: MCP tools, data stores, RAG Engine, Memory Bank

## Open Questions (remaining)

1. What's the acceptable latency? 7 parallel Flash calls + 1 Pro synthesis ≈ how many seconds? (need to benchmark)
2. Orchestrator: LLM-based layer selection vs hardcoded use-case→layer mapping?
3. Do we align the frontend (pills, prompts, use cases) before or after building the agents?

## Next Steps

1. ~~Research Agent Designer docs~~ — done, parallel not supported but using it for prototyping
2. ~~Write agent instructions~~ — done, see `docs/agent-multi-agent-instructions.md`
3. **Build orchestrator + 2 sub-agents** (Market Landscape, Guest Intelligence) in Agent Designer
4. **Critical test:** can the orchestrator delegate to multiple sub-agents sequentially and synthesize? (see test plan in `agent-multi-agent-instructions.md`)
5. Adjust orchestrator instructions based on test results
6. Build remaining 5 sub-agents in Agent Designer
7. Full testing and iteration across all 7 layers
8. Add data source mapping to specialist instructions (separate pass)
9. "Get code" → export to ADK Python
10. Rewrite orchestration: coordinator → `SequentialAgent(ParallelAgent(...), synthesizer)`
11. Deploy to Agent Engine
12. Align frontend content with the 7-layer taxonomy
