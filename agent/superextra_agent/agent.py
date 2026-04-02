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

# --- Instruction providers (inject session state into templates) ---

_SCOPER_TEMPLATE = (INSTRUCTIONS_DIR / "research_scoper.md").read_text()

def _scoper_instruction(ctx):
    """Inject places_context into the scoper's instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    return _SCOPER_TEMPLATE.format(places_context=places_context)

_EXECUTOR_TEMPLATE = (INSTRUCTIONS_DIR / "research_executor.md").read_text()

def _executor_instruction(ctx):
    """Inject scope_plan and places_context into the executor's instructions."""
    scope_plan = ctx.state.get("scope_plan", "No research plan available.")
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    return _EXECUTOR_TEMPLATE.format(scope_plan=scope_plan, places_context=places_context)

_PLANNER_TEMPLATE = (INSTRUCTIONS_DIR / "research_planner.md").read_text()

def _planner_instruction(ctx):
    """Inject places_context into the planner's instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    return _PLANNER_TEMPLATE.format(places_context=places_context)

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
    """Create a context enricher instance (ADK requires unique instances per pipeline)."""
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
    """Create a synthesizer instance (ADK requires unique instances per pipeline)."""
    return LlmAgent(
        name=name,
        model=MODEL_GEMINI,
        instruction=_synthesizer_instruction,
        description="Synthesizes findings from all specialist agents into a cohesive report.",
        output_key="final_report",
        generate_content_config=THINKING_CONFIG,
    )


# --- Agent definitions ---

research_scoper = LlmAgent(
    name="research_scoper",
    model=MODEL_GEMINI,
    instruction=_scoper_instruction,
    description="Analyzes the user question, runs reconnaissance, and presents a research plan for user approval.",
    tools=[google_search],
    output_key="scope_plan",
    generate_content_config=THINKING_CONFIG,
)

research_executor = LlmAgent(
    name="research_executor",
    model=MODEL_GEMINI,
    instruction=_executor_instruction,
    description="Executes an approved research plan by dispatching specialist agents.",
    tools=SPECIALIST_TOOLS,
    output_key="research_plan",
    generate_content_config=THINKING_CONFIG,
)

research_planner = LlmAgent(
    name="research_planner",
    model=MODEL_GEMINI,
    instruction=_planner_instruction,
    description="Analyzes the user question, identifies distinct research angles, and delegates to specialist agents.",
    tools=[google_search] + SPECIALIST_TOOLS,
    output_key="research_plan",
    generate_content_config=THINKING_CONFIG,
)

# --- Pipelines ---
# Each pipeline needs its own agent instances (ADK doesn't allow sharing).

# Phase 1: Scope — gathers context and presents plan for user approval (first message)
scoping_pipeline = SequentialAgent(
    name="scoping_pipeline",
    sub_agents=[_make_enricher(), research_scoper],
    description="Gathers Google Places data and presents a research plan for user approval. Use this for the first message in a conversation when the question has enough context to research.",
)

# Phase 2: Execute — runs approved plan through specialists and synthesizer (after confirmation)
execution_pipeline = SequentialAgent(
    name="execution_pipeline",
    sub_agents=[research_executor, _make_synthesizer()],
    description="Executes an approved research plan by dispatching specialists and synthesizing findings. Use this after the user has confirmed a research plan.",
)

# Full pipeline — used for follow-up questions after research is complete
research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_planner, _make_synthesizer()],
    description="Full research pipeline: enriches context, plans and executes research, then synthesizes findings. Use this for follow-up questions after a research report has already been delivered.",
)

# --- Router (root agent) ---

_router = LlmAgent(
    name="router",
    model=MODEL_GEMINI,
    instruction=(INSTRUCTIONS_DIR / "router.md").read_text(),
    description="Routes user questions to scoping, execution, or full research pipeline.",
    sub_agents=[scoping_pipeline, execution_pipeline, research_pipeline],
    output_key="router_response",
    generate_content_config=THINKING_CONFIG,
)

app = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[ChatLoggerPlugin()],
)
root_agent = _router
