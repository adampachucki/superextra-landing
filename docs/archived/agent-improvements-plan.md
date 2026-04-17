# Agent Improvements: Source Quality, Geo Bias, Two-Phase Research, Code Execution

> **Status: archived — all five phases shipped.**
> Verified in code as of 2026-04: Phase 1 (source quality guidance in specialist instructions), Phase 2 (`_inject_geo_bias` in `specialists.py`), Phase 3 (`make_gap_researcher` in `specialists.py`), Phase 4 (`_inject_code_execution` + `_embed_chart_images` in `agent.py`). Kept for historical context.

## What this is

A plan to implement four improvements to the Superextra research agent. Each targets a specific weakness in how the agent researches and reports. The improvements are independent — implement them one at a time, test after each, only move on when results look good.

Read `CLAUDE.md` and `instructions/AUTHORING.md` before starting. Both contain critical context about the agent architecture, patterns, and gotchas.

## Background: Current Architecture

The agent is a restaurant industry research system built on Google ADK (Agent Development Kit) using Gemini models on Vertex AI. It lives in `agent/superextra_agent/`.

**Pipeline:** Router → Sequential(enricher → orchestrator → ParallelAgent(10 specialists) → synthesizer)

- **Router** (`router`, gemini-2.5-flash): Classifies user messages — routes research questions to the pipeline, asks for clarification when context is missing
- **Context Enricher** (`context_enricher`, gemini-3.1-pro): Calls Google Places API tools to fetch structured data about the target restaurant and nearby competitors. Writes `places_context` to session state
- **Research Orchestrator** (`research_orchestrator`, gemini-3.1-pro): Runs google_search reconnaissance, audits the question's premises, assigns targeted briefs to specialists via `set_specialist_briefs` tool. Writes `research_plan` to state
- **Specialist Pool** (`specialist_pool`, ParallelAgent): Runs all assigned specialists in parallel. 10 agents total — 7 domain specialists + 1 review analyst (TripAdvisor API) + 2 dynamic researchers. Unassigned specialists skip instantly via `before_agent_callback`
- **Synthesizer** (`synthesizer`, gemini-3.1-pro): Reads all specialist outputs from state, produces the final intelligence report. Has NO tools — purely synthesizes

**Key files:**

- `agent/superextra_agent/agent.py` — pipeline composition, enricher/synthesizer factories, orchestrator definition
- `agent/superextra_agent/specialists.py` — specialist factory (`_make_specialist`), callbacks (`_append_sources`, `_make_skip_callback`), specialist pool, model config
- `agent/superextra_agent/places_tools.py` — 3 Google Places API tools (get_restaurant_details, find_nearby_restaurants, search_restaurants)
- `agent/superextra_agent/instructions/*.md` — 14 instruction files, one per agent role

**Specialist factory pattern** (`specialists.py`):

```python
def _make_specialist(name, description, output_key, tools=None, instruction_name=None):
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        description=description,
        instruction=_make_instruction(instruction_name or name, brief_key=name),
        tools=tools or [google_search],
        output_key=output_key,
        generate_content_config=THINKING_CONFIG,
        before_agent_callback=_make_skip_callback(name),
        after_model_callback=_append_sources,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )
```

**Instruction injection** (`_make_instruction`): Loads a `.md` template, injects `{places_context}` from session state, appends the specialist's brief from `specialist_briefs` dict in state. The brief is set by the orchestrator via the `set_specialist_briefs` tool.

**Session state flow:**

- Enricher writes: `places_context` (text)
- Orchestrator writes: `specialist_briefs` (dict), `research_plan` (text)
- Each specialist writes: `market_result`, `pricing_result`, `revenue_result`, `guest_result`, `location_result`, `ops_result`, `marketing_result`, `review_result`, `dynamic_result_1`, `dynamic_result_2`
- Synthesizer reads all of the above via template variables

**Callback signatures (verified from ADK source):**

- `before_model_callback`: `(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]` — positional args. Return `None` to proceed, return content to skip model call. Supports list of callbacks.
- `after_model_callback`: `(*, callback_context, llm_response)` — keyword-only args
- `before_agent_callback`: `(callback_context)` — return `None` to proceed, return `Content` to skip
- ADK auto-injects `tool_context` if a tool function has a parameter named `tool_context` — no registration needed

---

## Setup: Fix Broken Venv

The venv was built with Python 3.14 which is no longer installed on this machine. Python 3.13 is available.

```bash
cd agent && rm -rf .venv && python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

After recreating, verify:

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v -k "not test_router_evals"
```

(Skip `test_router_evals.py` — it makes live Gemini calls and is not part of the standard test suite.)

