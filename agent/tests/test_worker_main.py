"""Unit tests for worker_main transaction logic, title fallback, and source
extraction. No live Firestore / ADK — tests drive the pure-function
counterparts (``_fenced_update_logic``, ``_takeover_logic``) and mocks."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

# Worker module reads env at import time. Preset before importing.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("AGENT_ENGINE_ID", "0")

import pytest

from worker_main import (  # noqa: E402
    AGENT_ENGINE_ID,
    OwnershipLost,
    STALE_HEARTBEAT_S,
    _extract_sources_from_state_delta,
    _fallback_title,
    _fenced_update_logic,
    _strip_query_prefixes,
    _takeover_logic,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _mock_session_ref(doc_data: dict | None):
    """Return (session_ref, captured_updates_list) where ref.get(transaction=...)
    returns a snapshot of doc_data (None means doc doesn't exist)."""
    ref = MagicMock()
    snap = MagicMock()
    snap.exists = doc_data is not None
    snap.to_dict.return_value = doc_data or {}
    ref.get.return_value = snap
    return ref


# ── _fenced_update_logic ────────────────────────────────────────────────────


def test_fenced_update_commits_when_ids_match():
    ref = _mock_session_ref({
        "currentAttempt": 2,
        "currentWorkerId": "w-1",
    })
    txn = MagicMock()
    _fenced_update_logic(txn, ref, 2, "w-1", {"lastHeartbeat": "x"})
    txn.update.assert_called_once_with(ref, {"lastHeartbeat": "x"})


def test_fenced_update_raises_ownership_lost_on_attempt_mismatch():
    ref = _mock_session_ref({"currentAttempt": 3, "currentWorkerId": "w-1"})
    txn = MagicMock()
    with pytest.raises(OwnershipLost):
        _fenced_update_logic(txn, ref, 2, "w-1", {"lastHeartbeat": "x"})
    txn.update.assert_not_called()


def test_fenced_update_raises_ownership_lost_on_worker_mismatch():
    ref = _mock_session_ref({"currentAttempt": 2, "currentWorkerId": "other-w"})
    txn = MagicMock()
    with pytest.raises(OwnershipLost):
        _fenced_update_logic(txn, ref, 2, "w-1", {})


# ── _takeover_logic ─────────────────────────────────────────────────────────


def _fresh_now() -> datetime:
    return datetime.now(timezone.utc)


def test_takeover_first_delivery_queued_transitions_to_running():
    # agentStream seeded the doc as status=queued, currentRunId=run-1.
    ref = _mock_session_ref({
        "status": "queued",
        "currentRunId": "run-1",
        "currentAttempt": 0,
        "userId": "alice",
        "lastHeartbeat": None,
    })
    txn = MagicMock()
    out = _takeover_logic(txn, ref, "alice", "run-1", "w-1")
    assert out == {"action": "run", "attempt": 1}
    txn.update.assert_called_once()
    updates = txn.update.call_args[0][1]
    assert updates["status"] == "running"
    assert updates["currentWorkerId"] == "w-1"
    assert updates["currentAttempt"] == 1
    # Plan: takeover must NOT rewrite currentRunId.
    assert "currentRunId" not in updates


def test_takeover_increments_attempt_after_stale_heartbeat():
    ref = _mock_session_ref({
        "status": "running",
        "currentRunId": "run-1",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now() - timedelta(seconds=STALE_HEARTBEAT_S + 60),
    })
    txn = MagicMock()
    out = _takeover_logic(txn, ref, "alice", "run-1", "w-2")
    assert out["action"] == "run"
    assert out["attempt"] == 2
    txn.update.assert_called_once()


def test_takeover_fresh_heartbeat_returns_poll():
    ref = _mock_session_ref({
        "status": "running",
        "currentRunId": "run-1",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now(),
    })
    txn = MagicMock()
    out = _takeover_logic(txn, ref, "alice", "run-1", "w-2")
    assert out == {"action": "poll"}
    txn.update.assert_not_called()


def test_takeover_stale_run_redelivery_returns_noop_stale_and_does_not_write():
    # Session moved to run-2; this is run-1 redelivery.
    ref = _mock_session_ref({
        "status": "running",
        "currentRunId": "run-2",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now(),
    })
    txn = MagicMock()
    out = _takeover_logic(txn, ref, "alice", "run-1", "w-3")
    assert out == {"action": "noop_stale"}
    txn.update.assert_not_called()


def test_takeover_already_complete_returns_noop_complete():
    ref = _mock_session_ref({
        "status": "complete",
        "currentRunId": "run-1",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now(),
    })
    txn = MagicMock()
    out = _takeover_logic(txn, ref, "alice", "run-1", "w-1")
    assert out == {"action": "noop_complete"}
    txn.update.assert_not_called()


def test_takeover_already_error_returns_noop_complete():
    ref = _mock_session_ref({
        "status": "error",
        "currentRunId": "run-1",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now(),
    })
    txn = MagicMock()
    out = _takeover_logic(txn, ref, "alice", "run-1", "w-1")
    assert out == {"action": "noop_complete"}


def test_takeover_missing_doc_raises_500():
    from fastapi import HTTPException
    ref = _mock_session_ref(None)
    txn = MagicMock()
    with pytest.raises(HTTPException) as e:
        _takeover_logic(txn, ref, "alice", "run-1", "w-1")
    assert e.value.status_code == 500


def test_takeover_userid_mismatch_raises_500():
    from fastapi import HTTPException
    ref = _mock_session_ref({
        "status": "queued",
        "currentRunId": "run-1",
        "userId": "alice",
        "currentAttempt": 0,
    })
    txn = MagicMock()
    with pytest.raises(HTTPException) as e:
        _takeover_logic(txn, ref, "bob", "run-1", "w-1")
    assert e.value.status_code == 500
    assert "userId mismatch" in e.value.detail


# ── Source extraction ──────────────────────────────────────────────────────


def test_extract_sources_dedupes_across_specialists():
    sd = {
        "market_result": "[A](https://a.com) [B](https://b.com)",
        "revenue_result": "[A-dup](https://a.com) [C](https://c.com)",
        "guest_result": "NOT_RELEVANT",
        "other_key": "ignored",
    }
    sources = _extract_sources_from_state_delta(sd)
    # Order is specialist-by-specialist; within specialist, first-seen.
    urls = [s["url"] for s in sources]
    assert urls == ["https://a.com", "https://b.com", "https://c.com"]


def test_extract_sources_skips_non_string_values():
    sd = {"market_result": {"not": "a string"}, "pricing_result": "[A](https://x.com)"}
    assert _extract_sources_from_state_delta(sd) == [
        {"title": "A", "url": "https://x.com"}
    ]


# ── Title fallback ─────────────────────────────────────────────────────────


def test_strip_query_prefixes_peels_both():
    q = "[Date: 2026-04-20] [Context: asking about Umami, Berlin (Place ID: xxx)] What about reviews?"
    assert _strip_query_prefixes(q) == "What about reviews?"


def test_strip_query_prefixes_handles_no_prefix():
    assert _strip_query_prefixes("plain question") == "plain question"


def test_strip_query_prefixes_handles_only_date():
    assert _strip_query_prefixes("[Date: 2026-04-20] Hello") == "Hello"


def test_fallback_title_strips_prefixes_and_truncates():
    q = "[Date: 2026-04-20] What service issues come up in customer reviews of this restaurant?"
    title = _fallback_title(q)
    assert title
    assert len(title) <= 40
    assert not title.startswith("[Date")


def test_fallback_title_empty_query_returns_placeholder():
    assert _fallback_title("") == "Untitled"
    assert _fallback_title("[Date: 2026-04-20]") == "Untitled"


# ── Env sanity ──────────────────────────────────────────────────────────────


def test_default_agent_engine_id_is_set():
    # Regression guard: if someone drops the baked-in default, tests still
    # need to pass in CI without env vars. We override at module top; confirm.
    assert AGENT_ENGINE_ID


# ── Structured logging ─────────────────────────────────────────────────────


def test_json_formatter_emits_correlation_keys():
    import json
    import logging

    from worker_main import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="x.py", lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    record.sid = "sid-abc"
    record.runId = "run-123"
    record.attempt = 2
    record.workerId = "w-1"
    record.cloudTaskName = "projects/p/locations/l/queues/q/tasks/run-123"
    record.trace = "projects/p/traces/t-1"

    payload = json.loads(formatter.format(record))
    assert payload["severity"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["sid"] == "sid-abc"
    assert payload["runId"] == "run-123"
    assert payload["attempt"] == 2
    assert payload["workerId"] == "w-1"
    assert payload["cloudTaskName"].endswith("/tasks/run-123")
    assert payload["logging.googleapis.com/trace"] == "projects/p/traces/t-1"


def test_json_formatter_omits_absent_correlation_keys():
    import json
    import logging

    from worker_main import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.WARNING, pathname="x.py", lineno=1,
        msg="only message", args=(), exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert "sid" not in payload
    assert "runId" not in payload
    assert "logging.googleapis.com/trace" not in payload


def test_trace_from_header_builds_cloud_logging_resource_name():
    from worker_main import PROJECT as WORKER_PROJECT, _trace_from_header

    assert _trace_from_header(None) is None
    assert _trace_from_header("") is None
    assert _trace_from_header("abc123/456;o=1") == f"projects/{WORKER_PROJECT}/traces/abc123"
    assert _trace_from_header("abc123") == f"projects/{WORKER_PROJECT}/traces/abc123"


# ── Runner exception propagation (plan §Phase 10) ──────────────────────────
#
# These tests drive the `run` handler end-to-end with mocked module
# singletons. Verify that:
#
#   (a) a synthetic exception mid-stream does NOT escape out of the handler
#       — it's caught and turned into a 200 with action='pipeline_error',
#   (b) before the error write, the heartbeat task is cancelled,
#   (c) status=error is written via the fenced update path.


class _AsyncIterError:
    """Async-iterable that yields no events and raises on __anext__."""

    def __init__(self, exc):
        self._exc = exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self._exc


def _build_run_request():
    from worker_main import RunRequest

    return RunRequest(
        sessionId="sid-1",
        runId="run-1",
        adkSessionId="adk-1",
        userId="alice",
        queryText="[Date: 2026-04-20] hello",
        isFirstMessage=False,
    )


def _fake_request(headers=None):
    class FakeRequest:
        def __init__(self):
            self.headers = headers or {}

    return FakeRequest()


@pytest.mark.asyncio
async def test_runner_exception_writes_status_error_and_returns_200(monkeypatch):
    """Pipeline exception → caught, `status='error'` fenced-written, 200.

    Do NOT propagate infra 500 for deterministic pipeline failures — that
    would have Cloud Tasks retry the same broken run.
    """
    import worker_main

    # Replace the heavyweight module singletons with lightweight mocks.
    fake_runner = MagicMock()
    fake_runner.run_async = lambda **kwargs: _AsyncIterError(RuntimeError("boom"))

    fake_fs = MagicMock()
    fake_fs.collection.return_value.document.return_value = MagicMock()
    fake_fs.transaction.return_value = MagicMock()

    monkeypatch.setattr(worker_main, "_runner", fake_runner)
    monkeypatch.setattr(worker_main, "_fs", fake_fs)
    monkeypatch.setattr(worker_main, "_session_svc", MagicMock())

    # Takeover returns {action: 'run', attempt: 1} straight away.
    monkeypatch.setattr(worker_main, "_takeover_txn", lambda *a, **k: {"action": "run", "attempt": 1})

    # Heartbeat + fenced update cancellation: make them awaitable-no-ops, and
    # record which writes were attempted.
    fenced_writes = []

    async def fake_fenced_update(sid, attempt, worker_id, updates):
        fenced_writes.append(updates)

    hb_cancel_calls = []

    async def fake_cancel_heartbeat():
        hb_cancel_calls.append(True)

    monkeypatch.setattr(worker_main, "_fenced_update", fake_fenced_update)
    monkeypatch.setattr(worker_main, "_cancel_heartbeat", fake_cancel_heartbeat)
    monkeypatch.setattr(worker_main, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0))

    body = _build_run_request()
    result = await worker_main.run(body, _fake_request())

    assert result["ok"] is False
    assert result["action"] == "pipeline_error"
    # Heartbeat cancelled at least once on the way out. Exact count depends
    # on whether the explicit pre-write cancel is kept alongside the
    # `finally` cancel — both paths are correct as long as at least one
    # cancel happens BEFORE the fenced error write. The companion test
    # `test_pipeline_exception_cancels_heartbeat_before_error_write` is
    # the canonical ordering assertion; this one just verifies basic flow.
    assert len(hb_cancel_calls) >= 1
    # Error state written via fenced update.
    error_writes = [u for u in fenced_writes if u.get("status") == "error"]
    assert len(error_writes) == 1
    assert "RuntimeError" in error_writes[0]["error"]


@pytest.mark.asyncio
async def test_pipeline_exception_cancels_heartbeat_before_error_write(monkeypatch):
    """3.3 / T-weak — verify call ORDER, not just call count: in the
    pipeline-exception branch, `_cancel_heartbeat` must be awaited BEFORE
    `_fenced_update({'status': 'error', ...})` so a late heartbeat tick
    can't clobber the error write with a fresh timestamp.
    """
    import worker_main

    fake_runner = MagicMock()
    fake_runner.run_async = lambda **kwargs: _AsyncIterError(RuntimeError("boom"))

    fake_fs = MagicMock()
    fake_fs.collection.return_value.document.return_value = MagicMock()
    fake_fs.transaction.return_value = MagicMock()

    monkeypatch.setattr(worker_main, "_runner", fake_runner)
    monkeypatch.setattr(worker_main, "_fs", fake_fs)
    monkeypatch.setattr(worker_main, "_session_svc", MagicMock())
    monkeypatch.setattr(worker_main, "_takeover_txn", lambda *a, **k: {"action": "run", "attempt": 1})

    # Shared event-order recorder. Captures `('cancel',)` and `('fenced',
    # <updates_dict>)` as they happen; ordering across the two mocks is
    # what we assert.
    calls: list[tuple] = []

    async def recording_cancel():
        calls.append(("cancel",))

    async def recording_fenced_update(sid, attempt, worker_id, updates):
        calls.append(("fenced", updates))

    monkeypatch.setattr(worker_main, "_cancel_heartbeat", recording_cancel)
    monkeypatch.setattr(worker_main, "_fenced_update", recording_fenced_update)
    monkeypatch.setattr(worker_main, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0))

    body = _build_run_request()
    result = await worker_main.run(body, _fake_request())

    assert result["action"] == "pipeline_error"

    # The `status='error'` fenced write must appear AFTER the first cancel
    # in the recorded sequence. The second cancel (from `finally`) may
    # appear after the error write — that's idempotent and expected.
    cancel_indices = [i for i, c in enumerate(calls) if c[0] == "cancel"]
    error_write_indices = [
        i for i, c in enumerate(calls)
        if c[0] == "fenced" and isinstance(c[1], dict) and c[1].get("status") == "error"
    ]
    assert cancel_indices, "expected at least one cancel call"
    assert error_write_indices, "expected a status=error fenced write"
    assert cancel_indices[0] < error_write_indices[0], (
        f"cancel must precede error write; got calls={calls!r}"
    )


