from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import google_search
from google.genai import Client, types
from pathlib import Path
from urllib.parse import urlparse
from .tripadvisor_tools import find_tripadvisor_restaurant, get_tripadvisor_reviews
import os

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

_version = os.environ.get("GEMINI_VERSION", "3.1")

RETRY = types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=60.0)


def _append_sources(*, callback_context, llm_response):
    """Append grounding source URLs to the model response text.

    AgentTool only propagates the text output — grounding metadata is lost.
    By appending sources to the text, they travel through to session state
    where the Cloud Function can extract them.
    """
    gm = llm_response.grounding_metadata
    # Inject search queries into state so they appear in the SSE stream
    if gm and gm.web_search_queries and callback_context:
        callback_context.state["_web_search_queries"] = list(gm.web_search_queries)
    if not gm or not gm.grounding_chunks:
        return llm_response
    urls = []
    seen = set()
    for chunk in gm.grounding_chunks:
        if chunk.web and chunk.web.uri and chunk.web.uri not in seen:
            title = chunk.web.title or chunk.web.uri
            uri = chunk.web.uri
            # domain is often None; extract from URI if possible, else use title
            domain = chunk.web.domain
            if not domain and uri:
                try:
                    hostname = urlparse(uri).hostname or ""
                    if hostname and "vertexaisearch" not in hostname:
                        domain = hostname
                except Exception:
                    pass
            if not domain:
                domain = chunk.web.title or ""
            urls.append((title, uri, domain))
            seen.add(chunk.web.uri)
    if not urls:
        return llm_response
    # Append a Sources section to the last text part.
    # Format: - [title](uri){domain} — domain suffix lets the frontend
    # display the real source host even when uri is a redirect URL.
    if llm_response.content and llm_response.content.parts:
        for part in reversed(llm_response.content.parts):
            if part.text:
                lines = []
                for title, uri, domain in urls:
                    entry = f"- [{title}]({uri})"
                    if domain:
                        entry += "{" + domain + "}"
                    lines.append(entry)
                sources_md = "\n\n## Sources\n" + "\n".join(lines)
                part.text += sources_md
                break
    return llm_response


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
else:
    MODEL = "gemini-2.5-pro"
    SPECIALIST_MODEL = MODEL
    THINKING_CONFIG = None

MODEL_GEMINI = _make_gemini(MODEL)
SPECIALIST_GEMINI = _make_gemini(SPECIALIST_MODEL)


def _make_instruction(name: str, brief_key: str | None = None):
    """Create an InstructionProvider that injects places_context and brief into the template."""
    template = (INSTRUCTIONS_DIR / f"{name}.md").read_text()
    _brief_key = brief_key or name

    def provider(ctx):
        places_context = ctx.state.get("places_context", "No Google Places data available.")
        instruction = template.format(places_context=places_context)
        briefs = ctx.state.get("specialist_briefs", {})
        brief = briefs.get(_brief_key, "")
        if brief:
            instruction += f"\n\n## Your research brief\n\n{brief}"
        return instruction

    return provider


def _make_skip_callback(name: str):
    """Skip the specialist if the orchestrator didn't assign it a brief."""
    def callback(callback_context):
        briefs = callback_context.state.get("specialist_briefs", {})
        if name not in briefs:
            return types.Content(role="model", parts=[types.Part(text="NOT_RELEVANT")])
        return None
    return callback


def _on_model_error(callback_context, llm_request, error):
    """Return a graceful fallback when the LLM call fails."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=f"Research unavailable: {type(error).__name__}")]
        )
    )


def _on_tool_error(tool, args, tool_context, error):
    """Return a fallback dict when a tool (e.g., google_search) fails."""
    return {"error": f"Tool {tool.name} failed: {type(error).__name__}"}


async def set_specialist_briefs(briefs: dict, tool_context) -> str:
    """Assign research briefs to specialist agents.

    Args:
        briefs: Dict mapping specialist name to brief text.
               Valid names: market_landscape, menu_pricing, revenue_sales,
               guest_intelligence, location_traffic, operations,
               marketing_digital, review_analyst,
               dynamic_researcher_1, dynamic_researcher_2

    Note: review_analyst has structured review API tools (TripAdvisor).
    Include the restaurant name and area in its brief so it can look up
    the profile. guest_intelligence uses only google_search for independent
    cross-platform research — do not assign both to the same platform.
    """
    tool_context.state["specialist_briefs"] = briefs
    return f"Briefs set for: {', '.join(briefs.keys())}"


def _make_specialist(name, description, output_key, tools=None, instruction_name=None):
    """Create a specialist agent with standard callbacks and config."""
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


_SPECIALIST_CONFIGS = [
    ("market_landscape", "Analyzes restaurant market dynamics: openings, closings, competitor activity, cuisine trends, saturation, white space.", "market_result"),
    ("menu_pricing", "Analyzes menus, pricing, delivery markups, promotions, trending dishes.", "pricing_result"),
    ("revenue_sales", "Estimates revenue, check size, seasonality, channel splits, platform share.", "revenue_result"),
    ("guest_intelligence", "Analyzes review sentiment, complaint/praise patterns, rating trends.", "guest_result"),
    ("location_traffic", "Analyzes foot traffic, demographics, purchasing power, rent, trade areas.", "location_result"),
    ("operations", "Analyzes labor market, salary benchmarks, rent, supplier pricing.", "ops_result"),
    ("marketing_digital", "Analyzes social media, ads, delivery platform presence, web presence.", "marketing_result"),
]

ALL_SPECIALISTS = [_make_specialist(n, d, k) for n, d, k in _SPECIALIST_CONFIGS]

ALL_SPECIALISTS.append(_make_specialist(
    "review_analyst",
    "Quantitative review analysis from structured API sources: tourist/local breakdown, rating trends, owner engagement, rankings.",
    "review_result",
    tools=[find_tripadvisor_restaurant, get_tripadvisor_reviews],
))

for i in (1, 2):
    ALL_SPECIALISTS.append(_make_specialist(
        f"dynamic_researcher_{i}",
        "Flexible research agent for investigating specific angles that don't fit the 7 specialist domains.",
        f"dynamic_result_{i}",
        instruction_name="dynamic_researcher",
    ))
