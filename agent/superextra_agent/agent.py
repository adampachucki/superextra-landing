from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.tools import google_search
from .specialists import (
    MODEL_GEMINI, SPECIALIST_GEMINI, THINKING_CONFIG,
    SPECIALIST_TOOLS,
)
from .places_tools import get_restaurant_details, find_nearby_restaurants, search_restaurants
from .chat_logger import ChatLoggerPlugin
from pathlib import Path

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

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

context_enricher = LlmAgent(
    name="context_enricher",
    model=SPECIALIST_GEMINI,
    instruction=(INSTRUCTIONS_DIR / "context_enricher.md").read_text(),
    description="Fetches structured Google Places data for the target restaurant and its competitive set.",
    tools=[get_restaurant_details, find_nearby_restaurants, search_restaurants],
    output_key="places_context",
    generate_content_config=THINKING_CONFIG,
)

research_planner = LlmAgent(
    name="research_planner",
    model=MODEL_GEMINI,
    instruction=(INSTRUCTIONS_DIR / "research_planner.md").read_text(),
    description="Analyzes the user question, identifies distinct research angles, and delegates to specialist agents.",
    tools=[google_search] + SPECIALIST_TOOLS,
    output_key="research_plan",
    generate_content_config=THINKING_CONFIG,
)

synthesizer = LlmAgent(
    name="synthesizer",
    model=MODEL_GEMINI,
    instruction=_synthesizer_instruction,
    description="Synthesizes findings from all specialist agents into a cohesive report.",
    output_key="final_report",
    generate_content_config=THINKING_CONFIG,
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[context_enricher, research_planner, synthesizer],
    description="Full research pipeline: enriches context with Google Places data, plans and executes targeted research, then synthesizes findings into a cohesive market intelligence report. Use this when the question has enough context (restaurant, location, or area) to research.",
)

_router = LlmAgent(
    name="router",
    model=MODEL_GEMINI,
    instruction=(INSTRUCTIONS_DIR / "router.md").read_text(),
    description="Routes user questions to research or asks for clarification.",
    sub_agents=[research_pipeline],
    output_key="router_response",
    generate_content_config=THINKING_CONFIG,
)

app = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[ChatLoggerPlugin()],
)
root_agent = _router
