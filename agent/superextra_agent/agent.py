import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.apps import App
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from .chat_logger import ChatLoggerPlugin
from .firestore_progress import FirestoreProgressPlugin
from .places_tools import (
    find_nearby_restaurants,
    get_batch_restaurant_details,
    get_restaurant_details,
    search_restaurants,
)
from .specialist_catalog import SPECIALIST_RESULT_KEYS
from .specialists import (
    ALL_SPECIALISTS,
    MEDIUM_THINKING_CONFIG,
    MODEL_GEMINI,
    ORCHESTRATOR_THINKING_CONFIG,
    SPECIALIST_GEMINI,
    _inject_geo_bias,
    _make_gemini,
    _on_model_error,
    _on_tool_error,
)
from .web_tools import fetch_web_content

# Fast model for routing — no thinking needed.
# Routed via the global Vertex AI endpoint because 2.5 Flash isn't served
# from us-central1 (same constraint as the 3.1 models _make_gemini already
# handles for specialists).
_FAST_MODEL = _make_gemini("gemini-2.5-flash", force_global=True)

_dir_override = os.environ.get("SUPEREXTRA_INSTRUCTIONS_DIR")
INSTRUCTIONS_DIR = Path(_dir_override) if _dir_override else Path(__file__).parent / "instructions"

# --- Instruction providers (inject session state into templates) ---

_RESEARCH_LEAD_TEMPLATE = (INSTRUCTIONS_DIR / "research_lead.md").read_text()
_MARKET_SOURCE_PROFILES = (INSTRUCTIONS_DIR / "market_source_profiles.md").read_text()
_REPORT_WRITER_TEMPLATE = (INSTRUCTIONS_DIR / "report_writer.md").read_text()


def _research_lead_instruction(ctx):
    """Inject places_context and existing results into the research lead instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    existing = [
        label
        for key, label in SPECIALIST_RESULT_KEYS.items()
        if ctx.state.get(key) and ctx.state.get(key) != "Agent did not produce output."
    ]
    follow_up_note = ""
    if existing:
        follow_up_note = (
            "\n\n## Existing research from prior turn\n\n"
            f"Specialists with existing results: {', '.join(existing)}.\n\n"
            "Reuse prior results where they still fit. Call specialists that "
            "update, deepen, or add a complementary angle for the latest question."
        )
    return _RESEARCH_LEAD_TEMPLATE.format(
        places_context=places_context,
        market_source_profiles=_MARKET_SOURCE_PROFILES,
    ) + follow_up_note


# --- Shared agent config ---

_ENRICHER_INSTRUCTION = (INSTRUCTIONS_DIR / "context_enricher.md").read_text()
_ENRICHER_TOOLS = [
    get_restaurant_details,
    get_batch_restaurant_details,
    find_nearby_restaurants,
    search_restaurants,
]


def _skip_enricher_if_cached(*, callback_context):
    """Skip context enricher if places_context already populated from a prior turn."""
    existing = callback_context.state.get("places_context")
    if existing:
        return types.Content(role="model", parts=[types.Part(text=existing)])
    return None


def _make_enricher(name="context_enricher"):
    """Create a context enricher instance."""
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        instruction=_ENRICHER_INSTRUCTION,
        description=(
            "Fetches structured Google Places context for a target restaurant "
            "and competitive set when available."
        ),
        tools=_ENRICHER_TOOLS,
        output_key="places_context",
        generate_content_config=MEDIUM_THINKING_CONFIG,
        before_agent_callback=_skip_enricher_if_cached,
    )


# --- Follow-up agent (answers from existing research, with narrow web fill-in) ---

_FOLLOW_UP_TEMPLATE = (INSTRUCTIONS_DIR / "follow_up.md").read_text()


def _format_specialist_reports(state, default="No specialist notes available."):
    """Format specialist outputs stored in session state."""
    sections = []
    for key, label in SPECIALIST_RESULT_KEYS.items():
        value = state.get(key)
        if value and value != "Agent did not produce output.":
            sections.append(f"### {label}\n\n{value}")
    if not sections:
        return default
    return "\n\n".join(sections)


def _follow_up_instruction(ctx):
    """Inject prior report, specialist notes, and context into follow-up instructions.

    Uses `.format()` — inserted values are not scanned again, so chart-fence
    JSON in `final_report` flows through verbatim.
    """
    values = {
        "final_report": ctx.state.get("final_report", "No prior report available."),
        "specialist_reports": _format_specialist_reports(ctx.state),
        "places_context": ctx.state.get("places_context", "No restaurant data available."),
    }
    return _FOLLOW_UP_TEMPLATE.format(**values)


def _report_writer_instruction(ctx):
    """Inject the full research material into the final report writer."""
    values = {
        "places_context": ctx.state.get("places_context", "No restaurant data available."),
        "specialist_reports": _format_specialist_reports(
            ctx.state,
            default="No specialist reports available.",
        ),
    }
    return _REPORT_WRITER_TEMPLATE.format(**values)


follow_up = LlmAgent(
    name="follow_up",
    model=MODEL_GEMINI,
    instruction=_follow_up_instruction,
    description=(
        "Answers follow-up questions using prior research, specialist notes, "
        "restaurant context, and narrow web fill-in."
    ),
    tools=[google_search, fetch_web_content],
    generate_content_config=MEDIUM_THINKING_CONFIG,
    before_model_callback=_inject_geo_bias,
    on_model_error_callback=_on_model_error,
    on_tool_error_callback=_on_tool_error,
    # Distinct from `final_report` so a follow-up reply doesn't overwrite
    # the original research report in session state. The next follow-up would
    # otherwise read its own shorter answer as "the research."
    output_key="final_report_followup",
)

# --- Router instruction provider ---

_ROUTER_TEMPLATE = (INSTRUCTIONS_DIR / "router.md").read_text()


def _router_instruction(ctx):
    """Append session state info so the router knows whether a report exists."""
    has_report = bool(ctx.state.get("final_report"))
    if has_report:
        note = (
            "\n\n## Session state\n\n"
            "A research report has already been delivered in this conversation."
        )
    else:
        note = "\n\n## Session state\n\nNo research has been done yet in this conversation."
    return _ROUTER_TEMPLATE + note


# --- Agent definitions ---

research_lead = LlmAgent(
    name="research_lead",
    model=MODEL_GEMINI,
    instruction=_research_lead_instruction,
    description="Plans research, calls specialist agents as tools, and records research coverage.",
    tools=[
        google_search,
        fetch_web_content,
        *(AgentTool(agent=spec, include_plugins=True) for spec in ALL_SPECIALISTS),
    ],
    output_key="research_coverage",
    generate_content_config=ORCHESTRATOR_THINKING_CONFIG,
    before_model_callback=_inject_geo_bias,
)

report_writer = LlmAgent(
    name="report_writer",
    model=MODEL_GEMINI,
    instruction=_report_writer_instruction,
    description="Writes the final user-facing research report from specialist evidence.",
    output_key="final_report",
    generate_content_config=ORCHESTRATOR_THINKING_CONFIG,
)

# --- Pipeline ---

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_lead, report_writer],
    description="Enriches context, dispatches research, then writes the final report.",
)

# --- Router (root agent) ---

_router = LlmAgent(
    name="router",
    model=_FAST_MODEL,
    instruction=_router_instruction,
    description="Routes user questions to research, follow-up, or asks for clarification.",
    sub_agents=[research_pipeline, follow_up],
    output_key="router_response",
)

app = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[
        ChatLoggerPlugin(),
        FirestoreProgressPlugin(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
        ),
    ],
)
root_agent = _router
