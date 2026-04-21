"""Follow-up routing evals.

Tests that the router correctly routes:
- Simple follow-ups (after a report) → follow_up agent
- New research needs (after a report) → research_pipeline
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
    instruction=_router_instruction,
    description="Routes user questions to research, follow-up, or asks for clarification.",
    sub_agents=[_stub_pipeline, _stub_follow_up],
    output_key="router_response",
)


async def _run_conversation(messages: list[str], pre_state: dict | None = None) -> list[dict]:
    """Send messages through the test router, return routing results per turn."""
    runner = InMemoryRunner(agent=_test_router, app_name="eval")
    session = await runner.session_service.create_session(
        app_name="eval", user_id="eval_user",
    )

    # Pre-populate state to simulate prior research
    if pre_state:
        session.state.update(pre_state)

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
    "final_report": "## Market Analysis\n\nKey findings about Restaurant XYZ...\n\nPricing is competitive at PLN 35-45 range.",
    "places_context": "Target: Restaurant XYZ, Warsaw. Competitors: A, B, C.",
    "research_plan": "Core question: competitive positioning of Restaurant XYZ.",
}


# --- Simple follow-ups → should route to follow_up ---

SHOULD_FOLLOW_UP = [
    pytest.param("Summarize that in bullet points", id="reformat_request"),
    pytest.param("What did you find about pricing?", id="drill_into_existing"),
    pytest.param("Can you compare restaurants A and B from the report?", id="compare_from_report"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", SHOULD_FOLLOW_UP)
async def test_simple_followup_routes_to_follow_up(message):
    """After a report is delivered, simple follow-ups go to follow_up agent."""
    results = await _run_conversation([message], pre_state=REPORT_STATE)
    assert results[0]["transferred_to"] == "follow_up", (
        f"Expected transfer to follow_up but got: {results[0]['transferred_to']} "
        f"(response: {results[0]['response'][:200]})"
    )


# --- New research needs → should still route to research_pipeline ---

SHOULD_RESEARCH = [
    pytest.param("Now analyze Restaurant D in Krakow", id="new_restaurant"),
    pytest.param("What about the delivery market in this area?", id="new_topic_not_covered"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", SHOULD_RESEARCH)
async def test_new_research_routes_to_pipeline(message):
    """After a report, follow-ups needing new data go to research_pipeline."""
    results = await _run_conversation([message], pre_state=REPORT_STATE)
    assert results[0]["transferred_to"] == "research_pipeline", (
        f"Expected transfer to research_pipeline but got: {results[0]['transferred_to']} "
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
