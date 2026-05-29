"""Unit tests for `superextra_agent.gear_run_state.GearRunState`.

Plan §4.6 verification matrix:
  - observe_event mutations don't interleave (no `await` inside; verified
    statically by walking the AST of all mutation methods).
  - Empty final_reply → finalize() returns ('error', ...) not
    ('complete', ...) — empty-reply sanity check at plan §4.1.
  - finalize() never sets title — the title write lives in the
    plugin-owned fire-and-forget wrapper, not the terminal payload.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from superextra_agent import gear_run_state
from superextra_agent.gear_run_state import GearRunState


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> GearRunState:
    """Build a GearRunState wired against a mocked Firestore client.
    Tests that exercise Firestore writes stub the TimelineWriter directly.
    """
    fs = MagicMock(name="fs")
    defaults = dict(
        sid="sid-test",
        invocation_id="inv-test",
        run_id="run-test",
        turn_idx=1,
        user_id="user-test",
        query_text="What about reviews?",
        fs=fs,
    )
    defaults.update(overrides)
    return GearRunState(**defaults)


def _fake_event(
    *,
    function_calls: list[tuple[str, dict]] | None = None,
    function_responses: list[tuple[str, dict]] | None = None,
    state_delta: dict | None = None,
    text: str | None = None,
    grounding_chunks: list[dict] | None = None,
    author: str = "model",
    partial: bool = False,
):
    """Compose a minimal stand-in for an ADK Event that the timeline +
    map_event helpers can read."""
    parts = []
    for name, args in function_calls or []:
        parts.append(
            SimpleNamespace(
                function_call=SimpleNamespace(name=name, args=args),
                function_response=None,
                text=None,
            )
        )
    for name, response in function_responses or []:
        parts.append(
            SimpleNamespace(
                function_call=None,
                function_response=SimpleNamespace(name=name, response=response),
                text=None,
            )
        )
    if text is not None:
        parts.append(SimpleNamespace(function_call=None, function_response=None, text=text))
    content = SimpleNamespace(parts=parts) if parts else None
    actions = SimpleNamespace(state_delta=state_delta or {}) if state_delta is not None else SimpleNamespace(state_delta={})
    grounding_metadata = None
    if grounding_chunks is not None:
        grounding_metadata = SimpleNamespace(
            grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(**chunk)) for chunk in grounding_chunks
            ]
        )
    return SimpleNamespace(
        content=content,
        actions=actions,
        author=author,
        partial=partial,
        grounding_metadata=grounding_metadata,
        is_final_response=lambda: False,
    )


# ── Mutation discipline: observe_event has no `await` ────────────────────────


_AWAIT_FREE_METHODS = (
    "observe_event",
    "_merge_source",
    "_capture_final",
)


@pytest.mark.parametrize("method_name", _AWAIT_FREE_METHODS)
def test_observe_event_methods_are_await_free(method_name):
    """These methods must stay synchronous and await-free. Walk the AST of
    each and assert no Await/AsyncFor/AsyncWith nodes."""
    method = getattr(GearRunState, method_name)
    src = inspect.getsource(method)
    tree = ast.parse(src.lstrip())  # lstrip() handles indented def
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
            bad.append(type(node).__name__)
    assert not bad, (
        f"GearRunState.{method_name} must stay synchronous; "
        f"found {bad} — see plan §'No per-run lock' for why."
    )


# ── finalize() — empty-reply sanity check ────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_empty_reply_returns_error_payload():
    """A whitespace-only or missing final_reply produces the error terminal payload."""
    state = _make_state()
    state.final_reply = ""  # empty
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    session_update, turn_update, status = await state.finalize()
    assert status == "error"
    assert session_update["status"] == "error"
    assert session_update["error"] == "empty_or_malformed_reply"
    assert turn_update["status"] == "error"
    assert turn_update["error"] == "empty_or_malformed_reply"


@pytest.mark.asyncio
async def test_finalize_whitespace_only_reply_is_error():
    state = _make_state()
    state.final_reply = "   \n  \t  "
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    _s, _t, status = await state.finalize()
    assert status == "error"


@pytest.mark.asyncio
async def test_finalize_real_reply_returns_complete_payload():
    state = _make_state()
    state.final_reply = "Here's the answer: ..."
    state.final_sources = [{"url": "https://example.com", "title": "Example"}]
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)
    await state.observe_typed_pill(
        {
            "kind": "thought",
            "id": "thought-1",
            "author": "review_analyst",
            "text": "Reading reviews",
        }
    )

    session_update, turn_update, status = await state.finalize()
    assert status == "complete"
    assert session_update["status"] == "complete"
    assert turn_update["status"] == "complete"
    assert turn_update["reply"] == state.final_reply
    assert turn_update["sources"] == state.final_sources
    assert "turnSummary" in turn_update
    assert "notes" not in turn_update["turnSummary"]
    assert "diagnostics" not in turn_update["turnSummary"]
    assert "completedAt" in turn_update


# ── stop_heartbeat ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_heartbeat_cancels_running_task():
    state = _make_state()

    async def _hb():
        await asyncio.sleep(60)

    state.heartbeat_task = asyncio.create_task(_hb())
    await state.stop_heartbeat()
    assert state.heartbeat_task.cancelled() or state.heartbeat_task.done()


@pytest.mark.asyncio
async def test_stop_heartbeat_noop_if_none():
    state = _make_state()
    state.heartbeat_task = None
    await state.stop_heartbeat()  # must not raise


@pytest.mark.asyncio
async def test_stop_heartbeat_handles_already_finished():
    state = _make_state()

    async def _done():
        return None

    state.heartbeat_task = asyncio.create_task(_done())
    await asyncio.sleep(0)  # let it complete
    await state.stop_heartbeat()  # must not raise


# ── observe_event / _capture_final ───────────────────────────────────────────


def test_capture_final_snapshots_accumulated_sources():
    state = _make_state()
    state.specialist_sources = [
        {"url": "https://a", "title": "A"},
        {"url": "https://b", "title": "B"},
    ]
    state.specialist_sources_seen = {"https://a", "https://b"}
    state._capture_final({"reply": "answer"})

    urls = [s["url"] for s in state.final_sources]
    assert urls == ["https://a", "https://b"]
    titles = {s["url"]: s["title"] for s in state.final_sources}
    assert titles["https://a"] == "A"


def test_observe_event_returns_timeline_list():
    state = _make_state()
    out = state.observe_event(_fake_event())
    assert isinstance(out, list)


def test_observe_event_drains_tool_source_state_delta():
    state = _make_state()
    source = {
        "provider": "google_maps",
        "place_id": "ChIJtarget",
        "url": "https://maps.google.com/?cid=target",
        "title": "Google Maps - Target",
    }

    state.observe_event(_fake_event(state_delta={"_tool_src_google_maps_abc": source}))

    assert state.specialist_sources == [source]


def test_observe_event_merges_grounding_sources_into_drawer_candidates():
    state = _make_state()
    source = {
        "uri": "https://example.com/grounded",
        "title": "Grounded",
        "domain": "example.com",
    }
    drawer_source = {
        "url": "https://example.com/grounded",
        "title": "Grounded",
        "domain": "example.com",
    }

    state.observe_event(
        _fake_event(
            state_delta={"market_result": "Result"},
            text="Result",
            grounding_chunks=[source],
            author="market_landscape",
        )
    )
    state._capture_final({"reply": "answer"})

    assert state.final_sources == [{**drawer_source, "provider": "grounding"}]


def test_partial_source_events_merge_once():
    state = _make_state()
    source = {"uri": "https://example.com/grounded", "title": "Grounded"}

    state.observe_event(_fake_event(grounding_chunks=[source], partial=True))
    state.observe_event(_fake_event(grounding_chunks=[source], partial=False))

    assert state.specialist_sources == [
        {
            "url": "https://example.com/grounded",
            "title": "Grounded",
            "provider": "grounding",
        }
    ]


def test_partial_source_event_is_not_lost_if_no_aggregate_repeats_it():
    state = _make_state()
    source = {"uri": "https://example.com/grounded", "title": "Grounded"}

    state.observe_event(_fake_event(grounding_chunks=[source], partial=True))
    state._capture_final({"reply": "answer"})

    assert state.final_sources == [
        {
            "url": "https://example.com/grounded",
            "title": "Grounded",
            "provider": "grounding",
        }
    ]


def test_source_dedupe_keeps_same_url_for_distinct_provider_or_place():
    state = _make_state()
    url = "https://www.google.com/maps/place/?q=place_id:ChIJtarget"

    state._merge_source({
        "provider": "google_maps",
        "place_id": "ChIJtarget",
        "url": url,
        "title": "Google Maps - Target",
    })
    state._merge_source({
        "provider": "google_reviews",
        "place_id": "ChIJtarget",
        "url": url,
        "title": "Google Reviews - Target",
    })
    state._merge_source({
        "provider": "google_reviews",
        "place_id": "ChIJtarget",
        "url": url,
        "title": "Google Reviews - Target duplicate",
    })

    assert [s["provider"] for s in state.specialist_sources] == [
        "google_maps",
        "google_reviews",
    ]


def test_source_dedupe_collapses_same_url_sources_by_url():
    state = _make_state()

    state._merge_source({
        "url": "https://example.com/article",
        "title": "Search result title",
        "domain": "example.com",
    })
    state._merge_source({
        "url": "https://example.com/article",
        "title": "Fetched page title",
        "domain": "example.com",
    })

    assert state.specialist_sources == [
        {
            "url": "https://example.com/article",
            "title": "Search result title",
            "domain": "example.com",
        }
    ]


@pytest.mark.asyncio
async def test_finalize_resolves_and_dedupes_grounding_redirect_sources(monkeypatch):
    state = _make_state()
    state.final_reply = "answer"
    redirect_a = {
        "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
        "title": "trojmiasto.pl",
        "domain": "trojmiasto.pl",
        "provider": "grounding",
    }
    redirect_b = {
        "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/b",
        "title": "Duplicate article",
        "domain": "trojmiasto.pl",
        "provider": "grounding",
    }
    other = {"url": "https://example.com/other", "title": "Other"}
    state.final_sources = [redirect_a, redirect_b, other]

    async def resolve(url):
        if url in {redirect_a["url"], redirect_b["url"]}:
            return "https://www.trojmiasto.pl/article"
        return url

    monkeypatch.setattr(gear_run_state, "resolve_source_display_url", resolve)

    _session_update, turn_update, status = await state.finalize()

    assert status == "complete"
    assert turn_update["sources"] == [
        {**redirect_a, "url": "https://www.trojmiasto.pl/article"},
        other,
    ]
    assert "diagnostics" not in turn_update["turnSummary"]


def test_capture_final_preserves_place_scoped_sources_with_same_url():
    state = _make_state()
    url = "https://www.google.com/maps/place/?q=place_id:ChIJtarget"
    state.specialist_sources = [
        {
            "provider": "google_maps",
            "place_id": "ChIJtarget",
            "url": url,
            "title": "Google Maps - Target",
        },
        {
            "provider": "google_reviews",
            "place_id": "ChIJtarget",
            "url": url,
            "title": "Google Reviews - Target",
        },
    ]

    state._capture_final({"reply": "answer"})

    assert [s["provider"] for s in state.final_sources] == [
        "google_maps",
        "google_reviews",
    ]


@pytest.mark.asyncio
async def test_observe_typed_pill_dedupes_by_id():
    """Dedupe keys on `id`: a repeat of the same id is dropped, but two rows
    that share group/family/text yet carry distinct ids both write — distinct
    tool calls (e.g. searching two named restaurants) must not collapse."""
    state = _make_state()
    state.timeline_writer.write_timeline = AsyncMock(return_value={"ok": True})
    pill = {
        "kind": "detail",
        "id": "a",
        "group": "platform",
        "family": "Google Maps",
        "text": "1 place matches",
    }

    first = await state.observe_typed_pill(pill)
    # Same identity re-emitted → dropped.
    repeat = await state.observe_typed_pill({**pill})
    # Different call (different id), identical label → still written.
    distinct = await state.observe_typed_pill({**pill, "id": "b"})

    assert first == {"ok": True}
    assert repeat is None
    assert distinct == {"ok": True}
    assert state.timeline_writer.write_timeline.await_count == 2


def test_observe_event_capture_final_short_circuits_after_first():
    state = _make_state()
    # Synthesize an event whose mapper produces a `complete` block — easier
    # to drive via _capture_final directly since map_event behavior is
    # exercised by firestore_events tests.
    state._capture_final({"reply": "first"})
    state._capture_final({"reply": "second"})  # observe_event guards this case
    # The guard is `if mapped.get("complete") and self.final_reply is None:`
    # in observe_event itself. _capture_final has no guard. We test the
    # observe_event path by direct call:
    fake_state = _make_state()
    fake_state.final_reply = "already-set"
    out = fake_state.observe_event(_fake_event())
    assert fake_state.final_reply == "already-set"
    assert isinstance(out, list)


# ── Title — finalize() never touches title (the wrapper owns the write) ──────


@pytest.mark.asyncio
async def test_finalize_does_not_set_title():
    """Regression guard: title is owned by the fire-and-forget wrapper
    spawned in `FirestoreProgressPlugin.before_run_callback`, not by
    finalize. A future change that resurrects 'set title in the terminal
    payload' would re-introduce the old 'title only appears at the end'
    behavior."""
    state = _make_state()
    state.final_reply = "answer"
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    session_update, _t, status = await state.finalize()
    assert status == "complete"
    assert "title" not in session_update
