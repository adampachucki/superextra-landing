"""Unit tests for `superextra_agent.firestore_progress` (plan §4.6).

Covers:
  - `_claim_logic` predicates: currentRunId match, session status='queued',
    turn status='pending'. Mismatch → OwnershipLost.
  - `_fenced_logic` predicates: currentRunId match, session status='running'.
    Mismatch on either → OwnershipLost. Skipping turn update when no
    turn_ref is the heartbeat / lastEventAt path.
  - `_retry_critical` retries transient errors, never retries OwnershipLost,
    surfaces final exception after max_attempts.
  - `_heartbeat_loop` exits cleanly on OwnershipLost; logs+continues on
    transient blip.
  - `FirestoreProgressPlugin` lifecycle: per-invocation isolation,
    halt-content path on bad state, after_run cancels heartbeat BEFORE
    terminal write.
  - `_halt_content` returns `types.Content` (not Event) so ADK's early-exit
    check at runners.py:819 fires.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.api_core.exceptions import DeadlineExceeded, GoogleAPICallError
from google.genai import types

from superextra_agent import firestore_progress
from superextra_agent.firestore_progress import (
    FirestoreProgressPlugin,
    OwnershipLost,
    _claim_logic,
    _fenced_logic,
    _halt_content,
    _heartbeat_loop,
    _retry_critical,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_session_ref(doc_data: dict | None):
    ref = MagicMock(name="session_ref")
    snap = MagicMock(name="session_snap")
    snap.exists = doc_data is not None
    snap.to_dict.return_value = doc_data or {}
    ref.get.return_value = snap
    return ref


def _mock_turn_ref(doc_data: dict | None):
    ref = MagicMock(name="turn_ref")
    snap = MagicMock(name="turn_snap")
    snap.exists = doc_data is not None
    snap.to_dict.return_value = doc_data or {}
    ref.get.return_value = snap
    return ref


# ── _claim_logic ─────────────────────────────────────────────────────────────


def test_claim_logic_writes_running_when_predicates_match():
    txn = MagicMock(name="txn")
    session = _mock_session_ref({"currentRunId": "r-1", "status": "queued"})
    turn = _mock_turn_ref({"status": "pending"})

    _claim_logic(txn, session, turn, "r-1")

    # Two updates issued: session → running + heartbeat fields, turn → running
    calls = txn.update.call_args_list
    assert len(calls) == 2
    sess_args = calls[0][0]
    assert sess_args[0] is session
    assert sess_args[1]["status"] == "running"
    assert "lastHeartbeat" in sess_args[1]
    assert "lastEventAt" in sess_args[1]
    turn_args = calls[1][0]
    assert turn_args[0] is turn
    assert turn_args[1] == {"status": "running"}


def test_claim_logic_raises_ownership_lost_on_runid_mismatch():
    txn = MagicMock()
    session = _mock_session_ref({"currentRunId": "r-other", "status": "queued"})
    turn = _mock_turn_ref({"status": "pending"})

    with pytest.raises(OwnershipLost) as ei:
        _claim_logic(txn, session, turn, "r-1")
    assert "runId" in str(ei.value)
    txn.update.assert_not_called()


def test_claim_logic_raises_ownership_lost_on_status_not_queued():
    txn = MagicMock()
    # Already running (e.g. another invocation took it)
    session = _mock_session_ref({"currentRunId": "r-1", "status": "running"})
    turn = _mock_turn_ref({"status": "pending"})

    with pytest.raises(OwnershipLost) as ei:
        _claim_logic(txn, session, turn, "r-1")
    assert "status" in str(ei.value)
    txn.update.assert_not_called()


def test_claim_logic_raises_on_terminal_status():
    txn = MagicMock()
    session = _mock_session_ref({"currentRunId": "r-1", "status": "error"})
    turn = _mock_turn_ref({"status": "pending"})

    with pytest.raises(OwnershipLost):
        _claim_logic(txn, session, turn, "r-1")


def test_claim_logic_raises_when_turn_not_pending():
    txn = MagicMock()
    session = _mock_session_ref({"currentRunId": "r-1", "status": "queued"})
    turn = _mock_turn_ref({"status": "running"})

    with pytest.raises(OwnershipLost) as ei:
        _claim_logic(txn, session, turn, "r-1")
    assert "turn.status" in str(ei.value)
    txn.update.assert_not_called()


# ── _fenced_logic ────────────────────────────────────────────────────────────


def test_fenced_logic_two_doc_running_predicate_matches():
    txn = MagicMock()
    session = _mock_session_ref({"currentRunId": "r-1", "status": "running"})
    turn = MagicMock(name="turn_ref")

    _fenced_logic(
        txn,
        session,
        turn,
        "r-1",
        {"status": "complete"},
        {"reply": "done"},
    )
    assert txn.update.call_count == 2


def test_fenced_logic_single_doc_skips_turn_update():
    """Heartbeat / lastEventAt paths pass turn_ref=None and turn_updates=None."""
    txn = MagicMock()
    session = _mock_session_ref({"currentRunId": "r-1", "status": "running"})

    _fenced_logic(
        txn,
        session,
        None,
        "r-1",
        {"lastHeartbeat": "ts"},
        None,
    )
    assert txn.update.call_count == 1


def test_fenced_logic_raises_when_status_not_running():
    """plan §"Cross-cutting" — status != 'running' must raise OwnershipLost
    so a watchdog/cleanup-flipped error state can't be resurrected."""
    txn = MagicMock()
    # Watchdog flipped this run to 'error' while we were processing
    session = _mock_session_ref({"currentRunId": "r-1", "status": "error"})

    with pytest.raises(OwnershipLost) as ei:
        _fenced_logic(txn, session, None, "r-1", {"x": 1}, None)
    assert "status" in str(ei.value)
    txn.update.assert_not_called()


