from types import SimpleNamespace

import pytest

from superextra_agent.event_capture_plugin import EventCapturePlugin


@pytest.mark.asyncio
async def test_event_capture_plugin_captures_events():
    plugin = EventCapturePlugin()
    invocation_context = SimpleNamespace(session=SimpleNamespace(id="eval-session-1"))
    event = SimpleNamespace(author="market_landscape")

    await plugin.on_event_callback(invocation_context=invocation_context, event=event)

    assert plugin.events == [event]
