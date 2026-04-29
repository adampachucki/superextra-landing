"""`EventCapturePlugin` — captures every ADK event into an in-memory list.

Used by the eval harness when wrapping specialists as `AgentTool`. Under
that pattern, each AgentTool call creates a child runner whose events stay
encapsulated; the parent runner's iterator no longer surfaces specialist
events. ADK propagates plugins from the parent runner to child runners
(`agent_tool.py:222-236`), so a plugin's `on_event_callback` *does* fire
for child events. This plugin exploits that to recover the per-specialist
event stream the eval scorer needs.

Lifecycle callbacks (`before_run_callback`, `after_run_callback`) are
deliberately NOT overridden — they fire once per root invocation, and
under AgentTool each child invocation IS its own root from ADK's
perspective. We only care about events here; let the lifecycle hooks be
no-ops so the same plugin works under both Variant A and Variant B.
"""

from __future__ import annotations

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.plugins.base_plugin import BasePlugin
from typing_extensions import override


class EventCapturePlugin(BasePlugin):
    def __init__(self, *, name: str = "event_capture") -> None:
        super().__init__(name=name)
        self.events: list[Event] = []

    @override
    async def on_event_callback(
        self, *, invocation_context: InvocationContext, event: Event
    ):
        self.events.append(event)
        return None