# ── Tier 1.2 + 1.3 — state_delta accumulation + terminal promotion ─────────
#
# Drive the `run` handler with a synthetic event stream so we can verify:
#
#   1.2 — sources from earlier specialist events flow into the terminal
#         `sources` array on the session doc (not just the synthesiser's
#         final state_delta).
#   1.3 — the mapper's `type='complete'` emission is what promotes to
#         `final_reply`. Works for both synthesiser finals and router
#         clarifications.
#   1.3 — the simplified sanity gate (`not final_reply or
#         not final_reply.strip()`) rejects empty and whitespace-only
#         replies; previously-rejected short valid replies go through.


class _AsyncIterEvents:
    """Async-iterable that yields a fixed list of events then stops."""

    def __init__(self, events):
        self._events = list(events)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._idx]
        self._idx += 1
        return event


def _mk_event(state_delta: dict, *, author: str | None = None):
    """Synthetic event with the minimum shape the worker reads:
    `event.actions.state_delta` for accumulation."""
    actions = SimpleNamespace(state_delta=state_delta)
    return SimpleNamespace(actions=actions, author=author)


def _install_run_harness(monkeypatch, *, events, emissions):
    """Wire up the module singletons + mocks for a `run` invocation.

    ``events`` is the sequence of ADK events yielded by `_runner.run_async`.
    ``emissions`` is a matching list of ``{'type': ..., 'data': ...}`` dicts
    returned by `map_and_write_event` for each event (or `None` to skip).
    Returns `(fenced_writes, hb_cancel_calls)` for post-run assertions.
    """
    import worker_main

    assert len(events) == len(emissions)

    fake_runner = MagicMock()
    fake_runner.run_async = lambda **kwargs: _AsyncIterEvents(events)

    fake_fs = MagicMock()
    fake_fs.collection.return_value.document.return_value = MagicMock()
    fake_fs.transaction.return_value = MagicMock()

    monkeypatch.setattr(worker_main, "_runner", fake_runner)
    monkeypatch.setattr(worker_main, "_fs", fake_fs)
    monkeypatch.setattr(worker_main, "_session_svc", MagicMock())
    monkeypatch.setattr(worker_main, "_takeover_txn", lambda *a, **k: {"action": "run", "attempt": 1})

    emission_iter = iter(emissions)

    async def fake_map_and_write_event(**kwargs):
        try:
            return next(emission_iter)
        except StopIteration:
            return None

    monkeypatch.setattr(worker_main, "map_and_write_event", fake_map_and_write_event)

    fenced_writes: list[dict] = []

    async def fake_fenced_update(sid, attempt, worker_id, updates):
        fenced_writes.append(updates)

    hb_cancel_calls: list[bool] = []

    async def fake_cancel_heartbeat():
        hb_cancel_calls.append(True)

    monkeypatch.setattr(worker_main, "_fenced_update", fake_fenced_update)
    monkeypatch.setattr(worker_main, "_cancel_heartbeat", fake_cancel_heartbeat)
    monkeypatch.setattr(worker_main, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0))
    # Avoid the Gemini Flash title call in tests; deterministic fallback.
    monkeypatch.setattr(worker_main, "_generate_title", lambda q: asyncio.sleep(0, result="test"))

    return fenced_writes, hb_cancel_calls


