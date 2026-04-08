# Agent Capabilities Roadmap

Ideas for making the Superextra agents smarter, the experience better, and perceived value higher — leveraging Google Cloud, Vertex AI, Gemini, and ADK capabilities.

Current architecture: `router → ParallelAgent(7 specialists) → synthesizer`, all using `gemini-2.5-pro` + Google Search.

---

## Tier 1: High-Impact, Low Effort

### 1. Google Maps Places API as a dedicated tool

Biggest gap right now. Specialists search the web for data Google already has structured.

What it unlocks:

- **Ratings, review counts, review text** — real-time, no scraping
- **Price level + price range** — structured competitive pricing
- **Business status** — `CLOSED_PERMANENTLY`, `FUTURE_OPENING` (track openings/closings)
- **Dining attributes** — delivery, takeout, outdoor seating, kids menu, live music, dog-friendly
- **AI-generated review summaries and place summaries** — Gemini-powered, refreshed regularly
- **Area Summaries** — neighborhood-level AI overview (foot traffic, vibe)
- **Nearby Search** — "all Italian restaurants within 1km of this address" with rating/price filters
- **Photos** — up to 10 per restaurant, fetchable by resource name

Build `places_search` and `place_details` tools in ADK. Market Landscape, Menu & Pricing, Guest Intelligence, and Location & Traffic specialists all benefit immediately.

### 2. Geographic bias on Google Search grounding

Google Search grounding accepts **lat/long coordinates** for location-specific results. Currently searches return generic results. Passing target neighborhood coordinates makes every specialist's research hyper-local. Trivial change, immediate improvement.

### 3. Structured output from specialists

Use ADK's `output_schema` on each specialist to force consistent JSON (not free-form markdown). Benefits:

- Synthesizer gets reliable, parseable data
- Frontend can render structured data (tables, comparison cards) natively
- More consistent quality across runs

### 4. Enable thinking/planning on synthesizer

Gemini 2.5+ has configurable "thinking" — internal reasoning before responding. Add `BuiltInPlanner` to the synthesizer so it reasons through how to connect 7 specialist outputs rather than concatenating. Also useful on the router for complex multi-part questions.

---

## Tier 2: Meaningful Capability Upgrades

### 5. Code execution on the synthesizer

Gemini has a built-in Python sandbox with pandas, matplotlib, seaborn, geopandas, scikit-learn. Give the synthesizer a code execution tool:

- Generate pricing comparison charts
- Plot rating distributions across competitors
- Create trend visualizations
- Do statistical analysis ("price is 1.2sigma above neighborhood mean")

Reports with embedded charts feel 10x more valuable than text-only.

### 6. URL context — read competitor websites directly

Gemini can read up to **20 web pages per request** (34MB each). Build a `read_url` tool so specialists can:

- Read full competitor menus from their websites
- Analyze job postings on career pages (Operations specialist)
- Read full review pages instead of search snippets
- Extract data from competitor Instagram/social profiles

### 7. Image analysis pipeline

Combine Places API photos with Gemini vision:

- Fetch restaurant photos → analyze ambiance, food presentation, interior design
- Read menu photos/PDFs → extract structured pricing data
- Compare visual positioning across competitors ("fine-dining plating, casual pricing")
- Analyze competitor Instagram feeds for marketing strategy

Could be a new specialist or a tool available to Marketing & Digital and Guest Intelligence agents.

### 8. Generator-Critic loop (quality gate)

Add a quality-check agent after the synthesizer:

```
router → ParallelAgent(7 specialists) → synthesizer → critic
```

The critic evaluates:

- Are statistics grounded in cited sources?
- Are there hallucinated numbers?
- Are data gaps acknowledged?
- Is the synthesis actually answering the user's question?

