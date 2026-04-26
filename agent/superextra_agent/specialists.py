import logging
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import google_search
from google.genai import Client, types

from .apify_tools import get_google_reviews
from .specialist_catalog import (
    BRIEFABLE_SPECIALISTS,
    ROLE_TITLES,
    SPECIALIST_OUTPUT_KEYS,
    VALID_BRIEF_KEYS,
)
from .tripadvisor_tools import find_tripadvisor_restaurant, get_tripadvisor_reviews
from .web_tools import fetch_web_content

logger = logging.getLogger(__name__)

_dir_override = os.environ.get("SUPEREXTRA_INSTRUCTIONS_DIR")
INSTRUCTIONS_DIR = Path(_dir_override) if _dir_override else Path(__file__).parent / "instructions"

_version = os.environ.get("GEMINI_VERSION", "3.1")

RETRY = types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=60.0)


def _make_gemini(model: str, *, force_global: bool = False) -> Gemini:
    """Create a Gemini instance.

    Routes via the global Vertex AI endpoint when the model family requires
    it (3.1 models) or when `force_global=True` (e.g. 2.5 Flash, which ADK
    would otherwise pin to the container's us-central1 region).

    ADK bakes `GOOGLE_CLOUD_LOCATION=us-central1` into the container
    (matching the Cloud Run region), but several model families don't serve
    from that location. Overriding `api_client` to use `location='global'`
    routes model calls to `https://aiplatform.googleapis.com/` while the
    rest of ADK (sessions, Agent Engine) stays on us-central1.
    """
    g = Gemini(model=model, retry_options=RETRY)
    if _version == "3.1" or force_global:
        g.api_client = Client(
            vertexai=True,
            location="global",
            http_options=types.HttpOptions(retry_options=RETRY),
        )
    return g


if _version == "3.1":
    MODEL = "gemini-3.1-pro-preview"
    SPECIALIST_MODEL = "gemini-3.1-pro-preview-customtools"
    THINKING_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
    )
    MEDIUM_THINKING_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"),
    )
    ORCHESTRATOR_THINKING_CONFIG = MEDIUM_THINKING_CONFIG
else:
    MODEL = "gemini-2.5-pro"
    SPECIALIST_MODEL = MODEL
    THINKING_CONFIG = None
    MEDIUM_THINKING_CONFIG = None
    ORCHESTRATOR_THINKING_CONFIG = None

MODEL_GEMINI = _make_gemini(MODEL)
SPECIALIST_GEMINI = _make_gemini(SPECIALIST_MODEL)


_SOURCE_GUIDANCE = """
## Source quality

For quantitative claims (prices, market size, salary benchmarks, stats), prefer authoritative
primary sources — government data, industry reports, company filings, academic research. Always
cite the source and year. For qualitative signals (sentiment, local dynamics, recent events), any
credible source — news, food blogs, forums, social — is legitimate; local specificity often beats
authoritative-but-generic. If a claim only appears in non-authoritative sources, flag that.
"""


_SPECIALIST_BASE = (INSTRUCTIONS_DIR / "specialist_base.md").read_text()

_NO_BASE = {"gap_researcher"}


def _make_instruction(name: str, brief_key: str | None = None):
    """Create an InstructionProvider that injects places_context and brief into the template."""
    body = (INSTRUCTIONS_DIR / f"{name}.md").read_text()
    if name in _NO_BASE:
        template = body
    else:
        template = (_SPECIALIST_BASE
                    .replace("{specialist_body}", body)
                    .replace("{role_title}", ROLE_TITLES.get(name, name)))
    _brief_key = brief_key or name

    def provider(ctx):
        places_context = ctx.state.get("places_context", "No Google Places data available.")
        # Exposed to specialists that need the deterministic target ID (currently
        # review_analyst.md, so TripAdvisor source pills resolve to the target
        # venue). Other specialist templates don't reference {target_place_id};
        # Python str.format silently ignores unused kwargs.
        target_place_id = ctx.state.get("_target_place_id", "")
        instruction = template.format(
            places_context=places_context,
            target_place_id=target_place_id,
        )
        instruction += _SOURCE_GUIDANCE
        briefs = ctx.state.get("specialist_briefs", {})
        brief = briefs.get(_brief_key, "")
        if brief:
            instruction += f"\n\n## Your research brief\n\n{brief}"
        return instruction

    return provider


def _inject_geo_bias(*, callback_context, llm_request):
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


def _make_skip_callback(name: str):
    """Skip the specialist if the orchestrator didn't assign it a brief."""
    def callback(*, callback_context):
        briefs = callback_context.state.get("specialist_briefs", {})
        if name not in briefs:
            return types.Content(role="model", parts=[types.Part(text="NOT_RELEVANT")])
        return None
    return callback