@pytest.mark.asyncio
async def test_sources_accumulate_across_specialist_events(monkeypatch):
    """1.2 — specialist outputs in earlier events must merge into the
    terminal `sources` array, not just the synthesiser's final state_delta.
    """
    events = [
        _mk_event(
            {"market_result": "See [Source A](https://a.example) for details."},
            author="market_landscape",
        ),
        _mk_event(
            {"review_result": "Reviews complain; see [Source B](https://b.example)."},
            author="review_analyst",
        ),
        _mk_event(
            {"final_report": "Overall summary with [Source C](https://c.example)."},
            author="synthesizer",
        ),
    ]
    emissions = [
        None,  # specialist mid-event — mapper may emit activity, not relevant
        None,
        {
            "type": "complete",
            "data": {
                "reply": "Overall summary with [Source C](https://c.example).",
                "sources": [{"title": "Source C", "url": "https://c.example"}],
            },
        },
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    body = _build_run_request()
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"

    complete_writes = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete_writes) == 1
    sources = complete_writes[0]["sources"]
    urls = {s["url"] for s in sources}
    # Synth's own markdown source + both specialists' accumulated sources.
    assert urls == {"https://a.example", "https://b.example", "https://c.example"}


@pytest.mark.asyncio
async def test_router_clarification_promotes_to_session_doc(monkeypatch):
    """1.3 — a short router clarification with no synthesiser must still
    land as `status='complete'` on the session doc."""
    events = [_mk_event({}, author="router")]
    emissions = [
        {
            "type": "complete",
            "data": {"reply": "Which location?", "sources": []},
        }
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    body = _build_run_request()
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"

    complete_writes = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete_writes) == 1
    assert complete_writes[0]["reply"] == "Which location?"
    # No `status=error` anywhere — the old len<100 gate would have rejected.
    assert not any(u.get("status") == "error" for u in fenced_writes)


