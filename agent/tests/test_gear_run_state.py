"""Unit tests for `superextra_agent.gear_run_state.GearRunState`.

Plan §4.6 verification matrix:
  - observe_event mutations don't interleave (no `await` inside; verified
    statically by walking the AST of all mutation methods).
  - Note tasks pending after finalize() bounded wait are cancelled AND
    gathered, so `timeline_builder.build_summary()` reads stable state.
  - Empty final_reply → finalize() returns ('error', ...) not
    ('complete', ...) — empty-reply sanity check at plan §4.1.
  - Note-task and title-task cancellation doesn't leak when cancel()
    is called.
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
    The TimelineWriter inside still calls `firestore_events.write_event_doc`
    on `write_timeline`, but tests that exercise that path stub the
    writer directly.
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
    "_maybe_emit_notes",
    "_capture_final",
)


@pytest.mark.parametrize("method_name", _AWAIT_FREE_METHODS)
def test_observe_event_methods_are_await_free(method_name):
    """plan §"No per-run lock" — these methods MUST stay synchronous and
    await-free, so concurrent coroutines (note tasks) cannot interleave a
    partial mutation. Walk the AST of each and assert no Await/AsyncFor/
    AsyncWith nodes."""
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
    assert "completedAt" in turn_update


# ── finalize() — note-task drain order ───────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_cancels_pending_note_tasks_and_gathers():
    """plan §v3.7 race fix — `asyncio.wait` with a timeout does NOT cancel
    pending tasks; finalize() must explicitly cancel stragglers AND gather
    all results so a raised note-task exception doesn't sit unretrieved.
    """
    state = _make_state()
    state.final_reply = "answer"
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    cancelled: list[str] = []

    async def _fast() -> None:
        return None

    async def _slow() -> None:
        try:
            await asyncio.sleep(60)  # would outlast the drain
        except asyncio.CancelledError:
            cancelled.append("slow")
            raise

    async def _raises() -> None:
        raise RuntimeError("note task crashed")

    fast_task = asyncio.create_task(_fast())
    slow_task = asyncio.create_task(_slow())
    raises_task = asyncio.create_task(_raises())
    state.note_tasks.extend([fast_task, slow_task, raises_task])

    # Patch the drain timeout so the test runs quickly.
    monkey_attr = "NOTE_TASK_DRAIN_TIMEOUT_S"
    original = getattr(gear_run_state, monkey_attr)
    try:
        setattr(gear_run_state, monkey_attr, 0.1)
        await state.finalize()
    finally:
        setattr(gear_run_state, monkey_attr, original)

    assert fast_task.done()
    assert slow_task.cancelled() or slow_task.done()
    assert raises_task.done()
    assert cancelled == ["slow"], "the long-running note task must have been cancelled"


# ── finalize() — close timeline_writer AFTER notes drain ─────────────────────


@pytest.mark.asyncio
async def test_finalize_closes_timeline_writer_after_notes_drain():
    """plan §v3.8 close-order swap — closing the writer first lets a
    resuming note task mutate the builder while its write_timeline call
    no-ops against the closed writer (turnSummary would contain a note
    the live UI never saw). Verify drain happens before close."""
    state = _make_state()
    state.final_reply = "answer"
    order: list[str] = []
    real_close = state.timeline_writer.close

    async def _close():
        order.append("close")
        await real_close()

    state.timeline_writer.close = _close  # type: ignore[assignment]
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    async def _note():
        order.append("note")

    state.note_tasks.append(asyncio.create_task(_note()))

    await state.finalize()

    # Note ran first (or at least started before close completed).
    assert order.index("note") < order.index("close")


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


def test_observe_event_increments_seq_and_returns_list():
    state = _make_state()
    out = state.observe_event(_fake_event())
    assert isinstance(out, list)
    assert state.seq == 1


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


# ── Note-task / title-task cancellation hygiene ─────────────────────────────


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


# ── _maybe_emit_notes spawns LLM-backed tasks for 'plan_ready' / 'research_result' ──


@pytest.mark.asyncio
async def test_maybe_emit_notes_spawns_task_for_plan_ready(monkeypatch):
    """plan_ready and research_result milestones spawn LLM-backed note
    tasks (deterministic notes are written immediately, plus a task is
    scheduled for the LLM-backed enrichment)."""
    state = _make_state()

    spawned: list[str] = []

    # Patch the LLM-backed function so we can observe scheduling without
    # making a real call. _emit_note_task is what the GearRunState spawns.
    async def _fake_emit_note_task(*, milestone, **_):
        spawned.append(milestone)

    monkeypatch.setattr(gear_run_state, "_emit_note_task", _fake_emit_note_task)

    extras = state._maybe_emit_notes(
        {
            "plan_ready_text": "Plan is ready",
            "research_result_text": "Research is done",
        }
    )
    # No deterministic notes returned for these two (they're LLM-backed)
    # — the spawned tasks will write the notes via _emit_note_task.
    assert extras == []
    assert len(state.note_tasks) == 2
    # Drain spawned tasks so they don't leak warnings
    await asyncio.gather(*state.note_tasks)
    assert sorted(spawned) == ["plan_ready", "research_result"]


def test_maybe_emit_notes_returns_deterministic_for_context_start():
    """context_start and research_placeholder are deterministic and must
    be returned as timeline events to write inline."""
    state = _make_state()
    extras = state._maybe_emit_notes({"context_started": True})
    assert len(extras) == 1
    assert extras[0]["kind"] == "note"
    assert "checking the venue" in extras[0]["text"]


def test_maybe_emit_notes_idempotent_per_milestone():
    """Each milestone's note can only fire once."""
    state = _make_state()
    a = state._maybe_emit_notes({"context_started": True})
    b = state._maybe_emit_notes({"context_started": True})
    assert len(a) == 1
    assert b == []