def test_fenced_logic_raises_on_runid_drift():
    txn = MagicMock()
    # Session moved on to a newer turn / run
    session = _mock_session_ref({"currentRunId": "r-2", "status": "running"})

    with pytest.raises(OwnershipLost) as ei:
        _fenced_logic(txn, session, None, "r-1", {"x": 1}, None)
    assert "runId" in str(ei.value)


# ── _retry_critical ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_critical_succeeds_on_first_attempt():
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        return "ok"

    out = await _retry_critical(_factory, max_attempts=3, base_delay=0.001)
    assert out == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_critical_retries_on_transient_then_succeeds():
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise DeadlineExceeded("transient")
        return "ok"

    out = await _retry_critical(_factory, max_attempts=5, base_delay=0.001)
    assert out == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_critical_surfaces_after_max_attempts():
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        raise DeadlineExceeded("persistent")

    with pytest.raises(DeadlineExceeded):
        await _retry_critical(_factory, max_attempts=3, base_delay=0.001)
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_critical_never_retries_ownership_lost():
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        raise OwnershipLost("definitive")

    with pytest.raises(OwnershipLost):
        await _retry_critical(_factory, max_attempts=5, base_delay=0.001)
    assert calls == 1


# ── _heartbeat_loop ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heartbeat_loop_exits_on_ownership_lost(monkeypatch):
    """plan §"Write-class taxonomy" — heartbeat exits cleanly on
    OwnershipLost (definitive signal)."""
    fs = MagicMock()
    state = MagicMock()
    state.sid = "sid"
    state.run_id = "run"

    calls = 0

    async def _fake_fenced(_fs, _state, _updates):
        nonlocal calls
        calls += 1
        raise OwnershipLost("flipped")

    monkeypatch.setattr(firestore_progress, "fenced_session_update", _fake_fenced)
    monkeypatch.setattr(firestore_progress, "HEARTBEAT_INTERVAL_S", 0.001)

    await asyncio.wait_for(_heartbeat_loop(fs, state), timeout=1.0)
    assert calls == 1


@pytest.mark.asyncio
async def test_heartbeat_loop_continues_on_transient_blip(monkeypatch):
    """plan §"Write-class taxonomy" — heartbeat absorbs a transient blip
    and keeps pulsing. Only OwnershipLost / cancellation exits."""
    fs = MagicMock()
    state = MagicMock()
    state.sid = "sid"
    state.run_id = "run"

    calls = 0

    async def _fake_fenced(_fs, _state, _updates):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise GoogleAPICallError("blip")
        if calls >= 3:
            raise OwnershipLost("done testing")

    monkeypatch.setattr(firestore_progress, "fenced_session_update", _fake_fenced)
    monkeypatch.setattr(firestore_progress, "HEARTBEAT_INTERVAL_S", 0.001)

    await asyncio.wait_for(_heartbeat_loop(fs, state), timeout=1.0)
    # 2 transient blips absorbed + 3rd call raised OwnershipLost
    assert calls == 3


@pytest.mark.asyncio
async def test_heartbeat_loop_silent_on_cancellation(monkeypatch):
    fs = MagicMock()
    state = MagicMock()
    state.sid = "sid"
    state.run_id = "run"

    async def _fake_fenced(*_a, **_kw):
        await asyncio.sleep(60)  # block forever

    monkeypatch.setattr(firestore_progress, "fenced_session_update", _fake_fenced)
    monkeypatch.setattr(firestore_progress, "HEARTBEAT_INTERVAL_S", 0.001)

    task = asyncio.create_task(_heartbeat_loop(fs, state))
    await asyncio.sleep(0.05)
    task.cancel()
    # Must NOT raise — _heartbeat_loop swallows CancelledError.
    await task


# ── _halt_content ────────────────────────────────────────────────────────────


def test_halt_content_returns_types_content():
    """plan §"Cross-cutting" — `before_run_callback` returning a
    `types.Content` triggers ADK's early-exit at runners.py:819. Returning
    anything else (Event, None, raised exception) does NOT take that branch.
    """
    out = _halt_content("test_reason")
    assert isinstance(out, types.Content)
    assert out.role == "model"
    assert out.parts and out.parts[0].text and "test_reason" in out.parts[0].text


# ── FirestoreProgressPlugin lifecycle ────────────────────────────────────────


def _mock_invocation_context(*, sid: str, run_id: str, turn_idx: int, invocation_id: str):
    """Compose a stand-in InvocationContext that the plugin can read."""
    session = SimpleNamespace(
        id=f"se-{sid}",
        state={"runId": run_id, "turnIdx": turn_idx, "attempt": 1},
    )
    return SimpleNamespace(
        invocation_id=invocation_id,
        session=session,
        user_id="user-test",
        user_content=types.Content(
            role="user", parts=[types.Part(text="What about reviews?")]
        ),
    )


@pytest.mark.asyncio
async def test_plugin_before_run_halts_when_state_missing(monkeypatch):
    """If session.state has no runId, before_run returns a `types.Content`
    so the runner short-circuits cleanly via ADK's early-exit branch."""
    plugin = FirestoreProgressPlugin(project="superextra-site")

    bad_session = SimpleNamespace(id="se-x", state={})
    ctx = SimpleNamespace(
        invocation_id="inv-1",
        session=bad_session,
        user_id="user",
        user_content=None,
    )
    out = await plugin.before_run_callback(invocation_context=ctx)
    assert isinstance(out, types.Content)


@pytest.mark.asyncio
async def test_plugin_before_run_halts_on_ownership_lost(monkeypatch):
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()  # short-circuit lazy init

    async def _claim(_fs, _state):
        raise OwnershipLost("not claimable")

    monkeypatch.setattr(firestore_progress, "claim_invocation", _claim)

    ctx = _mock_invocation_context(
        sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-1"
    )
    out = await plugin.before_run_callback(invocation_context=ctx)
    assert isinstance(out, types.Content)
    assert "not_claimable" in out.parts[0].text


@pytest.mark.asyncio
async def test_plugin_before_run_registers_state_and_spawns_heartbeat(monkeypatch):
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()

    claim_calls = 0

    async def _claim(_fs, _state):
        nonlocal claim_calls
        claim_calls += 1

    heartbeat_started = asyncio.Event()
    heartbeat_can_exit = asyncio.Event()

    async def _hb(_fs, _state):
        heartbeat_started.set()
        await heartbeat_can_exit.wait()

    monkeypatch.setattr(firestore_progress, "claim_invocation", _claim)
    monkeypatch.setattr(firestore_progress, "_heartbeat_loop", _hb)
    # Block the title task too (it's a separate coroutine).
    async def _no_title(_q):
        return None

    monkeypatch.setattr(firestore_progress, "_generate_title", _no_title)

    ctx = _mock_invocation_context(
        sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-1"
    )
    out = await plugin.before_run_callback(invocation_context=ctx)
    assert out is None
    assert claim_calls == 1
    assert "inv-1" in plugin._states
    state = plugin._states["inv-1"]
    assert state.heartbeat_task is not None
    # First turn → title task spawned.
    assert state.title_task is not None

    # Cleanup
    heartbeat_can_exit.set()
    await asyncio.gather(
        state.heartbeat_task, state.title_task, return_exceptions=True
    )


@pytest.mark.asyncio
async def test_plugin_per_invocation_isolation(monkeypatch):
    """Two concurrent invocations on the same session don't share state."""
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()

    async def _noop_claim(_fs, _state):
        return None

    async def _noop_hb(_fs, _state):
        await asyncio.sleep(60)

    async def _no_title(_q):
        return None

    monkeypatch.setattr(firestore_progress, "claim_invocation", _noop_claim)
    monkeypatch.setattr(firestore_progress, "_heartbeat_loop", _noop_hb)
    monkeypatch.setattr(firestore_progress, "_generate_title", _no_title)

    a = _mock_invocation_context(sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-A")
    b = _mock_invocation_context(sid="abc", run_id="r-2", turn_idx=2, invocation_id="inv-B")

    await plugin.before_run_callback(invocation_context=a)
    await plugin.before_run_callback(invocation_context=b)

    state_a = plugin._states["inv-A"]
    state_b = plugin._states["inv-B"]

    state_a.final_reply = "answer-A"
    state_b.final_reply = "answer-B"

    assert state_a.final_reply != state_b.final_reply
    assert state_a is not state_b
    assert state_a.run_id == "r-1"
    assert state_b.run_id == "r-2"

    # Cleanup
    for s in (state_a, state_b):
        if s.heartbeat_task:
            s.heartbeat_task.cancel()
        await asyncio.gather(s.heartbeat_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_plugin_after_run_cancels_heartbeat_before_terminal_write(monkeypatch):
    """plan §4.3 sequence — `stop_heartbeat` must run BEFORE the terminal
    fenced write so a late tick can't clobber `status=complete`."""
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()

    order: list[str] = []
    heartbeat_cancelled = asyncio.Event()

    async def _hb(_fs, _state):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            order.append("heartbeat_cancelled")
            heartbeat_cancelled.set()
            raise

    async def _claim(_fs, _state):
        return None

    async def _no_title(_q):
        return None

    async def _terminal_write(_fs, _state, _su, _tu):
        # By the time terminal_write is called, heartbeat must already be
        # cancelled — that's the load-bearing ordering.
        assert heartbeat_cancelled.is_set(), (
            "terminal write fired before heartbeat was cancelled"
        )
        order.append("terminal_write")

    monkeypatch.setattr(firestore_progress, "claim_invocation", _claim)
    monkeypatch.setattr(firestore_progress, "_heartbeat_loop", _hb)
    monkeypatch.setattr(firestore_progress, "_generate_title", _no_title)
    monkeypatch.setattr(
        firestore_progress, "fenced_session_and_turn_update", _terminal_write
    )

    ctx = _mock_invocation_context(
        sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-1"
    )
    await plugin.before_run_callback(invocation_context=ctx)
    state = plugin._states["inv-1"]
    state.final_reply = "answer"  # so finalize() returns complete payload
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)
    # Drain title task quickly — _no_title returns None immediately, so
    # the title_task will have completed already.
    await asyncio.sleep(0)

    await plugin.after_run_callback(invocation_context=ctx)

    assert order == ["heartbeat_cancelled", "terminal_write"]
    assert "inv-1" not in plugin._states


@pytest.mark.asyncio
async def test_plugin_after_run_swallows_ownership_lost(monkeypatch):
    """plan §4.3 — terminal write OwnershipLost is logged, not re-raised."""
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()

    async def _claim(_fs, _state):
        return None

    async def _no_title(_q):
        return None

    async def _no_hb(_fs, _state):
        await asyncio.sleep(60)

    async def _terminal_write(_fs, _state, _su, _tu):
        raise OwnershipLost("watchdog flipped us")

    monkeypatch.setattr(firestore_progress, "claim_invocation", _claim)
    monkeypatch.setattr(firestore_progress, "_heartbeat_loop", _no_hb)
    monkeypatch.setattr(firestore_progress, "_generate_title", _no_title)
    monkeypatch.setattr(
        firestore_progress, "fenced_session_and_turn_update", _terminal_write
    )

    ctx = _mock_invocation_context(
        sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-1"
    )
    await plugin.before_run_callback(invocation_context=ctx)
    state = plugin._states["inv-1"]
    state.final_reply = "answer"
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    # Must not raise.
    await plugin.after_run_callback(invocation_context=ctx)


@pytest.mark.asyncio
async def test_plugin_on_event_writes_timeline_events(monkeypatch):
    """on_event_callback feeds events through observe_event and writes
    each returned timeline event."""
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()

    async def _claim(_fs, _state):
        return None

    async def _no_title(_q):
        return None

    async def _no_hb(_fs, _state):
        await asyncio.sleep(60)

    async def _no_fenced(_fs, _state, _updates):
        return None

    monkeypatch.setattr(firestore_progress, "claim_invocation", _claim)
    monkeypatch.setattr(firestore_progress, "_heartbeat_loop", _no_hb)
    monkeypatch.setattr(firestore_progress, "_generate_title", _no_title)
    monkeypatch.setattr(firestore_progress, "fenced_session_update", _no_fenced)

    ctx = _mock_invocation_context(
        sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-1"
    )
    await plugin.before_run_callback(invocation_context=ctx)
    state = plugin._states["inv-1"]
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)

    # Stub observe_event to return a known set of timeline events.
    state.observe_event = MagicMock(
        return_value=[{"kind": "note", "text": "hello"}, {"kind": "detail", "text": "x"}]
    )

    fake_event = SimpleNamespace()
    await plugin.on_event_callback(invocation_context=ctx, event=fake_event)

    state.observe_event.assert_called_once_with(fake_event)
    assert state.timeline_writer.write_timeline.await_count == 2

    # Cleanup
    state.heartbeat_task.cancel()
    await asyncio.gather(state.heartbeat_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_plugin_on_event_swallows_lastEventAt_ownership_lost(monkeypatch):
    """A flipped session shouldn't take down the run via on_event_callback —
    OwnershipLost on the lastEventAt bump is silently absorbed."""
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()

    async def _claim(_fs, _state):
        return None

    async def _no_title(_q):
        return None

    async def _no_hb(_fs, _state):
        await asyncio.sleep(60)

    fenced_calls = 0

    async def _fenced_with_ownership_lost(_fs, _state, _updates):
        nonlocal fenced_calls
        fenced_calls += 1
        raise OwnershipLost("watchdog")

    monkeypatch.setattr(firestore_progress, "claim_invocation", _claim)
    monkeypatch.setattr(firestore_progress, "_heartbeat_loop", _no_hb)
    monkeypatch.setattr(firestore_progress, "_generate_title", _no_title)
    monkeypatch.setattr(
        firestore_progress, "fenced_session_update", _fenced_with_ownership_lost
    )

    ctx = _mock_invocation_context(
        sid="abc", run_id="r-1", turn_idx=1, invocation_id="inv-1"
    )
    await plugin.before_run_callback(invocation_context=ctx)
    state = plugin._states["inv-1"]
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)
    state.observe_event = MagicMock(return_value=[])

    # Must not raise.
    await plugin.on_event_callback(invocation_context=ctx, event=SimpleNamespace())
    assert fenced_calls == 1

    # Cleanup
    state.heartbeat_task.cancel()
    await asyncio.gather(state.heartbeat_task, return_exceptions=True)
