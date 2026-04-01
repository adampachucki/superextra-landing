from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search
from google.adk.tools import AgentTool
from google.genai import Client, types
from pathlib import Path
import os

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
else:
    MODEL = "gemini-2.5-pro"
    SPECIALIST_MODEL = MODEL
    THINKING_CONFIG = None

MODEL_GEMINI = _make_gemini(MODEL)
SPECIALIST_GEMINI = _make_gemini(SPECIALIST_MODEL)


def _make_instruction(name: str):
    """Create an InstructionProvider that injects places_context into the template."""
    template = (INSTRUCTIONS_DIR / f"{name}.md").read_text()

    def provider(ctx):
        places_context = ctx.state.get("places_context", "No Google Places data available.")
        return template.format(places_context=places_context)

    return provider


market_landscape = LlmAgent(
    name="market_landscape",
    model=SPECIALIST_GEMINI,
    description="Analyzes restaurant market dynamics: openings, closings, competitor activity, cuisine trends, saturation, white space.",
    instruction=_make_instruction("market_landscape"),
    tools=[google_search],
    output_key="market_result",
    generate_content_config=THINKING_CONFIG,
)

menu_pricing = LlmAgent(
    name="menu_pricing",
    model=SPECIALIST_GEMINI,
    description="Analyzes menus, pricing, delivery markups, promotions, trending dishes.",
    instruction=_make_instruction("menu_pricing"),
    tools=[google_search],
    output_key="pricing_result",
    generate_content_config=THINKING_CONFIG,
)

revenue_sales = LlmAgent(
    name="revenue_sales",
    model=SPECIALIST_GEMINI,
    description="Estimates revenue, check size, seasonality, channel splits, platform share.",
    instruction=_make_instruction("revenue_sales"),
    tools=[google_search],
    output_key="revenue_result",
    generate_content_config=THINKING_CONFIG,
)

guest_intelligence = LlmAgent(
    name="guest_intelligence",
    model=SPECIALIST_GEMINI,
    description="Analyzes review sentiment, complaint/praise patterns, rating trends.",
    instruction=_make_instruction("guest_intelligence"),
    tools=[google_search],
    output_key="guest_result",
    generate_content_config=THINKING_CONFIG,
)

location_traffic = LlmAgent(
    name="location_traffic",
    model=SPECIALIST_GEMINI,
    description="Analyzes foot traffic, demographics, purchasing power, rent, trade areas.",
    instruction=_make_instruction("location_traffic"),
    tools=[google_search],
    output_key="location_result",
    generate_content_config=THINKING_CONFIG,
)

operations = LlmAgent(
    name="operations",
    model=SPECIALIST_GEMINI,
    description="Analyzes labor market, salary benchmarks, rent, supplier pricing.",
    instruction=_make_instruction("operations"),
    tools=[google_search],
    output_key="ops_result",
    generate_content_config=THINKING_CONFIG,
)

marketing_digital = LlmAgent(
    name="marketing_digital",
    model=SPECIALIST_GEMINI,
    description="Analyzes social media, ads, delivery platform presence, web presence.",
    instruction=_make_instruction("marketing_digital"),
    tools=[google_search],
    output_key="marketing_result",
    generate_content_config=THINKING_CONFIG,
)

dynamic_researcher_1 = LlmAgent(
    name="dynamic_researcher_1",
    model=SPECIALIST_GEMINI,
    description="Flexible research agent for investigating specific angles that don't fit the 7 specialist domains. Provide a clear, specific research brief.",
    instruction=_make_instruction("dynamic_researcher"),
    tools=[google_search],
    output_key="dynamic_result_1",
    generate_content_config=THINKING_CONFIG,
)

dynamic_researcher_2 = LlmAgent(
    name="dynamic_researcher_2",
    model=SPECIALIST_GEMINI,
    description="Second flexible research agent for investigating additional angles that don't fit the 7 specialist domains. Provide a clear, specific research brief.",
    instruction=_make_instruction("dynamic_researcher"),
    tools=[google_search],
    output_key="dynamic_result_2",
    generate_content_config=THINKING_CONFIG,
)

SPECIALIST_TOOLS = [
    AgentTool(agent=market_landscape, skip_summarization=True),
    AgentTool(agent=menu_pricing, skip_summarization=True),
    AgentTool(agent=revenue_sales, skip_summarization=True),
    AgentTool(agent=guest_intelligence, skip_summarization=True),
    AgentTool(agent=location_traffic, skip_summarization=True),
    AgentTool(agent=operations, skip_summarization=True),
    AgentTool(agent=marketing_digital, skip_summarization=True),
    AgentTool(agent=dynamic_researcher_1, skip_summarization=True),
    AgentTool(agent=dynamic_researcher_2, skip_summarization=True),
]
