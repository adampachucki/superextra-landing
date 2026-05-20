from types import SimpleNamespace

import pytest

from superextra_agent.event_capture_plugin import EventCapturePlugin
from superextra_agent.web_tools import clear_fetch_cache_for_run, set_fetch_run_id


@pytest.mark.asyncio
async def test_event_capture_plugin_captures_child_events_and_binds_run(monkeypatch):
    run_id = "eval-session-1"
    url = "https://example.com/source"
    plugin = EventCapturePlugin()
    invocation_context = SimpleNamespace(session=SimpleNamespace(id=run_id))
    event = SimpleNamespace(
        author="market_landscape",
        grounding_metadata=SimpleNamespace(
            grounding_chunks=[
                SimpleNamespace(
                    web=SimpleNamespace(
                        uri=url,
                        title="Source",
                        domain="example.com",
                    )
                )
            ]
        ),
    )

    calls: list[str] = []

    def capture_run_id(value: str):
        calls.append(value)
        set_fetch_run_id(value)

    monkeypatch.setattr("superextra_agent.event_capture_plugin.set_fetch_run_id", capture_run_id)

    try:
        await plugin.before_run_callback(invocation_context=invocation_context)
        await plugin.on_event_callback(invocation_context=invocation_context, event=event)
    finally:
        clear_fetch_cache_for_run(run_id)

    assert plugin.events == [event]
    assert calls == [run_id]
