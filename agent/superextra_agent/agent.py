from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.apps import App
from google.adk.tools import google_search
from google.genai import Client, types
from .specialists import (
    MODEL_GEMINI, SPECIALIST_GEMINI, THINKING_CONFIG,
    ALL_SPECIALISTS, set_specialist_briefs_tool, RETRY,
)
from .places_tools import get_restaurant_details, find_nearby_restaurants, search_restaurants
from .chat_logger import ChatLoggerPlugin
from pathlib import Path

# Fast model for simple tasks (routing) — no thinking needed.
# Route via global endpoint (same as 3.1 models).
_FAST_MODEL = Gemini(model="gemini-2.5-flash", retry_options=RETRY)
_FAST_MODEL.api_client = Client(
    vertexai=True, location="global",
    http_options=types.HttpOptions(retry_options=RETRY),
)

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

# --- Instruction providers (inject session state into templates) ---

_ORCHESTRATOR_TEMPLATE = (INSTRUCTIONS_DIR / "research_orchestrator.md").read_text()

def _orchestrator_instruction(ctx):
    """Inject places_context into the orchestrator's instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    return _ORCHESTRATOR_TEMPLATE.format(places_context=places_context)

_SYNTHESIZER_TEMPLATE = (INSTRUCTIONS_DIR / "synthesizer.md").read_text()
_SYNTHESIZER_KEYS = [
    "places_context", "research_plan",
    "market_result", "pricing_result", "revenue_result",
    "guest_result", "location_result", "ops_result", "marketing_result",
    "dynamic_result_1", "dynamic_result_2",
]

def _synthesizer_instruction(ctx):
    """Resolve synthesizer template with defaults for missing specialist outputs."""
    values = {k: ctx.state.get(k, "Agent did not produce output.") for k in _SYNTHESIZER_KEYS}
    return _SYNTHESIZER_TEMPLATE.format(**values)

# --- Shared agent config ---

_ENRICHER_INSTRUCTION = (INSTRUCTIONS_DIR / "context_enricher.md").read_text()
_ENRICHER_TOOLS = [get_restaurant_details, find_nearby_restaurants, search_restaurants]


def _make_enricher(name="context_enricher"):
    """Create a context enricher instance."""
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        instruction=_ENRICHER_INSTRUCTION,
        description="Fetches structured Google Places data for the target restaurant and its competitive set.",
        tools=_ENRICHER_TOOLS,
        output_key="places_context",
        generate_content_config=THINKING_CONFIG,
    )


def _make_synthesizer(name="synthesizer"):
    """Create a synthesizer instance."""
    return LlmAgent(
        name=name,
        model=MODEL_GEMINI,
        instruction=_synthesizer_instruction,
        description="Synthesizes findings from all specialist agents into a cohesive report.",
        output_key="final_report",
        generate_content_config=THINKING_CONFIG,
    )


# --- Agent definitions ---

research_orchestrator = LlmAgent(
    name="research_orchestrator",
    model=MODEL_GEMINI,
    instruction=_orchestrator_instruction,
    description="Plans research: reconnaissance, premise audit, and specialist brief assignment.",
    tools=[google_search, set_specialist_briefs_tool],
    output_key="research_plan",
    generate_content_config=THINKING_CONFIG,
)

specialist_pool = ParallelAgent(
    name="specialist_pool",
    sub_agents=ALL_SPECIALISTS,
    description="Runs assigned specialists in parallel. Specialists without briefs skip instantly.",
)

# --- Pipeline ---

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_orchestrator, specialist_pool, _make_synthesizer()],
    description="Enriches context, plans research, runs specialists in parallel, then synthesizes findings.",
)

# --- Router (root agent) ---

_router = LlmAgent(
    name="router",
    model=_FAST_MODEL,
    instruction=(INSTRUCTIONS_DIR / "router.md").read_text(),
    description="Routes user questions to research or asks for clarification.",
    sub_agents=[research_pipeline],
    output_key="router_response",
)

app = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[ChatLoggerPlugin()],
)
root_agent = _router
