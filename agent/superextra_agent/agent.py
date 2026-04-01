from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents import LlmAgent
from google.adk.apps import App
from .specialists import ALL_SPECIALISTS, MODEL, SPECIALIST_MODEL, THINKING_CONFIG
from .places_tools import get_restaurant_details, find_nearby_restaurants, search_restaurants
from .chat_logger import ChatLoggerPlugin
from pathlib import Path

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

context_enricher = LlmAgent(
    name="context_enricher",
    model=SPECIALIST_MODEL,
    instruction=(INSTRUCTIONS_DIR / "context_enricher.md").read_text(),
    description="Fetches structured Google Places data for the target restaurant and its competitive set.",
    tools=[get_restaurant_details, find_nearby_restaurants, search_restaurants],
    output_key="places_context",
    generate_content_config=THINKING_CONFIG,
)

parallel_research = ParallelAgent(
    name="parallel_research",
    sub_agents=ALL_SPECIALISTS,
    description="Runs all specialist research agents in parallel.",
)

synthesizer = LlmAgent(
    name="synthesizer",
    model=MODEL,
    instruction=(INSTRUCTIONS_DIR / "synthesizer.md").read_text(),
    description="Synthesizes findings from all specialist agents into a cohesive report.",
    output_key="final_report",
    generate_content_config=THINKING_CONFIG,
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[context_enricher, parallel_research, synthesizer],
    description="Full research pipeline: enriches context with Google Places data, runs 7 specialist agents in parallel, then synthesizes findings into a cohesive market intelligence report. Use this when the question has enough context (restaurant, location, or area) to research.",
)

_router = LlmAgent(
    name="router",
    model=MODEL,
    instruction=(INSTRUCTIONS_DIR / "router.md").read_text(),
    description="Routes user questions to research or asks for clarification.",
    sub_agents=[research_pipeline],
    output_key="router_response",
    generate_content_config=THINKING_CONFIG,
)

root_agent = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[ChatLoggerPlugin()],
)