---

## Testing Approach

After each change: run unit tests, then run a live query through the full agent and inspect the output.

**Unit tests:**

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v -k "not test_router_evals"
```

**Live test:** Create `agent/test_live.py` and run it to send a real query through the full pipeline. This makes ~10-15 Gemini Pro calls and takes 2-4 minutes. Use `InMemoryRunner` (same pattern as `tests/test_router_evals.py`):

```python
import asyncio, sys, os
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GEMINI_VERSION", "3.1")
# Load .env for GOOGLE_PLACES_API_KEY and SERPAPI_API_KEY
from pathlib import Path
for line in (Path(__file__).parent / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from google.adk.runners import InMemoryRunner
from google.genai import types
from superextra_agent.agent import root_agent

QUERY = (
    "[Context: place_id=ChIJAQBMwGlZIkcRfzreG1Y5GHI, name=Kago Sushi, "
    "address=Mokotowska 4/6, 00-641 Warsaw] "
    "[Date: 2026-04-10] How does Kago Sushi compare to its nearby competition? "
    "Include pricing, ratings, and market positioning."
)

async def main():
    runner = InMemoryRunner(agent=root_agent, app_name="test")
    session = await runner.session_service.create_session(app_name="test", user_id="test")

    async for event in runner.run_async(
        user_id="test", session_id=session.id,
        new_message=types.Content(parts=[types.Part(text=QUERY)], role="user"),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text and part.text != "NOT_RELEVANT":
                    print(f"\n{'='*60}")
                    print(f"AGENT: {event.author}")
                    print(f"{'='*60}")
                    print(part.text[:2000])
                    if len(part.text) > 2000:
                        print(f"\n... ({len(part.text)} chars total)")
                if hasattr(part, "inline_data") and part.inline_data:
                    print(f"\n[INLINE IMAGE: {part.inline_data.mime_type}, {len(part.inline_data.data)} bytes]")

asyncio.run(main())
```

Run with:

```bash
cd agent && PYTHONPATH=. .venv/bin/python test_live.py
```

**Test query rationale:** Kago Sushi is a real restaurant in central Warsaw (Mokotowska 4/6). The query asks for pricing, ratings, and competitive positioning — this triggers multiple specialists with concrete data, produces numerical comparisons (useful for code execution charts), and benefits from geographic bias (Warsaw-specific sources). Run this query at each phase to compare output quality.

**Run the baseline BEFORE making any changes.** Save the output to `agent/test_output_baseline.txt` so you can compare against it after each change.

---

## Phase 1: Source Quality Guidance

### Why

Specialists use google_search and cite whatever surfaces first. For quantitative claims (market size, growth rates, salary benchmarks), authoritative sources like government statistical agencies and industry databases produce more reliable data than random blog posts. But we don't want to limit specialists to only those sources — local blogs, forums, and news surface qualitative insights that formal sources miss.

### What to change

**`specialists.py`** — Add a shared guidance block and modify `_make_instruction` to append it:

```python
_SOURCE_GUIDANCE = """
## Source quality

When making quantitative claims (market size, growth rates, average prices, salary benchmarks,
demographic statistics), prefer authoritative primary sources — government statistical agencies,
industry databases and reports, trade publications, public company filings, and academic research.

For qualitative signals (trends, sentiment, local dynamics, recent events), any credible source
provides legitimate signal — news articles, local media, food blogs, forums, and social media.

When you cite a number, note the source. "Average restaurant revenue: PLN 1.2M (GUS, 2025)"
is more credible than an unsourced figure. If a claim only appears in non-authoritative sources,
note this limitation.

Do not limit yourself to authoritative sources — they often lack local specificity. Use them for
benchmarks and baselines, then add local detail from any credible source.
"""
```

Modify `_make_instruction` to append `_SOURCE_GUIDANCE` after the template is formatted (so `{places_context}` is already resolved) but before the research brief:

```python
def _make_instruction(name: str, brief_key: str | None = None):
    template = (INSTRUCTIONS_DIR / f"{name}.md").read_text()
    _brief_key = brief_key or name

    def provider(ctx):
        places_context = ctx.state.get("places_context", "No Google Places data available.")
        instruction = template.format(places_context=places_context)
        instruction += _SOURCE_GUIDANCE
        briefs = ctx.state.get("specialist_briefs", {})
        brief = briefs.get(_brief_key, "")
        if brief:
            instruction += f"\n\n## Your research brief\n\n{brief}"
        return instruction

    return provider
```

Note: `_SOURCE_GUIDANCE` contains no `{` or `}` characters, so it won't interfere with `str.format()`. It's appended after formatting.

### What to verify

- Unit tests pass
- Run live test query — compare specialist outputs vs baseline
- Look for: numerical claims now cite source types (e.g., "GUS", "Statista", "NRA report")
- Look for: specialists still cite local/informal sources for qualitative insights (not over-constrained)

---

## Phase 2: Google Search Geographic Bias

### Why

When a specialist googles "ramen restaurants Warsaw Mokotow," the search results aren't biased toward the actual coordinates. The Gemini API supports geographic bias via `ToolConfig.retrieval_config.lat_lng` — this tells Google Search grounding to prefer results near a specific point on the map. Since the enricher already fetches the restaurant's lat/lng from Google Places, we can inject it into every specialist's search calls.

### Technical details (verified from ADK source)

The path to set geographic bias on a Gemini API request:

```
llm_request.config.tool_config.retrieval_config.lat_lng
```

Types involved (from `google.genai.types`):

- `GenerateContentConfig.tool_config: Optional[ToolConfig]`
- `ToolConfig.retrieval_config: Optional[RetrievalConfig]`
- `RetrievalConfig.lat_lng: Optional[LatLng]` — also has `language_code: Optional[str]`
- `LatLng` has `latitude: float` and `longitude: float`

Since the location varies per query (different restaurants in different cities), we can't set it statically at agent construction time. We need a `before_model_callback` that reads coordinates from session state and patches the request dynamically.

The existing `THINKING_CONFIG` (set via `generate_content_config`) only touches `thinking_config`, not `tool_config` — no conflict.

ADK auto-injects `tool_context` into any tool function that has a parameter named `tool_context`. No registration or annotation needed — just add the parameter.

### What to change

**`places_tools.py`** — Add `tool_context` parameter to `get_restaurant_details`. After a successful API response, extract lat/lng and write to state:

```python
async def get_restaurant_details(place_id: str, tool_context=None) -> dict:
    # ... existing code ...
    if resp.status_code != 200:
        return {"status": "error", "error_message": f"..."}
    place = resp.json()
    # Store coordinates for geo-biased search
    if tool_context:
        loc = place.get("location", {})
        if loc.get("latitude") and loc.get("longitude"):
            tool_context.state["_target_lat"] = loc["latitude"]
            tool_context.state["_target_lng"] = loc["longitude"]
    return {"status": "success", "place": place}
```

**`specialists.py`** — Add `_inject_geo_bias` callback and wire it into the factory:

```python
def _inject_geo_bias(callback_context, llm_request):
    """Bias google_search results toward the target restaurant's location."""
    lat = callback_context.state.get("_target_lat")
    lng = callback_context.state.get("_target_lng")
    if not lat or not lng:
        return None
    llm_request.config = llm_request.config or types.GenerateContentConfig()
    llm_request.config.tool_config = llm_request.config.tool_config or types.ToolConfig()
    llm_request.config.tool_config.retrieval_config = types.RetrievalConfig(
        lat_lng=types.LatLng(latitude=lat, longitude=lng),
    )
    return None
```

Set `before_model_callback=_inject_geo_bias` on `_make_specialist`. The factory currently doesn't set `before_model_callback`, so just add it.

**`agent.py`** — Import `_inject_geo_bias` from specialists and set it on `research_orchestrator` too (it also uses google_search for reconnaissance):

```python
from .specialists import (
    MODEL_GEMINI, SPECIALIST_GEMINI, THINKING_CONFIG,
    ALL_SPECIALISTS, set_specialist_briefs, RETRY,
    _inject_geo_bias,
)

research_orchestrator = LlmAgent(
    ...
    before_model_callback=_inject_geo_bias,
)
```

### What to verify

- Unit tests pass — add a test for `_inject_geo_bias`:
  - When state has `_target_lat`/`_target_lng`, callback sets `retrieval_config.lat_lng`
  - When state is missing coordinates, callback returns `None` without modifying request
- Run live test query — check the output for more Warsaw-specific, Polish-language sources
- In chat logger JSONL (if available), model requests should show `retrieval_config` populated

---

## Phase 3: Two-Phase Research

### Why

Both dynamic researchers currently run in parallel with all other specialists, getting briefs from the orchestrator upfront. `dynamic_researcher_2` could be far more valuable as a gap-filler that runs AFTER Phase 1 specialists complete, reads their outputs, and investigates what they missed — contradictions between specialists, angles nobody covered, surprising findings worth deeper investigation.

### Pipeline change

```
Before: enricher → orchestrator → ParallelAgent([7 core + review_analyst + dynamic_1 + dynamic_2]) → synthesizer
After:  enricher → orchestrator → ParallelAgent([7 core + review_analyst + dynamic_1]) → gap_researcher → synthesizer
```

The gap researcher IS dynamic_researcher_2 repurposed — same name in state (`dynamic_result_2`), new role.

### What to change

**`specialists.py`:**

1. Change the loop at line 200-206 to only create `dynamic_researcher_1`:

```python
ALL_SPECIALISTS.append(_make_specialist(
    "dynamic_researcher_1",
    "Flexible research agent for investigating specific angles that don't fit the 7 specialist domains.",
    "dynamic_result_1",
    instruction_name="dynamic_researcher",
))
```

2. Update the `set_specialist_briefs` docstring to remove `dynamic_researcher_2` from valid names.

3. Add gap researcher instruction provider — like `_synthesizer_instruction` in `agent.py`, it resolves all specialist output keys from state:

```python
_GAP_RESEARCHER_TEMPLATE = (INSTRUCTIONS_DIR / "gap_researcher.md").read_text()
_GAP_RESEARCHER_KEYS = [
    "places_context", "research_plan",
    "market_result", "pricing_result", "revenue_result",
    "guest_result", "location_result", "ops_result", "marketing_result",
    "review_result", "dynamic_result_1",
]

def _gap_researcher_instruction(ctx):
    values = {k: ctx.state.get(k, "Agent did not produce output.") for k in _GAP_RESEARCHER_KEYS}
    return _GAP_RESEARCHER_TEMPLATE.format(**values)
```

4. Add skip callback for when there's nothing to gap-check:

```python
def _skip_if_no_outputs(callback_context):
    """Skip gap researcher if no specialists produced output."""
    output_keys = [
        "market_result", "pricing_result", "revenue_result",
        "guest_result", "location_result", "ops_result", "marketing_result",
        "review_result", "dynamic_result_1",
    ]
    default = "Agent did not produce output."
    if all(callback_context.state.get(k, default) == default for k in output_keys):
        return types.Content(role="model", parts=[types.Part(text="No specialist outputs to analyze.")])
    return None
```

5. Export a factory function:

```python
def make_gap_researcher():
    return LlmAgent(
        name="gap_researcher",
        model=SPECIALIST_GEMINI,
        description="Analyzes Phase 1 specialist outputs for gaps, contradictions, and underexplored angles.",
        instruction=_gap_researcher_instruction,
        tools=[google_search],
        output_key="dynamic_result_2",
        generate_content_config=THINKING_CONFIG,
        before_agent_callback=_skip_if_no_outputs,
        before_model_callback=_inject_geo_bias,
        after_model_callback=_append_sources,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )
```

Note: it writes to `dynamic_result_2` so the synthesizer picks it up without changes (the synthesizer template already has `{dynamic_result_2}`).

**`instructions/gap_researcher.md`** (new file):

Write an instruction file for the gap researcher. It should:

- Receive all specialist outputs, places_context, and research_plan as template variables
- Read through Phase 1 findings and identify: gaps (angles nobody covered), contradictions between specialists, surprising findings worth deeper investigation, weak evidence behind important claims
- Run targeted google_search to fill the 1-3 most important gaps
- If Phase 1 was thorough and no meaningful gaps exist, return a short "No significant gaps identified" message rather than inventing work
- End with a Brief alignment statement (consistency with other specialists)
- Follow the same patterns as `dynamic_researcher.md` for tone, source quality, and research methodology

Template variables it needs: `{places_context}`, `{research_plan}`, `{market_result}`, `{pricing_result}`, `{revenue_result}`, `{guest_result}`, `{location_result}`, `{ops_result}`, `{marketing_result}`, `{review_result}`, `{dynamic_result_1}`

Read `instructions/AUTHORING.md` before writing this file.

**`agent.py`:**

Import and insert into pipeline:

```python
from .specialists import (
    MODEL_GEMINI, SPECIALIST_GEMINI, THINKING_CONFIG,
    ALL_SPECIALISTS, set_specialist_briefs, RETRY,
    _inject_geo_bias, make_gap_researcher,
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_orchestrator, specialist_pool, make_gap_researcher(), _make_synthesizer()],
    ...
)
```

**`instructions/research_orchestrator.md`:**

- Remove `dynamic_researcher_2` from the available specialist agents list (line 74)
- Add a note after the specialist list: "A gap-analysis researcher runs automatically after all specialists complete. It reads their outputs and investigates gaps, contradictions, or underexplored angles. You do not need to assign it a brief."

### What to verify

- Unit tests pass — add test for `_gap_researcher_instruction` resolving template variables, and `_skip_if_no_outputs` behavior
- Run live test query:
  - Gap researcher output should appear AFTER all specialist outputs (check ordering in printed output)
  - Gap researcher should reference specific findings from Phase 1 ("Market Landscape found X, but did not cover Y")
  - If Phase 1 was thorough, gap researcher should be brief rather than inventing filler
- Compare final report vs Phase 2 — should the synthesizer's report be richer with the gap researcher's additional findings?

---

## Phase 4: Code Execution on Synthesizer

### Why

The synthesizer produces text-only reports even when specialists provide rich numerical data — pricing tables, rating distributions, revenue estimates. Gemini has a built-in code execution tool that runs Python (with matplotlib, numpy, pandas) in a sandbox and returns charts as inline base64 PNG images. This would let the synthesizer generate pricing comparison bar charts, rating distributions, market share breakdowns — turning text reports into visual analysis.

### Technical details (verified from ADK source)

`BuiltInCodeExecutor` (at `google.adk.code_executors.built_in_code_executor`) works by appending `types.Tool(code_execution=types.ToolCodeExecution())` to the model request's tools list. It checks `is_gemini_2_or_above(model)` — `gemini-3.1-pro-preview` passes this (version `3.1`, major `3` >= 2).

**Critical constraint:** `BuiltInCodeExecutor` cannot coexist with other tools (function tools, google_search, etc.) on the same agent. The synthesizer currently has NO tools — it only reads specialist outputs via instruction template variables. So there's no conflict.

Set via `code_executor=` parameter on `LlmAgent`, NOT via `tools=`.

**Sandbox capabilities:**

- Python only, 30-second timeout, no network access, no filesystem
- Available libraries: numpy, pandas, matplotlib (only supported chart renderer), scipy, scikit-learn, seaborn, geopandas, pillow, sympy
- Charts returned as inline `Part(inline_data=...)` with `mime_type="image/png"` and base64 data
- Model can iterate up to 5 times on errors within a single API call

### What to change

**`agent.py`:**

```python
from google.adk.code_executors import BuiltInCodeExecutor

def _make_synthesizer(name="synthesizer"):
    return LlmAgent(
        name=name,
        model=MODEL_GEMINI,
        instruction=_synthesizer_instruction,
        description="Synthesizes findings from all specialist agents into a cohesive report.",
        output_key="final_report",
        generate_content_config=THINKING_CONFIG,
        code_executor=BuiltInCodeExecutor(),
    )
```

**`instructions/synthesizer.md`** — Append after existing content:

```markdown
## Data visualization

When specialist findings include numerical data suitable for comparison — pricing across competitors,
rating distributions, revenue estimates, market share splits — generate a chart using matplotlib.

- Bar or horizontal bar charts for pricing or rating comparisons across competitors
- Pie charts for market share or channel splits
- Line charts for trends over time (rating changes, seasonal patterns)

Only generate charts when concrete numerical data exists in the specialist findings. Do not chart
estimated or placeholder data. Keep charts clean and readable: labeled axes, clear title, use
seaborn styling (`import seaborn as sns; sns.set_style("whitegrid")`).

If no numerical data in the findings is suitable for visualization, skip chart generation entirely
and produce a text-only report.
```

### What to verify

- Unit tests pass
- Run live test query — look for:
  - `[INLINE IMAGE: image/png, N bytes]` in the test script output (the script prints inline_data parts)
  - The synthesizer should generate charts when pricing/rating data exists
  - Charts should contain real data from specialists, not made-up numbers
- If no charts appear, check: is the synthesizer model actually getting code_execution in its tools? Are there error messages?
- Note: the frontend (agent.superextra.ai) may not render inline images yet — that's a separate piece of work. The value here is in the API response.

---

## Phase 5: Final Validation

Run the test query one final time with all four changes active. Compare against the baseline output saved in Phase 0.

**Check:**

- **Source quality:** Are numerical claims in specialist outputs attributed to source types? Do you see references to government agencies, industry reports alongside local sources?
- **Local relevance:** Do search results reference Warsaw-specific sources, Polish-language content, local neighborhoods?
- **Gap coverage:** Did the gap researcher identify and fill meaningful gaps? Or did it correctly identify "no significant gaps" when Phase 1 was thorough?
- **Visualization:** Are charts present in the synthesizer's response when numerical data exists?
- **Overall quality:** Is the final report meaningfully better than baseline?

After validation, clean up `agent/test_live.py` and any saved output files. Run the full test suite one more time:

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v -k "not test_router_evals"
```

Commit all changes together with a descriptive message.
