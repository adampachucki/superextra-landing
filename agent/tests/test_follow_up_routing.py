"""Continuation routing evals.

Tests that the router correctly routes:
- Simple continuations (after a report) → continue_research agent
- New research needs (after a report) → continue_research agent
- First messages (no report) → research_pipeline (unchanged)

Uses stub agents and InMemoryRunner. Each test costs 1-2 flash calls.

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

from superextra_agent.agent import _router_instruction

INSTRUCTIONS_DIR = (
    Path(__file__).resolve().parent.parent / "superextra_agent" / "instructions"
)

# Build router + stub agents only when live evals are actually requested.
# `Client(vertexai=True, ...)` calls google.auth.default() at construction
# time, which raises DefaultCredentialsError in CI (no ADC). Guarding here
# keeps module collection clean even when the skipif above would have
# skipped each test individually.
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

    _stub_continue_research = LlmAgent(
        name="continue_research",
        model=_flash,
        instruction="Reply with exactly: 'Continuation activated.' Nothing else.",
        description="Stub continuation agent for routing tests.",
        output_key="final_report",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    _test_router = LlmAgent(
        name="router",
        model=_flash,
        instruction=_router_instruction,
        description="Routes user questions to research, continuation, or asks for clarification.",
        sub_agents=[_stub_pipeline, _stub_continue_research],
        output_key="router_response",
    )


async def _run_conversation(messages: list[str], pre_state: dict | None = None) -> list[dict]:
    """Send messages through the test router, return routing results per turn."""
    runner = InMemoryRunner(agent=_test_router, app_name="eval")
    session = await runner.session_service.create_session(
        app_name="eval",
        user_id="eval_user",
        state=dict(pre_state) if pre_state else None,
    )

    results = []
    for message in messages:
        transferred_to = None
        response_text = ""

        async for event in runner.run_async(
            user_id="eval_user",
            session_id=session.id,
            new_message=types.Content(
                parts=[types.Part(text=message)],
                role="user",
            ),
        ):
            if event.actions.transfer_to_agent:
                transferred_to = event.actions.transfer_to_agent
            if event.author == "router" and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_text += part.text

        results.append({
            "transferred_to": transferred_to,
            "response": response_text,
        })

    return results


# State simulating a completed research session
REPORT_STATE = {
    "final_report": (
        "## Market Analysis\n\n"
        "Key findings about Restaurant XYZ...\n\n"
        "Pricing is competitive at PLN 35-45 range."
    ),
    "places_context": "Target: Restaurant XYZ, Warsaw. Competitors: A, B, C.",
}


# --- Simple follow-ups → should route to continue_research ---

SHOULD_FOLLOW_UP = [
    pytest.param("Summarize that in bullet points", id="reformat_request"),
    pytest.param("What did you find about pricing?", id="drill_into_existing"),
    pytest.param("Can you compare restaurants A and B from the report?", id="compare_from_report"),
    pytest.param("Can you check if Restaurant XYZ still lists brunch?", id="narrow_current_fill_in"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", SHOULD_FOLLOW_UP)
async def test_simple_followup_routes_to_continue_research(message):
    """After a report is delivered, simple follow-ups go to the continuation agent."""
    results = await _run_conversation([message], pre_state=REPORT_STATE)
    assert results[0]["transferred_to"] == "continue_research", (
        f"Expected transfer to continue_research but got: {results[0]['transferred_to']} "
        f"(response: {results[0]['response'][:200]})"
    )


# --- New research needs after a report should stay in continuation ---

SHOULD_RESEARCH = [
    pytest.param("What about the delivery market in this area?", id="new_topic_not_covered"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", SHOULD_RESEARCH)
async def test_new_research_routes_to_continue_research(message):
    """After a report, new data requests stay in continuation.

    The continuation agent decides whether to answer with focused research or
    suggest a new session; the router should not jam a full pipeline into the
    old thread.
    """
    results = await _run_conversation([message], pre_state=REPORT_STATE)
    assert results[0]["transferred_to"] == "continue_research", (
        f"Expected transfer to continue_research but got: {results[0]['transferred_to']} "
        f"(response: {results[0]['response'][:200]})"
    )


# --- New target after a report should stay in continuation ---


@pytest.mark.asyncio
async def test_new_restaurant_after_report_routes_to_continue_research():
    """After a report, the continuation agent owns new-session suggestions."""
    results = await _run_conversation(
        ["Now analyze Restaurant D in Manchester"], pre_state=REPORT_STATE
    )
    assert results[0]["transferred_to"] == "continue_research", (
        f"Expected continuation but got: {results[0]['transferred_to']} "
        f"(response: {results[0]['response'][:200]})"
    )


# --- No prior report → should route to research_pipeline ---

@pytest.mark.asyncio
async def test_first_message_routes_to_pipeline():
    """Without prior report, actionable questions go to research_pipeline."""
    results = await _run_conversation(
        ["[Context: place_id=abc, name=Pizzeria Roma, address=Via Roma 1] How's competition?"],
    )
    assert results[0]["transferred_to"] == "research_pipeline", (
        f"Expected transfer to research_pipeline but got: {results[0]['transferred_to']} "
        f"(response: {results[0]['response'][:200]})"
    )


# --- No prior report, vague → should clarify ---

@pytest.mark.asyncio
async def test_vague_still_clarifies():
    """Without prior report, vague messages still get clarification."""
    results = await _run_conversation(["How's my competition?"])
    assert results[0]["transferred_to"] is None, (
        f"Expected no transfer (clarification) but got: {results[0]['transferred_to']}"
    )
    assert results[0]["response"], "Router should ask a clarifying question"
