from types import SimpleNamespace

import pytest

from superextra_agent.event_capture_plugin import EventCapturePlugin
from superextra_agent.web_tools import clear_fetch_cache_for_run, read_discovered_sources


@pytest.mark.asyncio
async def test_event_capture_plugin_feeds_local_eval_source_reader(monkeypatch):
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

    async def read_pages(urls):
        return {
            "status": "success",
            "results": [{"status": "success", "url": urls[0]}],
            "sources": [{"url": urls[0], "title": "Source"}],
            "success_count": 1,
            "failed_count": 0,
        }

    monkeypatch.setattr("superextra_agent.web_tools._read_captured_pages", read_pages)

    try:
        await plugin.before_run_callback(invocation_context=invocation_context)
        await plugin.on_event_callback(invocation_context=invocation_context, event=event)

        result = await read_discovered_sources(
            [], tool_context=SimpleNamespace(agent_name="market_landscape")
        )
    finally:
        clear_fetch_cache_for_run(run_id)

    assert plugin.events == [event]
    assert result["status"] == "success"
    assert result["available_count"] == 1
    assert result["attempted_count"] == 1
    assert result["auto_appended_urls"] == [url]
    assert result["success_count"] == 1