If it fails, loop back (ADK's `LoopAgent`) for revision. Difference between "pretty good" and "trustworthy."

### 9. Memory Bank for user context

ADK provides `MemoryService` — persistent, searchable, cross-session knowledge:

- Remember user's restaurant name, cuisine, location, price point
- Track competitive set across sessions
- Store past research findings so agents build on prior work
- "Since you last checked, 2 new competitors opened nearby"

Transforms from a search tool into an **intelligence service that knows you**.

---

## Tier 3: Phase 3 Vision

### 10. BigQuery as an agent tool

When scraper data lands in BigQuery, build a `query_market_data` tool:

- Parameterized SQL queries: "average rating of Italian restaurants in Warsaw Mokotow"
- Price distribution analysis across neighborhoods
- Time-series tracking: competitive landscape changes over 6 months
- Gemini can also run inside BigQuery via `AI.GENERATE_TEXT`

### 11. Vertex AI RAG / File Search for proprietary data

Index industry reports, scraped menus, market research PDFs in a **File Search store** or **RAG Engine**:

- Specialists ground answers in proprietary data + web search
- Supports 100+ file formats (PDF, Excel, CSV, JSON)
- Returns citations pointing to specific document sections

### 12. LoopAgent for iterative research

Currently the pipeline is single-pass. With `LoopAgent`:

```
research → evaluate_coverage → identify_gaps → research_deeper → done?
```

A specialist researches, then evaluates: "Did I find specific pricing data? Do I have recent data? Are there gaps?" If yes, searches again with refined queries. This is how a human analyst works.

### 13. Gemini Live API for voice briefings

Low-latency real-time voice + vision:

- "Give me a 2-minute audio briefing on my competitive landscape"
- Walk past a restaurant, point phone: "What do you know about this place?"
- Voice Q&A during a team meeting

Infrastructure exists: 70 languages, function calling during live sessions, interruption handling.

### 14. Model optimization per role

Not every agent needs the most expensive model:

| Role          | Recommended               | Why                                              |
| ------------- | ------------------------- | ------------------------------------------------ |
| Router        | Gemini 3 Flash            | Fast, good at classification                     |
| 7 Specialists | Gemini 3 Flash            | Parallel, speed matters; Flash is frontier-class |
| Synthesizer   | Gemini 2.5 Pro or 3.1 Pro | Reasoning depth matters here                     |
| Critic        | Gemini 3 Flash            | Evaluation is simpler than synthesis             |

Could cut cost 60-70% while maintaining quality where it counts.

### 15. Eval pipeline in CI

ADK has a built-in eval framework with `.evalset.json` files:

- Build test cases for common restaurant questions with expected answer patterns
- Measure tool trajectory (did the agent call the right tools?)
- Detect hallucinations automatically
- Run `adk eval` in CI to catch regressions when changing instructions

---

## Perceived Value Multipliers

Beyond raw capability, these shape how valuable it _feels_:

1. **Charts and visuals** (code execution) — a pricing chart is worth 1000 words
2. **Structured data cards** (output_schema + frontend) — render competitor comparisons as interactive tables, not paragraphs
3. **Source transparency** (grounding metadata) — show exactly where each claim comes from with clickable links
4. **Memory and continuity** — "Since you last checked, 2 new competitors opened" feels like a dedicated analyst
5. **Speed** — Flash models for specialists + parallel execution = full reports in <15 seconds
6. **Proactive alerts** (future) — push insights without waiting for questions: "A competitor just closed" / "Area average rating dropped"

---

## Recommended Priority Order

1. Places API tools — biggest data quality jump
2. Geographic search bias — trivial change, immediate improvement
3. Structured output — better synthesis, better frontend rendering
4. Code execution on synthesizer — visual reports, huge perceived value
5. Memory Bank — transforms tool into service
6. URL reading — deeper research without scraping
7. Image analysis — unique differentiator
8. Critic agent — trust and quality assurance
9. Model optimization — cost reduction for scaling
10. Everything else — as product matures

---

## Google Cloud Capabilities Reference

### Gemini Model Family (as of March 2026)

- **Gemini 3.1 Pro** — advanced intelligence, complex problem-solving, powerful agentic capabilities
- **Gemini 3 Flash** — frontier-class performance matching larger models at lower cost
- **Gemini 3.1 Flash-Lite** — cost-optimized frontier model
- **Gemini 3.1 Flash Live** — low-latency real-time voice/dialogue
- **Gemini 2.5 Pro** — deep reasoning and coding, configurable "thinking" mode

Key capabilities:

- 1M+ token context windows (~99% retrieval accuracy)
- Structured output with JSON Schema enforcement
- Parallel + compositional function calling
- Built-in Python sandbox (pandas, matplotlib, scikit-learn, geopandas, opencv)
- URL context: read up to 20 web pages per request (34MB each)
- Image analysis: object detection, bounding boxes, text recognition (menus, signage)
- Audio: transcription, translation, emotion detection

### ADK Orchestration Patterns

| Pattern                | ADK Class                             | Status  |
| ---------------------- | ------------------------------------- | ------- |
| Sequential pipeline    | `SequentialAgent`                     | Using   |
| Parallel fan-out       | `ParallelAgent`                       | Using   |
| LLM-driven routing     | `LlmAgent` with `transfer_to_agent()` | Using   |
| Iterative refinement   | `LoopAgent`                           | Not yet |
| Agent as callable tool | `AgentTool`                           | Using   |
| Generator-Critic       | `LoopAgent` + critic sub-agent        | Not yet |
| Built-in planning      | `BuiltInPlanner` / `PlanReActPlanner` | Not yet |

### ADK Memory

- **Session** (short-term): single conversation thread, temporary state
- **Memory** (long-term): searchable cross-session knowledge via `MemoryService`
- **Agent Engine** (managed): cloud-hosted sessions + Memory Bank + observability