def _on_model_error(*, callback_context, llm_request, error):
    """Return a graceful fallback when the LLM call fails."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=f"Research unavailable: {type(error).__name__}")]
        )
    )


def _on_tool_error(*, tool, args, tool_context, error):
    """Return a fallback dict when a tool (e.g., google_search) fails."""
    return {"error": f"Tool {tool.name} failed: {type(error).__name__}"}


async def set_specialist_briefs(briefs: dict, tool_context) -> str:
    """Assign research briefs to specialist agents.

    Args:
        briefs: Dict mapping specialist name to brief text.
               Valid names: market_landscape, menu_pricing, revenue_sales,
               guest_intelligence, location_traffic, operations,
               marketing_digital, review_analyst,
               dynamic_researcher_1

    Note: review_analyst has structured review API tools (TripAdvisor).
    Include the restaurant name and area in its brief so it can look up
    the profile. guest_intelligence uses only google_search for independent
    cross-platform research — do not assign both to the same platform.
    """
    invalid = set(briefs.keys()) - VALID_BRIEF_KEYS
    if invalid:
        logger.warning("Unknown specialist brief keys ignored: %s", invalid)
    valid_briefs = {k: v for k, v in briefs.items() if k in VALID_BRIEF_KEYS}
    tool_context.state["specialist_briefs"] = valid_briefs
    return f"Briefs set for: {', '.join(valid_briefs.keys())}"


def _make_specialist(name, description, output_key, tools=None, instruction_name=None, thinking_config=None):
    """Create a specialist agent with standard callbacks and config.

    `include_contents='none'` isolates the model call to its own instruction +
    brief. The instruction provider (`_make_instruction`) already resolves
    every piece of required context from `ctx.state` at runtime (places_context,
    briefs), so the model doesn't need prior ADK conversation history — and
    the history it would otherwise inherit (enricher output, orchestrator
    reasoning, sibling specialist outputs with their own source blocks) was
    pure prompt bloat.
    """
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        description=description,
        instruction=_make_instruction(instruction_name or name, brief_key=name),
        tools=tools or [google_search, fetch_web_content],
        output_key=output_key,
        include_contents="none",
        generate_content_config=thinking_config if thinking_config is not None else THINKING_CONFIG,
        before_agent_callback=_make_skip_callback(name),
        before_model_callback=_inject_geo_bias,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )


# Thinking-level buckets: MEDIUM for pattern-matching / aggregation,
# HIGH for quantitative-inference / strategic work. Catalog entries carry
# `thinking="high" | "medium"`; we map to the actual config at build time.
_THINKING_CONFIGS = {"high": THINKING_CONFIG, "medium": MEDIUM_THINKING_CONFIG}

# Per-specialist tool overrides. Everything not listed here uses the default
# `[google_search, fetch_web_content]` pair.
_SPECIALIST_TOOLS: dict[str, list] = {
    "review_analyst": [find_tripadvisor_restaurant, get_tripadvisor_reviews, get_google_reviews],
}

ALL_SPECIALISTS = [
    _make_specialist(
        s.name,
        s.description,
        s.output_key,
        tools=_SPECIALIST_TOOLS.get(s.name),
        instruction_name=s.instruction_name,
        thinking_config=_THINKING_CONFIGS[s.thinking],
    )
    for s in BRIEFABLE_SPECIALISTS
]

# --- Gap researcher (Phase 2 of two-phase research) ---

_GAP_RESEARCHER_TEMPLATE = (INSTRUCTIONS_DIR / "gap_researcher.md").read_text()

# Context pairs at the top, then every briefable specialist's output_key.
# Derived so new specialists flow automatically.
_GAP_RESEARCHER_KEYS = [
    "places_context", "research_plan",
    *[s.output_key for s in BRIEFABLE_SPECIALISTS],
]


def _gap_researcher_instruction(ctx):
    """Uses `.format()` — it does NOT re-scan inserted values, so specialist
    outputs containing literal `{` / `}` characters flow through verbatim.
    The template itself has no literal braces that would need escaping."""
    values = {k: ctx.state.get(k, "Agent did not produce output.") for k in _GAP_RESEARCHER_KEYS}
    return _GAP_RESEARCHER_TEMPLATE.format(**values)


def _should_run_gap_researcher(callback_context):
    """Decide whether to invoke the gap researcher.

    Gap research is a Gemini Pro + MEDIUM-thinking + 3-search call (~30–50K
    tokens). The prior gate only skipped when no specialist produced any
    output at all, so the step ran on almost every turn. This tightens the
    decision to: inspect only orchestrator-assigned specialists, and run
    when any of them either has no state entry or returned the model-error
    fallback `"Research unavailable: …"` (see `_on_model_error`).

    Unassigned specialists aren't iterated at all (they never appear in
    `specialist_briefs`), so their `NOT_RELEVANT` outputs are irrelevant.
    An orchestrator run with zero assigned specialists skips at the top.
    """
    briefs = callback_context.state.get("specialist_briefs", {}) or {}
    assigned = [n for n in briefs.keys() if n in SPECIALIST_OUTPUT_KEYS]

    if not assigned:
        # Orchestrator dispatched nothing — preserves the previous
        # "no specialist outputs to analyze" skip behavior.
        logger.info("gap gate: skip — no assigned specialists")
        return types.Content(role="model", parts=[types.Part(text="No specialist outputs to analyze.")])

    failures: list[str] = []
    for spec_name in assigned:
        value = callback_context.state.get(SPECIALIST_OUTPUT_KEYS[spec_name])
        if not isinstance(value, str) or value.startswith("Research unavailable: "):
            failures.append(spec_name)

    if not failures:
        logger.info("gap gate: skip — %d/%d assigned specialists succeeded",
                    len(assigned), len(assigned))
        return types.Content(role="model", parts=[types.Part(text="All assigned specialists succeeded; no gaps to research.")])

    logger.info("gap gate: run — %d/%d assigned specialists failed: %s",
                len(failures), len(assigned), failures)
    return None


def make_gap_researcher():
    # `include_contents='none'`: `_gap_researcher_instruction` injects every
    # specialist output + places_context + research_plan from state at runtime,
    # so the model doesn't need prior conversation history.
    return LlmAgent(
        name="gap_researcher",
        model=SPECIALIST_GEMINI,
        description="Analyzes Phase 1 specialist outputs for gaps, contradictions, and underexplored angles.",
        instruction=_gap_researcher_instruction,
        tools=[google_search, fetch_web_content],
        output_key="gap_research_result",
        include_contents="none",
        generate_content_config=MEDIUM_THINKING_CONFIG,
        before_agent_callback=_should_run_gap_researcher,
        before_model_callback=_inject_geo_bias,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )
