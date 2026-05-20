"""`EventCapturePlugin` — captures every ADK event into an in-memory list.

Used by the eval harness when wrapping specialists as `AgentTool`. Under
that pattern, each AgentTool call creates a child runner whose events stay
encapsulated; the parent runner's iterator no longer surfaces specialist
events. ADK propagates plugins from the parent runner to child runners
(`agent_tool.py:222-236`), so a plugin's `on_event_callback` *does* fire
for child events. This plugin exploits that to recover the per-specialist
event stream the eval scorer needs.

`before_run_callback` binds the local ADK session id as the fetch run id so eval
runs exercise the same per-run fetch cache scope as production.
"""

from __future__ import annotations

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.plugins.base_plugin import BasePlugin
from typing_extensions import override

from .web_tools import (
    clear_fetch_cache_for_run,
    set_fetch_run_id,
)


class EventCapturePlugin(BasePlugin):
    def __init__(self, *, name: str = "event_capture") -> None:
        super().__init__(name=name)
        self.events: list[Event] = []

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext):
        run_id = getattr(invocation_context.session, "id", None)
        if isinstance(run_id, str) and run_id:
            clear_fetch_cache_for_run(run_id)
            set_fetch_run_id(run_id)
        return None

    @override
    async def on_event_callback(
        self, *, invocation_context: InvocationContext, event: Event
    ):
        self.events.append(event)
        return None
