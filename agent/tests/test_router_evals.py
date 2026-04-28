"""Router routing evals.

Tests that the router correctly transfers to research_pipeline for
research-ready messages and asks for clarification when context is missing.

Uses a stub pipeline to avoid running the real research pipeline (which
makes 5-10+ Gemini Pro calls per test case). Each test case here costs
one gemini-2.5-flash call for the router + one trivial flash call for the
stub — fast and cheap.

These tests make live Gemini API calls. Skipped by default — opt in via
`RUN_LIVE_EVALS=1` (or just run `npm run test:evals`).

Requires: gcloud auth application-default credentials for Vertex AI.
"""

import os

os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test-key")
os.environ.setdefault("GEMINI_VERSION", "3.1")

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_EVALS"),
    reason="Live Gemini eval — set RUN_LIVE_EVALS=1 or run `npm run test:evals`",
)
from pathlib import Path
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import Client, types

INSTRUCTIONS_DIR = (
    Path(__file__).resolve().parent.parent / "superextra_agent" / "instructions"
)

# --- Test router setup (stub pipeline avoids running real research) ---
#
# Built lazily — `Client(vertexai=True, ...)` calls google.auth.default()
# at construction time, which raises DefaultCredentialsError in CI (no ADC).
# Module-level eager init would break collection even though skipif would
# have skipped the tests themselves.

_test_router = None
if os.environ.get("RUN_LIVE_EVALS"):
    _RETRY = types.HttpRetryOptions(attempts=3, initial_delay=1.0, max_delay=30.0)

    _flash = Gemini(model="gemini-2.5-flash", retry_options=_RETRY)
    _flash.api_client = Client(
        vertexai=True,
        location="global",
        http_options=types.HttpOptions(retry_options=_RETRY),
    )

    _stub_pipeline = LlmAgent(
        name="research_pipeline",
        model=_flash,
        instruction="Reply with exactly: 'Pipeline activated.' Nothing else.",
        description="Stub pipeline for routing tests.",
        output_key="final_report",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    # The production router also routes to `follow_up` when a prior report
    # exists. This suite runs only first-turn prompts, so the model
    # shouldn't transfer there — but a mis-route without this stub would
    # raise "agent not found" and mask the real assertion failure.
    _stub_follow_up = LlmAgent(
        name="follow_up",
        model=_flash,
        instruction="Reply with exactly: 'Follow-up activated.' Nothing else.",
        description="Stub follow-up agent for routing tests.",
        output_key="final_report",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    _test_router = LlmAgent(
        name="router",
        model=_flash,
        instruction=(INSTRUCTIONS_DIR / "router.md").read_text(),
        description="Routes user questions to research, follow-up, or asks for clarification.",
        sub_agents=[_stub_pipeline, _stub_follow_up],
        output_key="router_response",
    )


async def _check_routing(message: str) -> dict:
    """Send a message through the test router, return whether it transferred."""
    runner = InMemoryRunner(agent=_test_router, app_name="eval")
    session = await runner.session_service.create_session(
        app_name="eval", user_id="eval_user",
    )

    transferred = False
    router_text = ""

    async for event in runner.run_async(
        user_id="eval_user",
        session_id=session.id,
        new_message=types.Content(
            parts=[types.Part(text=message)],
            role="user",
        ),
    ):
        if event.actions.transfer_to_agent == "research_pipeline":
            transferred = True
        if event.author == "router" and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    router_text += part.text

    return {"transferred": transferred, "response": router_text}


# --- Should route to research_pipeline ---

SHOULD_ROUTE = [
    pytest.param(
        "[Context: place_id=ChIJ123, name=Test Restaurant, address=123 Main St, Warsaw] "
        "[Date: 2026-04-01] How does this restaurant compare to nearby competition?",
        id="context_prefix_with_question",
    ),
    pytest.param(
        "[Context: place_id=abc, name=Pizzeria Roma, address=Via Roma 1, Milan] "
        "What are their peak hours?",
        id="context_prefix_simple",
    ),
    pytest.param(
        "What are the current dining trends in Warsaw?",
        id="industry_trends_city",
    ),
    pytest.param(
        "How saturated is the ramen market in Brooklyn?",
        id="market_saturation_neighborhood",
    ),
    pytest.param(
        "What's the competitive landscape for fine dining in Manhattan?",
        id="competitive_landscape_area",
    ),
]

# --- Should ask for clarification ---

SHOULD_CLARIFY = [
    pytest.param(
        "How's my competition doing?",
        id="vague_competition",
    ),
    pytest.param(
        "Compare the competition",
        id="no_location_no_context",
    ),
    pytest.param(
        "What are chef salaries?",
        id="salary_needs_location",
    ),
    pytest.param(
        "What should I price my menu at?",
        id="pricing_needs_specifics",
    ),
    pytest.param(
        "How profitable is my restaurant?",
        id="needs_specific_restaurant",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", SHOULD_ROUTE)
async def test_routes_to_pipeline(message):
    """Router should transfer to research_pipeline for research-ready messages."""
    result = await _check_routing(message)
    assert result["transferred"], (
        f"Expected transfer but router responded: {result['response'][:200]}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("message", SHOULD_CLARIFY)
async def test_asks_for_clarification(message):
    """Router should ask for clarification when message lacks context."""
    result = await _check_routing(message)
    assert not result["transferred"], (
        "Expected clarification question but router transferred to research_pipeline"
    )
    assert result["response"], "Router should provide a clarifying response"
