import base64
import logging
import re

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.apps import App
from google.adk.tools import google_search
from google.genai import Client, types

from .web_tools import fetch_web_content
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB

from .specialists import (
    MODEL_GEMINI, SPECIALIST_GEMINI, THINKING_CONFIG, ORCHESTRATOR_THINKING_CONFIG,
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

def _orchestrator_instruction(ctx):
    """Inject places_context into the orchestrator's instructions."""
    places_context = ctx.state.get("places_context", "No Google Places data available.")
    return _ORCHESTRATOR_TEMPLATE.format(places_context=places_context)

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


def _inject_code_execution(*, callback_context, llm_request):
    """Add code execution tool to the synthesizer's request.

    We inject the tool manually instead of using BuiltInCodeExecutor so that
    ADK's code execution post-processor doesn't strip inline_data images and
    save them to an artifact service.  This lets _embed_chart_images convert
    them to base64 data URIs that flow through as regular text.
    """
    llm_request.config = llm_request.config or types.GenerateContentConfig()
    llm_request.config.tools = llm_request.config.tools or []
    llm_request.config.tools.append(
        types.Tool(code_execution=types.ToolCodeExecution())
    )
    return None


def _embed_chart_images(*, callback_context, llm_response):
    """Convert inline_data image parts to base64 data URI markdown images.

    When the model places inline markdown references like
    ![alt](code_execution_image_N_...) in its text, replace those references
    with the actual base64 data URIs so charts render where the model intended.
    Fall back to appending standalone image parts when no references are found.
    """
    if not llm_response.content or not llm_response.content.parts:
        return llm_response

    # Collect base64 data URIs for each inline_data image, in order.
    images: list[str] = []
    for part in llm_response.content.parts:
        if (
            part.inline_data
            and part.inline_data.mime_type
            and part.inline_data.mime_type.startswith("image/")
        ):
            if len(part.inline_data.data) > MAX_IMAGE_BYTES:
                logger.warning(
                    "Skipping oversized chart image: %d bytes (limit %d)",
                    len(part.inline_data.data),
                    MAX_IMAGE_BYTES,
                )
                continue
            b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
            mime = part.inline_data.mime_type
            images.append(f"data:{mime};base64,{b64}")

    if not images:
        return llm_response

    # Try to replace code_execution_image references in text parts.
    # Pattern: ![alt text](code_execution_image_N_timestamp.ext)
    _IMG_REF = re.compile(r"!\[([^\]]*)\]\(code_execution_image_(\d+)_[^)]+\)")
    replaced = set()

    def _replace_ref(m):
        alt = m.group(1)
        idx = int(m.group(2)) - 1  # code_execution_image is 1-indexed
        if 0 <= idx < len(images):
            replaced.add(idx)
            return f"![{alt}]({images[idx]})"
        return m.group(0)

    new_parts = []
    for part in llm_response.content.parts:
        if part.text and _IMG_REF.search(part.text):
            new_parts.append(types.Part(text=_IMG_REF.sub(_replace_ref, part.text)))
        elif part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
            continue  # drop standalone inline_data — handled via text refs
        else:
            new_parts.append(part)

    # If some images weren't referenced in text, append them as fallback.
    for idx, uri in enumerate(images):
        if idx not in replaced:
            new_parts.append(types.Part(text=f"\n\n![Chart]({uri})\n\n"))

    llm_response.content.parts = new_parts
    return llm_response


def _make_synthesizer(name="synthesizer"):
    """Create a synthesizer instance."""
    return LlmAgent(
        name=name,
        model=MODEL_GEMINI,
        instruction=_synthesizer_instruction,
        description="Synthesizes findings from all specialist agents into a cohesive report.",
        output_key="final_report",
        generate_content_config=THINKING_CONFIG,
        before_model_callback=_inject_code_execution,
        after_model_callback=_embed_chart_images,
    )


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
