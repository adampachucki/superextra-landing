import logging

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.apps import App
from google.adk.tools import google_search
from google.genai import Client, types

from .log_ctx import worker_sid
from .web_tools import fetch_web_content
logger = logging.getLogger(__name__)

from .specialists import (
    MODEL_GEMINI, SPECIALIST_GEMINI, THINKING_CONFIG, MEDIUM_THINKING_CONFIG,
    ORCHESTRATOR_THINKING_CONFIG,
    ALL_SPECIALISTS, set_specialist_briefs, RETRY,
    _inject_geo_bias, make_gap_researcher,
)
from .places_tools import get_restaurant_details, get_batch_restaurant_details, find_nearby_restaurants, search_restaurants
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

_SPECIALIST_RESULT_KEYS = {
    "market_result": "Market Landscape", "pricing_result": "Menu & Pricing",
    "revenue_result": "Revenue & Sales", "guest_result": "Guest Intelligence",
    "location_result": "Location & Traffic", "ops_result": "Operations",
    "marketing_result": "Marketing & Digital", "review_result": "Review Analysis",
    "dynamic_result_1": "Dynamic Research",
}

def _orchestrator_instruction(ctx):
    """Inject places_context and existing results into the orchestrator's instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    existing = [label for key, label in _SPECIALIST_RESULT_KEYS.items()
                if ctx.state.get(key) and ctx.state.get(key) != "Agent did not produce output."]
    follow_up_note = ""
    if existing:
        prior_plan = ctx.state.get("research_plan", "Not available.")
        follow_up_note = (
            f"\n\n## Existing research from prior turn\n\n"
            f"Specialists with existing results: {', '.join(existing)}.\n\n"
            f"Prior research plan:\n{prior_plan}\n\n"
            f"Only assign specialists for angles NOT already covered, "
            f"unless the follow-up explicitly needs to update or deepen an existing area."
        )
    return _ORCHESTRATOR_TEMPLATE.format(places_context=places_context) + follow_up_note

_SYNTHESIZER_TEMPLATE = (INSTRUCTIONS_DIR / "synthesizer.md").read_text()
_SYNTHESIZER_KEYS = [
    "places_context", "research_plan",
    "market_result", "pricing_result", "revenue_result",
    "guest_result", "location_result", "ops_result", "marketing_result",
    "review_result", "dynamic_result_1", "dynamic_result_2",
]

def _synthesizer_instruction(ctx):
    """Resolve synthesizer template with defaults for missing specialist outputs."""
    values = {k: ctx.state.get(k, "Agent did not produce output.") for k in _SYNTHESIZER_KEYS}
    return _SYNTHESIZER_TEMPLATE.format(**values)

# --- Shared agent config ---

_ENRICHER_INSTRUCTION = (INSTRUCTIONS_DIR / "context_enricher.md").read_text()
_ENRICHER_TOOLS = [get_restaurant_details, get_batch_restaurant_details, find_nearby_restaurants, search_restaurants]


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
        description="Fetches structured Google Places data for the target restaurant and its competitive set.",
        tools=_ENRICHER_TOOLS,
        output_key="places_context",
        generate_content_config=MEDIUM_THINKING_CONFIG,
        before_agent_callback=_skip_enricher_if_cached,
    )


_FALLBACK_SECTIONS = [
    ("market_result", "Market Landscape"),
    ("pricing_result", "Menu & Pricing"),
    ("revenue_result", "Revenue & Sales"),
    ("guest_result", "Guest Intelligence"),
    ("location_result", "Location & Traffic"),
    ("ops_result", "Operations"),
    ("marketing_result", "Marketing & Digital"),
    ("review_result", "Review Analysis"),
    ("dynamic_result_1", "Additional Research"),
    ("dynamic_result_2", "Gap Research"),
]


def _build_fallback_report(state, reason: str) -> str:
    """Concatenate specialist outputs when the synthesizer fails to produce a response.

    Triggers: empty content, no text parts, or an error_code from the model.
    Guarantees `final_report` is populated so the user sees a usable reply
    instead of an `empty_or_malformed_reply` terminal state.
    """
    # `reason` is for the structured synth_outcome log, not the user banner.
    parts = [
        "# Research findings\n\n",
        "_Final synthesis didn't produce a response. Full research findings below._\n\n",
    ]
    had_content = False
    for key, label in _FALLBACK_SECTIONS:
        val = state.get(key)
        if not val or val == "Agent did not produce output.":
            continue
        had_content = True
        parts.append(f"## {label}\n\n{val}\n\n")
    if not had_content:
        parts.append(
            "_No specialist outputs were available in session state. Please try rephrasing your question._\n"
        )
    return "".join(parts)


def _synth_fallback_callback(*, callback_context, llm_response):
    """Guarantee `final_report` is always populated.

    The synthesizer is a plain text-generating agent (no tools). If the model
    returns an error_code, an empty response, or parts with no usable text,
    substitute a text-only report stitched from the specialist outputs in
    state. Emit a structured `synth_outcome` log for rate tracking.
    """
    def _outcome_extra(reason: str) -> dict:
        return {"event": "synth_outcome", "reason": reason, "sid": worker_sid.get()}

    error_code = getattr(llm_response, "error_code", None)
    if error_code:
        logger.warning("synth outcome %s", error_code, extra=_outcome_extra(error_code))
        return LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(text=_build_fallback_report(callback_context.state, error_code))],
        ))

    if not llm_response.content or not llm_response.content.parts:
        logger.warning("synth outcome empty_response", extra=_outcome_extra("empty_response"))
        return LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(text=_build_fallback_report(callback_context.state, "empty_response"))],
        ))

    if not any(getattr(p, "text", None) and p.text.strip() for p in llm_response.content.parts):
        logger.warning("synth outcome no_text_parts", extra=_outcome_extra("no_text_parts"))
        return LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part(text=_build_fallback_report(callback_context.state, "no_text_parts"))],
        ))

    logger.info("synth outcome ok", extra=_outcome_extra("ok"))
    return llm_response


def _make_synthesizer(name="synthesizer"):
    """Create a synthesizer instance. Text-only — charts are emitted as
    ```chart <JSON>``` fenced blocks and rendered by the frontend.

    `include_contents='none'`: `_synthesizer_instruction` already injects
    every specialist output + research_plan + places_context from state at
    runtime, so the model doesn't need prior ADK conversation history.
    This is the highest-value flip in the pipeline — synth requests in the
    observed runs carried content_count ~25, most of which was stale history.
    """
    return LlmAgent(
        name=name,
        model=MODEL_GEMINI,
        instruction=_synthesizer_instruction,
        description="Synthesizes findings from all specialist agents into a cohesive report.",
        output_key="final_report",
        include_contents="none",
        generate_content_config=THINKING_CONFIG,
        after_model_callback=_synth_fallback_callback,
    )


# --- Follow-up agent (answers from existing research, no tools) ---

_FOLLOW_UP_TEMPLATE = (INSTRUCTIONS_DIR / "follow_up.md").read_text()

def _follow_up_instruction(ctx):
    """Inject prior report and context into the follow-up agent's instructions."""
    replacements = {
        "final_report": ctx.state.get("final_report", "No prior report available."),
        "places_context": ctx.state.get("places_context", "No restaurant data available."),
        "research_plan": ctx.state.get("research_plan", "No research plan available."),
    }
    # Use replace() instead of .format() — LLM output may contain curly braces.
    result = _FOLLOW_UP_TEMPLATE
    for key, value in replacements.items():
        result = result.replace(f"{{{key}}}", value)
    return result

