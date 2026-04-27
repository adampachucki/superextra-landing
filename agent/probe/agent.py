"""Probe agents — two flavours, deployed as two separate AdkApps.

`lifecycle_app` uses a deterministic BaseAgent that yields events on a
timer (no LLM, no tools) so lifecycle gate outcomes can't be confounded
by model behaviour.

`event_shape_app` uses a real LlmAgent + tool so we exercise the actual
ADK event taxonomy plugins will see in production.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps import App
from google.adk.events.event import Event
from google.genai import types

from .probe_plugin import ProbePlugin

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")


class DeterministicSlowAgent(BaseAgent):
    """Yields N events spaced by sleep_seconds. No LLM, no tools, no
    decisions. Total runtime = num_events * sleep_seconds.

    Used for the lifecycle gate (Test 1) so probe outcomes can't be
    confounded by LLM behaviour.
    """

    num_events: int = 5
    sleep_seconds: int = 60

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        for i in range(self.num_events):
            await asyncio.sleep(self.sleep_seconds)
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"step_{i}_done")],
                ),
            )


def echo_tool(message: str) -> dict:
    """Echo tool used by event-shape agent — exercises function_call /
    function_response event shapes that the production
    FirestoreProgressPlugin will need to handle."""
    return {"echoed": message, "ok": True}


# Lifecycle root: 5 events × 60s = 5 min run. Tunable via num_events at
# deploy time if Test 1 needs longer runs to exercise caller-disconnect.
lifecycle_root = DeterministicSlowAgent(name="probe_lifecycle")

# Event-shape root: real LLM + one tool call.
event_shape_root = LlmAgent(
    name="probe_event_shape",
    model="gemini-2.5-flash",
    instruction=(
        "Call echo_tool exactly once with message='hello'. "
        "After the tool returns, reply with the single word 'done'."
    ),
    tools=[echo_tool],
)


def make_lifecycle_app() -> App:
    return App(
        name="superextra_probe_lifecycle",
        root_agent=lifecycle_root,
        plugins=[ProbePlugin(project=PROJECT)],
    )


def make_event_shape_app() -> App:
    return App(
        name="superextra_probe_event_shape",
        root_agent=event_shape_root,
        plugins=[ProbePlugin(project=PROJECT)],
    )
