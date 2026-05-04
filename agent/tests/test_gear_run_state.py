"""Unit tests for `superextra_agent.gear_run_state.GearRunState`.

Plan §4.6 verification matrix:
  - observe_event mutations don't interleave (no `await` inside; verified
    statically by walking the AST of all mutation methods).
  - Empty final_reply → finalize() returns ('error', ...) not
    ('complete', ...) — empty-reply sanity check at plan §4.1.
  - Title-task cancellation doesn't leak when cancel() is called.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from superextra_agent import gear_run_state, notes
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
    return SimpleNamespace(
        content=content,
        actions=actions,
        author="model",
        grounding_metadata=None,
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
    """plan §4.1 step 4 + worker_main.py:1292 — a whitespace-only or
    missing final_reply must produce the error terminal payload."""
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

    session_update, turn_update, status = await state.finalize()
    assert status == "complete"
    assert session_update["status"] == "complete"
    assert turn_update["status"] == "complete"
    assert turn_update["reply"] == state.final_reply
    assert turn_update["sources"] == state.final_sources
    assert "turnSummary" in turn_update
    assert "notes" not in turn_update["turnSummary"]
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


def test_capture_final_dedupes_specialist_and_mapper_sources():
    state = _make_state()
    state.specialist_sources = [
        {"url": "https://a", "title": "A"},
        {"url": "https://b", "title": "B"},
    ]
    state.specialist_sources_seen = {"https://a", "https://b"}
    state._capture_final(
        {
            "reply": "answer",
            "sources": [
                {"url": "https://a", "title": "A (mapper)"},  # dup
                {"url": "https://c", "title": "C"},  # new
            ],
        }
    )
    urls = [s["url"] for s in state.final_sources]
    assert urls == ["https://a", "https://c", "https://b"]
    # Mapper-side title wins (first-seen, since mapper sources come first
    # in the dedup loop).
    titles = {s["url"]: s["title"] for s in state.final_sources}
    assert titles["https://a"] == "A (mapper)"


def test_observe_event_returns_timeline_list():
    state = _make_state()
    out = state.observe_event(_fake_event())
    assert isinstance(out, list)


@pytest.mark.asyncio
async def test_observe_typed_pill_dedupes_detail_rows():
    state = _make_state()
    state.timeline_writer.write_timeline = AsyncMock(return_value={"ok": True})
    pill = {
        "kind": "detail",
        "id": "a",
        "group": "search",
        "family": "Searching the web",
        "text": "pizza",
    }

    first = await state.observe_typed_pill(pill)
    second = await state.observe_typed_pill({**pill, "id": "b"})

    assert first == {"ok": True}
    assert second is None
    state.timeline_writer.write_timeline.assert_awaited_once_with(pill)


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


# ── Title-task cancellation hygiene ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_handles_failing_title_task():
    """Title task that raises must not break finalize()."""
    state = _make_state()
    state.final_reply = "answer"
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    async def _title_raises() -> str:
        raise RuntimeError("title gen crashed")

    state.title_task = asyncio.create_task(_title_raises())

    session_update, _t, status = await state.finalize()
    assert status == "complete"
    # No title key when generation failed.
    assert "title" not in session_update


@pytest.mark.asyncio
async def test_finalize_uses_returned_title():
    state = _make_state()
    state.final_reply = "answer"
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    async def _title() -> str:
        return "Short Title"

    state.title_task = asyncio.create_task(_title())
    session_update, _t, status = await state.finalize()
    assert status == "complete"
    assert session_update.get("title") == "Short Title"


@pytest.mark.asyncio
async def test_finalize_propagates_cancellation():
    """plan §Commit-3 + F2 P3 — the title-task except clause was tightened
    from `(TimeoutError, CancelledError, Exception)` to
    `(TimeoutError, Exception)`. `Exception` does NOT subclass
    `CancelledError`, so cancellation now propagates out of finalize()
    rather than being swallowed by the title-task wrapper.

    Recipe (F2's simpler form): cancel the title_task directly and
    assert finalize() re-raises CancelledError. No timing-sensitive
    outer-task race.
    """
    state = _make_state()
    state.final_reply = "answer"
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    async def _hangs():
        await asyncio.sleep(60)

    title_task = asyncio.create_task(_hangs())
    state.title_task = title_task
    title_task.cancel()  # force CancelledError when finalize awaits it

    with pytest.raises(asyncio.CancelledError):
        await state.finalize()