@pytest.mark.asyncio
async def test_no_final_report_emits_empty_reply_error(monkeypatch):
    """1.3 — pipeline that produces no terminal `complete` emission must
    write `status='error'` (empty-reply guard still catches this)."""
    events = [_mk_event({"places_context": "some place"})]
    emissions = [None]  # mapper decided not to emit anything terminal

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    body = _build_run_request()
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is False
    assert result["action"] == "empty_or_malformed_reply"

    error_writes = [u for u in fenced_writes if u.get("status") == "error"]
    assert len(error_writes) == 1
    assert error_writes[0]["error"] == "empty_or_malformed_reply"


@pytest.mark.asyncio
async def test_whitespace_only_final_report_is_rejected(monkeypatch):
    """1.3 — whitespace-only reply must NOT pass the sanity gate.

    `_has_state_delta` in the mapper only filters `if not value` (empty
    string), so a `"   "` final_report would slip through both the mapper
    and a bare `not final_reply` check. The `.strip()` closes this.
    """
    events = [_mk_event({"final_report": "   "}, author="synthesizer")]
    emissions = [
        {
            "type": "complete",
            "data": {"reply": "   ", "sources": []},
        }
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    body = _build_run_request()
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is False
    assert result["action"] == "empty_or_malformed_reply"


@pytest.mark.asyncio
async def test_poll_until_resolved_times_out_after_seven_minutes(monkeypatch):
    """3.2 / T4 — `_poll_until_resolved` must raise HTTPException(500) after
    the 7-minute ceiling (`POLL_WAIT_MAX_S=420s`) when no state change
    resolves the wait. Verifies the 4th exit branch that wasn't covered.
    """
    import worker_main
    from fastapi import HTTPException

    # Mock Firestore ref.get to always return an in-flight running state
    # with a fresh heartbeat (so no takeover or noop branch fires).
    fake_snap = MagicMock()
    fake_snap.to_dict.return_value = {
        "status": "running",
        "currentRunId": "run-1",
        "userId": "alice",
        "lastHeartbeat": datetime.now(timezone.utc),
    }
    fake_ref = MagicMock()
    fake_ref.get.return_value = fake_snap

    fake_fs = MagicMock()
    fake_fs.collection.return_value.document.return_value = fake_ref
    monkeypatch.setattr(worker_main, "_fs", fake_fs)

    # Advance `asyncio.get_event_loop().time()` past POLL_WAIT_MAX_S on the
    # first check, and make asyncio.sleep a no-op so the loop doesn't
    # actually sleep.
    start_time = 1000.0
    times = iter([start_time, start_time + worker_main.POLL_WAIT_MAX_S + 1.0])

    class FakeLoop:
        def time(self):
            return next(times)

    monkeypatch.setattr(asyncio, "get_event_loop", lambda: FakeLoop())

    async def fake_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(HTTPException) as excinfo:
        await worker_main._poll_until_resolved("sid-1", "run-1", "w-1")
    assert excinfo.value.status_code == 500
    assert "poll_timeout" in excinfo.value.detail


@pytest.mark.asyncio
async def test_cancelled_error_propagates_after_heartbeat_cancel(monkeypatch):
    """2.2 — `asyncio.CancelledError` mid-stream must re-raise AFTER the
    heartbeat task has been cancelled by the `finally` branch.

    Verifies the plan's cancel-order guarantee on cancellation paths,
    which the old `except Exception` chain violated (CancelledError is
    `BaseException`-rooted, not `Exception`-rooted, so the old code
    leaked the heartbeat loop).
    """
    events = [_mk_event({"market_result": "partial"}, author="market_landscape")]
    emissions = [None]

    # Install the harness but override `run_async` to raise CancelledError
    # after yielding one event.
    fenced_writes, hb_cancel_calls = _install_run_harness(
        monkeypatch, events=events, emissions=emissions
    )

    import worker_main

    class _AsyncIterThenCancel:
        def __init__(self, events):
            self._events = list(events)
            self._idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._idx < len(self._events):
                event = self._events[self._idx]
                self._idx += 1
                return event
            raise asyncio.CancelledError()

    fake_runner = MagicMock()
    fake_runner.run_async = lambda **kwargs: _AsyncIterThenCancel(events)
    monkeypatch.setattr(worker_main, "_runner", fake_runner)

    body = _build_run_request()
    with pytest.raises(asyncio.CancelledError):
        await worker_main.run(body, _fake_request())

    # Heartbeat cancelled on the way out (via `finally`).
    assert hb_cancel_calls == [True]
    # No status=error write — we don't own the completion.
    assert not any(u.get("status") == "error" for u in fenced_writes)
    assert not any(u.get("status") == "complete" for u in fenced_writes)


@pytest.mark.asyncio
async def test_short_synth_reply_now_passes_sanity_gate(monkeypatch):
    """1.3 — a 30-char valid synth reply used to be false-rejected by the
    old `len<100` gate. After simplification it must pass."""
    short = "Closed permanently. See sign."  # 29 chars — under the old gate.
    events = [_mk_event({"final_report": short}, author="synthesizer")]
    emissions = [
        {"type": "complete", "data": {"reply": short, "sources": []}}
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    body = _build_run_request()
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"
    complete_writes = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete_writes) == 1
    assert complete_writes[0]["reply"] == short
