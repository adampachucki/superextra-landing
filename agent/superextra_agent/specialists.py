import logging
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import google_search
from google.genai import Client, types

from .apify_tools import get_google_reviews
from .tripadvisor_tools import find_tripadvisor_restaurant, get_tripadvisor_reviews
from .web_tools import fetch_web_content

logger = logging.getLogger(__name__)

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

_version = os.environ.get("GEMINI_VERSION", "3.1")

RETRY = types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=60.0)


def _make_gemini(model: str) -> Gemini:
    """Create a Gemini instance, routing to the global endpoint for 3.1 models."""
    g = Gemini(model=model, retry_options=RETRY)
    if _version == "3.1":
        # Gemini 3.1 is only available via the global Vertex AI endpoint.
        # ADK bakes GOOGLE_CLOUD_LOCATION=us-central1 into the container
        # (matching the Cloud Run region), but that location doesn't serve
        # 3.1 yet. Override the api_client to use location='global' so model
        # calls route to https://aiplatform.googleapis.com/ while the rest of
        # ADK (sessions, Agent Engine) keeps using us-central1.
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


_SPECIALIST_BASE = (INSTRUCTIONS_DIR / "specialist_base.md").read_text()

_ROLE_TITLES = {
    "market_landscape": "Market Landscape research agent",
    "menu_pricing": "Menu & Pricing research agent",
    "revenue_sales": "Revenue & Sales research agent",
    "guest_intelligence": "Guest Intelligence research agent",
    "location_traffic": "Location & Traffic research agent",
    "operations": "Operations research agent",
    "marketing_digital": "Marketing & Digital research agent",
    "review_analyst": "Review Analyst",
    "dynamic_researcher": "flexible research agent",
}

_NO_BASE = {"gap_researcher"}


def _make_instruction(name: str, brief_key: str | None = None):
    """Create an InstructionProvider that injects places_context and brief into the template."""
    body = (INSTRUCTIONS_DIR / f"{name}.md").read_text()
    if name in _NO_BASE:
        template = body
    else:
        template = (_SPECIALIST_BASE
                    .replace("{specialist_body}", body)
                    .replace("{role_title}", _ROLE_TITLES.get(name, name)))
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


VALID_BRIEF_KEYS = {
    "market_landscape", "menu_pricing", "revenue_sales",
    "guest_intelligence", "location_traffic", "operations",
    "marketing_digital", "review_analyst", "dynamic_researcher_1",
}


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
    """Create a specialist agent with standard callbacks and config."""
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        description=description,
        instruction=_make_instruction(instruction_name or name, brief_key=name),
        tools=tools or [google_search, fetch_web_content],
        output_key=output_key,
        generate_content_config=thinking_config if thinking_config is not None else THINKING_CONFIG,
        before_agent_callback=_make_skip_callback(name),
        before_model_callback=_inject_geo_bias,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )


# Phase 0: MEDIUM thinking on specialists whose task is pattern-matching / aggregation
# rather than deep reasoning. HIGH stays on quantitative-inference + strategic specialists.
_SPECIALIST_CONFIGS = [
    ("market_landscape", "Analyzes restaurant market dynamics: openings, closings, competitor activity, cuisine trends, saturation, white space.", "market_result", THINKING_CONFIG),
    ("menu_pricing", "Analyzes menus, pricing, delivery markups, promotions, trending dishes.", "pricing_result", THINKING_CONFIG),
    ("revenue_sales", "Estimates revenue, check size, seasonality, channel splits, platform share.", "revenue_result", THINKING_CONFIG),
    ("guest_intelligence", "Analyzes review sentiment, complaint/praise patterns, rating trends.", "guest_result", MEDIUM_THINKING_CONFIG),
    ("location_traffic", "Analyzes foot traffic, demographics, purchasing power, rent, trade areas.", "location_result", MEDIUM_THINKING_CONFIG),
    ("operations", "Analyzes labor market, salary benchmarks, rent, supplier pricing.", "ops_result", THINKING_CONFIG),
    ("marketing_digital", "Analyzes social media, ads, delivery platform presence, web presence.", "marketing_result", MEDIUM_THINKING_CONFIG),
]

ALL_SPECIALISTS = [_make_specialist(n, d, k, thinking_config=tc) for n, d, k, tc in _SPECIALIST_CONFIGS]

ALL_SPECIALISTS.append(_make_specialist(
    "review_analyst",
    "Quantitative review analysis from structured API sources: tourist/local breakdown, rating trends, owner engagement, rankings.",
    "review_result",
    tools=[find_tripadvisor_restaurant, get_tripadvisor_reviews, get_google_reviews],
))

ALL_SPECIALISTS.append(_make_specialist(
    "dynamic_researcher_1",
    "Flexible research agent for investigating specific angles that don't fit the 7 specialist domains.",
    "dynamic_result_1",
    instruction_name="dynamic_researcher",
))

# --- Gap researcher (Phase 2 of two-phase research) ---

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


def make_gap_researcher():
    return LlmAgent(
        name="gap_researcher",
        model=SPECIALIST_GEMINI,
        description="Analyzes Phase 1 specialist outputs for gaps, contradictions, and underexplored angles.",
        instruction=_gap_researcher_instruction,
        tools=[google_search, fetch_web_content],
        output_key="dynamic_result_2",
        generate_content_config=MEDIUM_THINKING_CONFIG,
        before_agent_callback=_skip_if_no_outputs,
        before_model_callback=_inject_geo_bias,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )
