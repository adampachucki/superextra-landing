import os
from pathlib import Path

from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import google_search
from google.genai import Client, types

from .apify_tools import get_google_reviews
from .specialist_catalog import (
    ROLE_TITLES,
    SPECIALISTS,
)
from .tripadvisor_tools import find_tripadvisor_restaurant, get_tripadvisor_reviews
from .web_tools import fetch_web_content

_dir_override = os.environ.get("SUPEREXTRA_INSTRUCTIONS_DIR")
INSTRUCTIONS_DIR = Path(_dir_override) if _dir_override else Path(__file__).parent / "instructions"

_version = os.environ.get("GEMINI_VERSION", "3.1")

RETRY = types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=60.0)


class GeminiGlobalEndpoint(Gemini):
    """Gemini variant whose `api_client` is constructed lazily, routed via
    the global Vertex AI endpoint (`location='global'`).

    Eager construction (the previous `g.api_client = Client(...)` pattern)
    is unpicklable: the live Client carries a `_thread.lock` that
    cloudpickle can't serialise, blocking `agent_engines.create(...)`
    deploys. See adk-python#3628 and probe round R2.4 for the empirical
    trace. Lazy construction defers Client creation until first access on
    the deployed runtime, so pickle time never sees a live client.
    """

    @property
    def api_client(self) -> Client:  # type: ignore[override]
        client = self.__dict__.get("_lazy_global_client")
        if client is not None:
            return client
        client = Client(
            vertexai=True,
            location="global",
            http_options=types.HttpOptions(retry_options=RETRY),
        )
        self.__dict__["_lazy_global_client"] = client
        return client

    @api_client.setter
    def api_client(self, value: Any) -> None:
        self.__dict__["_lazy_global_client"] = value


def _make_gemini(model: str, *, force_global: bool = False) -> Gemini:
    """Create a Gemini instance.

    Routes via the global Vertex AI endpoint when the model family requires
    it (3.1 models) or when `force_global=True` (e.g. 2.5 Flash, which ADK
    would otherwise pin to the container's us-central1 region).

    ADK bakes `GOOGLE_CLOUD_LOCATION=us-central1` into the container
    (matching the Cloud Run region), but several model families don't serve
    from that location. The `GeminiGlobalEndpoint` subclass returns a
    lazily-built `Client` with `location='global'` so model calls hit
    `https://aiplatform.googleapis.com/` while the rest of ADK (sessions,
    Agent Engine) stays on us-central1.
    """
    if _version == "3.1" or force_global:
        return GeminiGlobalEndpoint(model=model, retry_options=RETRY)
    return Gemini(model=model, retry_options=RETRY)


if _version == "3.1":
    MODEL = "gemini-3.1-pro-preview"
    SPECIALIST_MODEL = "gemini-3.1-pro-preview-customtools"
    # `include_thoughts=True` surfaces Gemini's native thought summaries on
    # every Gemini call (parent + AgentTool children, since the plugin runs
    # inside child runners). Mapped to `kind: 'thought'` timeline rows in
    # `firestore_events.map_event` and rendered as markdown in LiveActivity.
    THINKING_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="HIGH", include_thoughts=True),
    )
    MEDIUM_THINKING_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="MEDIUM", include_thoughts=True),
    )
    ORCHESTRATOR_THINKING_CONFIG = THINKING_CONFIG
else:
    MODEL = "gemini-2.5-pro"
    SPECIALIST_MODEL = MODEL
    THINKING_CONFIG = None
    MEDIUM_THINKING_CONFIG = None
    ORCHESTRATOR_THINKING_CONFIG = None

MODEL_GEMINI = _make_gemini(MODEL)
SPECIALIST_GEMINI = _make_gemini(SPECIALIST_MODEL)


_SPECIALIST_BASE = (INSTRUCTIONS_DIR / "specialist_base.md").read_text()


def _make_instruction(name: str):
    """Create an InstructionProvider that injects shared state into the template.

    Specialist-specific briefs arrive as the AgentTool `request` user message,
    so the instruction provider only supplies durable context.
    """
    body = (INSTRUCTIONS_DIR / f"{name}.md").read_text()
    template = _SPECIALIST_BASE.replace("{specialist_body}", body).replace(
        "{role_title}", ROLE_TITLES.get(name, name)
    )

    def provider(ctx):
        places_context = ctx.state.get("places_context", "No Google Places data available.")
        # Exposed to specialists that need the deterministic target ID (currently
        # review_analyst.md, so TripAdvisor source pills resolve to the target
        # venue). Other specialist templates don't reference {target_place_id};
        # Python str.format silently ignores unused kwargs.
        target_place_id = ctx.state.get("_target_place_id", "")
        instruction = template.format(
            places_context=places_context,
            target_place_id=target_place_id,
        )
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


def _make_specialist(
    name,
    description,
    output_key=None,
    tools=None,
    instruction_name=None,
    thinking_config=None,
):
    """Create an AgentTool-compatible specialist.

    `include_contents='default'` is intentional: AgentTool passes the
    orchestrator's brief as the user message (`request`), while the instruction
    provider injects shared state such as Places context.
    """
    return LlmAgent(
        name=name,
        model=SPECIALIST_GEMINI,
        description=description,
        instruction=_make_instruction(instruction_name or name),
        tools=tools or [google_search, fetch_web_content],
        output_key=output_key,
        include_contents="default",
        generate_content_config=thinking_config if thinking_config is not None else THINKING_CONFIG,
        before_model_callback=_inject_geo_bias,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=_on_tool_error,
    )


# Thinking-level buckets: MEDIUM for pattern-matching / aggregation,
# HIGH for quantitative-inference / strategic work. Catalog entries carry
# `thinking="high" | "medium"`; we map to the actual config at build time.
_THINKING_CONFIGS = {"high": THINKING_CONFIG, "medium": MEDIUM_THINKING_CONFIG}

# Per-specialist tool overrides. Everything not listed here uses the default
# `[google_search, fetch_web_content]` pair.
_SPECIALIST_TOOLS: dict[str, list] = {
    "review_analyst": [find_tripadvisor_restaurant, get_tripadvisor_reviews, get_google_reviews],
}

ALL_SPECIALISTS = [
    _make_specialist(
        s.name,
        s.description,
        s.output_key,
        tools=_SPECIALIST_TOOLS.get(s.name),
        instruction_name=s.instruction_name,
        thinking_config=_THINKING_CONFIGS[s.thinking],
    )
    for s in SPECIALISTS
]

CONTINUATION_SPECIALISTS = [
    _make_specialist(
        s.name,
        s.description,
        None,
        tools=_SPECIALIST_TOOLS.get(s.name),
        instruction_name=s.instruction_name,
        thinking_config=_THINKING_CONFIGS[s.thinking],
    )
    for s in SPECIALISTS
]