follow_up = LlmAgent(
    name="follow_up",
    model=_FAST_MODEL,
    instruction=_follow_up_instruction,
    description="Answers simple follow-up questions using existing research data. No tools.",
    output_key="final_report",
)

# --- Router instruction provider ---

_ROUTER_TEMPLATE = (INSTRUCTIONS_DIR / "router.md").read_text()

def _router_instruction(ctx):
    """Append session state info so the router knows whether a report exists."""
    has_report = bool(ctx.state.get("final_report"))
    if has_report:
        note = "\n\n## Session state\n\nA research report has already been delivered in this conversation."
    else:
        note = "\n\n## Session state\n\nNo research has been done yet in this conversation."
    return _ROUTER_TEMPLATE + note

# --- Agent definitions ---

research_orchestrator = LlmAgent(
    name="research_orchestrator",
    model=MODEL_GEMINI,
    instruction=_orchestrator_instruction,
    description="Plans research: reconnaissance, premise audit, and specialist brief assignment.",
    tools=[google_search, set_specialist_briefs, fetch_web_content],
    output_key="research_plan",
    generate_content_config=ORCHESTRATOR_THINKING_CONFIG,
    before_model_callback=_inject_geo_bias,
)

specialist_pool = ParallelAgent(
    name="specialist_pool",
    sub_agents=ALL_SPECIALISTS,
    description="Runs assigned specialists in parallel. Specialists without briefs skip instantly.",
)

# --- Pipeline ---

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_orchestrator, specialist_pool, make_gap_researcher(), _make_synthesizer()],
    description="Enriches context, plans research, runs specialists in parallel, then synthesizes findings.",
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
    plugins=[ChatLoggerPlugin()],
)
root_agent = _router
