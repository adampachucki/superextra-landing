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
    TurnSummaryBuilder,
    _fallback_title,
    _fenced_update_logic,
    _fenced_update_session_and_turn_logic,
    _merge_source,
    _strip_query_prefixes,
    _takeover_logic,
    _turn_doc_key,
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


def _mock_turn_ref():
    """Bare turn-doc ref; tests inspect txn.update calls by positional arg."""
    return MagicMock(name="turn_ref")


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
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    out = _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-1")
    assert out == {"action": "run", "attempt": 1}
    # Two update calls in one transaction: session + turn.
    assert txn.update.call_count == 2
    session_call = next(c for c in txn.update.call_args_list if c[0][0] is ref)
    turn_call = next(c for c in txn.update.call_args_list if c[0][0] is turn_ref)
    updates = session_call[0][1]
    assert updates["status"] == "running"
    assert updates["currentWorkerId"] == "w-1"
    assert updates["currentAttempt"] == 1
    # Plan: takeover must NOT rewrite currentRunId.
    assert "currentRunId" not in updates
    # Turn doc flipped to running atomically (pin #4).
    assert turn_call[0][1] == {"status": "running"}


def test_takeover_writes_turn_status_running_in_same_transaction():
    # Pin #4 from the verification-report checklist: session + turn writes
    # must land inside the same fenced transaction; no follow-up write.
    ref = _mock_session_ref({
        "status": "queued",
        "currentRunId": "run-1",
        "currentAttempt": 0,
        "userId": "alice",
        "lastHeartbeat": None,
    })
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-1")
    refs_updated = [c[0][0] for c in txn.update.call_args_list]
    assert ref in refs_updated
    assert turn_ref in refs_updated
    # Exactly these two — no third spurious write.
    assert len(refs_updated) == 2


def test_takeover_increments_attempt_after_stale_heartbeat():
    ref = _mock_session_ref({
        "status": "running",
        "currentRunId": "run-1",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now() - timedelta(seconds=STALE_HEARTBEAT_S + 60),
    })
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    out = _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-2")
    assert out["action"] == "run"
    assert out["attempt"] == 2
    # Session + turn updates in same txn.
    assert txn.update.call_count == 2


def test_takeover_fresh_heartbeat_returns_poll():
    ref = _mock_session_ref({
        "status": "running",
        "currentRunId": "run-1",
        "currentAttempt": 1,
        "userId": "alice",
        "lastHeartbeat": _fresh_now(),
    })
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    out = _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-2")
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
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    out = _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-3")
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
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    out = _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-1")
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
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    out = _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-1")
    assert out == {"action": "noop_complete"}


def test_takeover_missing_doc_raises_500():
    from fastapi import HTTPException
    ref = _mock_session_ref(None)
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    with pytest.raises(HTTPException) as e:
        _takeover_logic(txn, ref, turn_ref, "alice", "run-1", "w-1")
    assert e.value.status_code == 500


def test_takeover_userid_mismatch_raises_500_when_creator_uid_does_not_match():
    """Defensive check at worker_main.py:257 — under server-stored sessions,
    agentStream puts `session.userId` (the creator UID) into the task body.
    If those disagree it's a bug in agentStream; the worker refuses to
    continue so Cloud Tasks surfaces it via retries. Complements the
    creator-UID-on-followup test below which exercises the NO-raise path."""
    from fastapi import HTTPException
    ref = _mock_session_ref({
        "status": "queued",
        "currentRunId": "run-1",
        "userId": "alice",  # stored creator
        "currentAttempt": 0,
    })
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    with pytest.raises(HTTPException) as e:
        # Task body would carry some UID other than alice → bug.
        _takeover_logic(txn, ref, turn_ref, "bob", "run-1", "w-1")
    assert e.value.status_code == 500
    assert "userId mismatch" in e.value.detail


def test_takeover_userid_check_passes_when_body_carries_creator_uid():
    """Complements the mismatch test: under server-stored sessions,
    agentStream computes creatorUid from the session's stored userId (or
    the submitter on first turn) and puts that value into the Cloud Task
    body. So on follow-up turns the body carries the ORIGINAL creator UID
    even when a different visitor submitted — and the defensive check
    passes because session.userId == body.userId by contract.

    This is the load-bearing invariant from the plan: ADK
    `VertexAiSessionService.get_session` enforces
    `session.user_id == passed user_id`, so the creator UID must reach the
    worker's Runner call without being overwritten by the submitter UID
    en route."""
    ref = _mock_session_ref({
        "status": "queued",
        "currentRunId": "run-1",
        "currentAttempt": 0,
        "userId": "alice-creator",  # original chat creator, per plan §5/§8
        "lastHeartbeat": None,
    })
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    # agentStream puts session.userId in the task body; it's what reaches
    # the worker as body.userId. So even on a follow-up from visitor bob,
    # body.userId == alice-creator here.
    out = _takeover_logic(txn, ref, turn_ref, "alice-creator", "run-1", "w-1")
    assert out == {"action": "run", "attempt": 1}


# ── _fenced_update_session_and_turn_logic ──────────────────────────────────


def test_fenced_update_session_and_turn_commits_both_when_ids_match():
    ref = _mock_session_ref({
        "currentAttempt": 2,
        "currentWorkerId": "w-1",
    })
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    session_updates = {"status": "complete"}
    turn_updates = {"status": "complete", "reply": "ok"}
    _fenced_update_session_and_turn_logic(
        txn, ref, turn_ref, 2, "w-1", session_updates, turn_updates
    )
    assert txn.update.call_count == 2
    # Every call's first positional arg is the ref; partition by identity.
    refs = [c[0][0] for c in txn.update.call_args_list]
    data = {id(c[0][0]): c[0][1] for c in txn.update.call_args_list}
    assert ref in refs
    assert turn_ref in refs
    assert data[id(ref)] == session_updates
    assert data[id(turn_ref)] == turn_updates


def test_fenced_update_session_and_turn_raises_on_attempt_mismatch():
    ref = _mock_session_ref({"currentAttempt": 3, "currentWorkerId": "w-1"})
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    with pytest.raises(OwnershipLost):
        _fenced_update_session_and_turn_logic(
            txn, ref, turn_ref, 2, "w-1", {"status": "complete"}, {}
        )
    # Neither write landed.
    txn.update.assert_not_called()


def test_fenced_update_session_and_turn_raises_on_worker_mismatch():
    ref = _mock_session_ref({"currentAttempt": 2, "currentWorkerId": "other-w"})
    turn_ref = _mock_turn_ref()
    txn = MagicMock()
    with pytest.raises(OwnershipLost):
        _fenced_update_session_and_turn_logic(
            txn, ref, turn_ref, 2, "w-1", {}, {}
        )
    txn.update.assert_not_called()


def test_turn_doc_key_zero_pads_to_four_digits():
    # Pin #3: turn index travels as integer; doc key is the formatted string.
    assert _turn_doc_key(1) == "0001"
    assert _turn_doc_key(10) == "0010"
    assert _turn_doc_key(9999) == "9999"


# ── Source accumulator ─────────────────────────────────────────────────────


def test_merge_source_appends_new_url():
    sources: list[dict] = []
    seen: set[str] = set()
    _merge_source(sources, seen, {"title": "A", "url": "https://a.com"})
    assert sources == [{"title": "A", "url": "https://a.com"}]
    assert seen == {"https://a.com"}


def test_merge_source_dedupes_by_url():
    sources: list[dict] = [{"title": "A", "url": "https://a.com"}]
    seen: set[str] = {"https://a.com"}
    _merge_source(sources, seen, {"title": "A-dup", "url": "https://a.com"})
    _merge_source(sources, seen, {"title": "B", "url": "https://b.com"})
    assert [s["url"] for s in sources] == ["https://a.com", "https://b.com"]


def test_merge_source_skips_entries_without_url():
    sources: list[dict] = []
    seen: set[str] = set()
    _merge_source(sources, seen, {"title": "A"})  # no url
    _merge_source(sources, seen, "not a dict")  # wrong type
    _merge_source(sources, seen, {"url": ""})  # empty url
    assert sources == []


# ── TurnSummaryBuilder: find_tripadvisor_restaurant accumulation ───────────


def _event_with_tripadvisor_response(response: dict) -> SimpleNamespace:
    """Minimal event shape that TurnSummaryBuilder.observe_event can read."""
    fr = SimpleNamespace(name="find_tripadvisor_restaurant", response=response)
    part = SimpleNamespace(text=None, function_call=None, function_response=fr)
    return SimpleNamespace(
        author="review_analyst",
        id="evt-ta",
        content=SimpleNamespace(parts=[part]),
        actions=SimpleNamespace(state_delta=None),
        grounding_metadata=None,
        is_final_response=lambda: False,
    )


def test_tripadvisor_success_response_accumulates_link_and_name():
    """Regression guard for the `status == "success"` branch of
    TurnSummaryBuilder.observe_event. A verified TripAdvisor match puts
    its URL into `sources` and its display name into `venues`."""
    builder = TurnSummaryBuilder(started_at_ms=0)
    event = _event_with_tripadvisor_response({
        "status": "success",
        "tripadvisor_link": "https://www.tripadvisor.com/Restaurant_Review-123-Noma",
        "name": "Noma",
    })

    builder.observe_event(event, state={})

    assert any("Restaurant_Review-123-Noma" in src for src in builder.sources)
    assert "noma" in builder.venues


def test_tripadvisor_unverified_response_skips_accumulation():
    """Regression guard for the defense-in-depth status gate added in
    the coord-verification refactor. An `unverified` response — even if
    it somehow carried a `tripadvisor_link` or `name` — must not leak
    into the timeline counters. Protects against silent misattribution
    if a future tool change partially re-populates the payload."""
    builder = TurnSummaryBuilder(started_at_ms=0)
    event = _event_with_tripadvisor_response({
        "status": "unverified",
        "error_message": "coords didn't match",
        # Defensive: simulate a hypothetical partial payload leak.
        "tripadvisor_link": "https://www.tripadvisor.com/Restaurant_Review-999-Wrong",
        "name": "Wrong Venue",
    })

    builder.observe_event(event, state={})

    assert not any("Restaurant_Review-999-Wrong" in src for src in builder.sources)
    assert "wrong venue" not in builder.venues


def test_tripadvisor_error_response_skips_accumulation():
    """Transport failures also skip accumulation — distinct from unverified
    in status wording but equivalent in source-gating behavior."""
    builder = TurnSummaryBuilder(started_at_ms=0)
    event = _event_with_tripadvisor_response({
        "status": "error",
        "error_message": "SerpAPI 500",
    })

    builder.observe_event(event, state={})

    assert builder.sources == set()
    assert builder.venues == set()


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
    # `event` + `reason` are the synth telemetry fields emitted from
    # `_synth_fallback_callback`. `reason` is in _STRUCTURED_LOG_KEYS so the
    # formatter must surface it as a top-level jsonPayload field — that's
    # what the Cloud Logging synth-outcome rate query depends on.
    record.event = "synth_outcome"
    record.reason = "MALFORMED_FUNCTION_CALL"

    payload = json.loads(formatter.format(record))
    assert payload["severity"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["sid"] == "sid-abc"
    assert payload["runId"] == "run-123"
    assert payload["attempt"] == 2
    assert payload["workerId"] == "w-1"
    assert payload["cloudTaskName"].endswith("/tasks/run-123")
    assert payload["logging.googleapis.com/trace"] == "projects/p/traces/t-1"
    assert payload["event"] == "synth_outcome"
    assert payload["reason"] == "MALFORMED_FUNCTION_CALL"


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
        turnIdx=1,
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
    # record which writes were attempted. Both single-doc (heartbeat-style)
    # and two-doc (terminal) writes flow through the same capture list so
    # the error assertions below don't care which primitive lands it.
    fenced_writes: list[dict] = []

    async def fake_fenced_update(sid, attempt, worker_id, updates):
        fenced_writes.append(updates)

    async def fake_fenced_update_session_and_turn(
        sid, turn_idx, attempt, worker_id, session_updates, turn_updates
    ):
        fenced_writes.append(session_updates)

    hb_cancel_calls = []

    async def fake_cancel_heartbeat():
        hb_cancel_calls.append(True)

    monkeypatch.setattr(worker_main, "_fenced_update", fake_fenced_update)
    monkeypatch.setattr(
        worker_main,
        "_fenced_update_session_and_turn",
        fake_fenced_update_session_and_turn,
    )
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
    # Error state written via (two-doc) fenced update.
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
    # what we assert. The terminal error path uses the two-doc primitive
    # — we record its session-side updates.
    calls: list[tuple] = []

    async def recording_cancel():
        calls.append(("cancel",))

    async def recording_fenced_update(sid, attempt, worker_id, updates):
        calls.append(("fenced", updates))

    async def recording_fenced_update_session_and_turn(
        sid, turn_idx, attempt, worker_id, session_updates, turn_updates
    ):
        calls.append(("fenced", session_updates))

    monkeypatch.setattr(worker_main, "_cancel_heartbeat", recording_cancel)
    monkeypatch.setattr(worker_main, "_fenced_update", recording_fenced_update)
    monkeypatch.setattr(
        worker_main,
        "_fenced_update_session_and_turn",
        recording_fenced_update_session_and_turn,
    )
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


def _empty_mapping() -> dict:
    return {
        "timeline_events": [],
        "complete": None,
        "grounding_sources": [],
        "milestones": {
            "context_started": False,
            "plan_ready_text": None,
            "research_started": False,
            "research_result_text": None,
            "drafting_started": False,
        },
    }


def _translate_emission(emission):
    """Bridge older worker tests onto the new `map_event` contract.

    Tests below mostly care about terminal writes and accumulated sources.
    They can keep describing those fixtures tersely while the harness feeds
    `run()` the mapper shape it now consumes.
    """
    if emission is None:
        return _empty_mapping()

    if isinstance(emission, dict) and (
        "timeline_events" in emission
        or "complete" in emission
        or "grounding_sources" in emission
        or "milestones" in emission
    ):
        base = _empty_mapping()
        base.update(emission)
        return base

    if not isinstance(emission, dict):
        raise TypeError(f"unsupported emission fixture: {emission!r}")

    base = _empty_mapping()
    event_type = emission.get("type")
    data = emission.get("data") or {}
    if event_type == "activity":
        base["grounding_sources"] = list(data.get("sources") or [])
        return base
    if event_type == "complete":
        base["complete"] = {
            "reply": data.get("reply"),
            "sources": list(data.get("sources") or []),
        }
        return base
    raise ValueError(f"unsupported legacy emission type: {event_type!r}")


def _install_run_harness(monkeypatch, *, events, emissions):
    """Wire up the module singletons + mocks for a `run` invocation.

    ``events`` is the sequence of ADK events yielded by `_runner.run_async`.
    ``emissions`` is a matching list of mapper outputs (or older shorthand
    fixtures translated by `_translate_emission`).
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

    emission_iter = iter(_translate_emission(emission) for emission in emissions)

    def fake_map_event(event, state=None):
        try:
            return next(emission_iter)
        except StopIteration:
            return _empty_mapping()

    monkeypatch.setattr(worker_main, "map_event", fake_map_event)

    async def fake_write_event_doc(**kwargs):
        return {
            "type": kwargs["event_type"],
            "data": kwargs["data"],
        }

    monkeypatch.setattr(worker_main, "write_event_doc", fake_write_event_doc)

    # Capture both single-doc (progress/heartbeat) and two-doc (terminal)
    # fenced writes in a single list. The existing tests assert on session-
    # level shape (e.g., status='complete', reply=...) — under server-stored
    # sessions the reply/sources/turnSummary live on the turn doc, so the
    # test harness surfaces the TURN-doc updates under the same dict keys
    # the old tests expected on the session. Session-only fields (status,
    # title, updatedAt) are merged in so tests that look at `title` and
    # `status` keep working without further rewrites.
    fenced_writes: list[dict] = []

    async def fake_fenced_update(sid, attempt, worker_id, updates):
        fenced_writes.append(updates)

    async def fake_fenced_update_session_and_turn(
        sid, turn_idx, attempt, worker_id, session_updates, turn_updates
    ):
        # Record a merged view so test assertions about `status`, `reply`,
        # `sources`, `turnSummary`, and `title` all find their data on one
        # entry. This preserves the old single-doc assertions while the
        # production path writes two docs atomically.
        merged = {**session_updates, **turn_updates}
        fenced_writes.append(merged)

    hb_cancel_calls: list[bool] = []

    async def fake_cancel_heartbeat():
        hb_cancel_calls.append(True)

    monkeypatch.setattr(worker_main, "_fenced_update", fake_fenced_update)
    monkeypatch.setattr(
        worker_main,
        "_fenced_update_session_and_turn",
        fake_fenced_update_session_and_turn,
    )
    monkeypatch.setattr(worker_main, "_cancel_heartbeat", fake_cancel_heartbeat)
    monkeypatch.setattr(worker_main, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0))
    # Avoid the Gemini Flash title call in tests; deterministic fake.
    async def _fake_title(_q: str) -> str:
        return "test"
    monkeypatch.setattr(worker_main, "_generate_title", _fake_title)

    return fenced_writes, hb_cancel_calls


@pytest.mark.asyncio
async def test_sources_accumulate_across_specialist_events(monkeypatch):
    """Specialist activity events' `data.sources` must merge into the
    terminal `sources[]` array emitted by the synthesiser. Sources come from
    the mapper's grounding extraction, not from markdown-parsing specialist
    text."""
    events = [
        _mk_event(
            {"market_result": "Market landscape analysis."},
            author="market_landscape",
        ),
        _mk_event(
            {"review_result": "Review sentiment analysis."},
            author="review_analyst",
        ),
        _mk_event(
            {"final_report": "Overall summary."},
            author="synthesizer",
        ),
    ]
    emissions = [
        {
            "type": "activity",
            "data": {
                "category": "analyze",
                "id": "analyze-market_landscape",
                "status": "complete",
                "label": "Market Landscape",
                "agent": "market_landscape",
                "sources": [{"title": "Source A", "url": "https://a.example"}],
            },
        },
        {
            "type": "activity",
            "data": {
                "category": "analyze",
                "id": "analyze-review_analyst",
                "status": "complete",
                "label": "Review Analysis",
                "agent": "review_analyst",
                "sources": [{"title": "Source B", "url": "https://b.example"}],
            },
        },
        {
            "type": "complete",
            "data": {
                "reply": "Overall summary.",
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
    # Synth's own sources + both specialists' accumulated sources.
    assert urls == {"https://a.example", "https://b.example", "https://c.example"}


@pytest.mark.asyncio
async def test_sources_dedupe_across_specialist_and_synth(monkeypatch):
    """Overlapping URLs between specialist activity events and the synthesiser's
    terminal event dedupe to one entry in the final `sources[]`."""
    events = [
        _mk_event({"market_result": "Market."}, author="market_landscape"),
        _mk_event({"final_report": "Summary."}, author="synthesizer"),
    ]
    emissions = [
        {
            "type": "activity",
            "data": {
                "status": "complete",
                "agent": "market_landscape",
                "sources": [{"title": "Shared", "url": "https://shared.example"}],
            },
        },
        {
            "type": "complete",
            "data": {
                "reply": "Summary.",
                "sources": [{"title": "Shared (dup)", "url": "https://shared.example"}],
            },
        },
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)
    await __import__("worker_main").run(_build_run_request(), _fake_request())

    complete = [u for u in fenced_writes if u.get("status") == "complete"][0]
    assert [s["url"] for s in complete["sources"]] == ["https://shared.example"]


@pytest.mark.asyncio
async def test_tool_sources_drain_into_terminal_sources(monkeypatch):
    """When tools write unique `_tool_src_<uuid>` state keys, the worker
    drain iterates every `_tool_src_*` key in each event's state_delta and
    accumulates the entries. Parallel tool calls batched into one event
    all survive (each has its own uuid key)."""
    events = [
        _mk_event(
            {
                "_tool_src_aaa": {"title": "TripAdvisor — Umami", "url": "https://ta.com/r/1", "domain": "tripadvisor.com"},
                "_tool_src_bbb": {"title": "Google Reviews — Umami", "url": "https://maps.example/1", "domain": "google.com"},
            },
            author="review_analyst",
        ),
        _mk_event({"final_report": "Review summary."}, author="synthesizer"),
    ]
    emissions = [
        None,  # tool-response event — mapper doesn't emit for it
        {"type": "complete", "data": {"reply": "Review summary.", "sources": []}},
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)
    await __import__("worker_main").run(_build_run_request(), _fake_request())

    complete = [u for u in fenced_writes if u.get("status") == "complete"][0]
    urls = {s["url"] for s in complete["sources"]}
    assert urls == {"https://ta.com/r/1", "https://maps.example/1"}


@pytest.mark.asyncio
async def test_tool_sources_do_not_leak_across_events(monkeypatch):
    """The worker drain operates on each event's state_delta, so entries
    only flow in when a tool wrote them in THAT event. Simulates a
    follow-up turn: no tool writes any `_tool_src_*` key in any event,
    so no provider entries appear in the terminal sources[]."""
    events = [
        _mk_event({"market_result": "follow-up analysis"}, author="market_landscape"),
        _mk_event({"final_report": "Follow-up reply."}, author="follow_up"),
    ]
    emissions = [
        {"type": "activity", "data": {"status": "complete", "agent": "market_landscape", "sources": []}},
        {"type": "complete", "data": {"reply": "Follow-up reply.", "sources": []}},
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)
    await __import__("worker_main").run(_build_run_request(), _fake_request())

    complete = [u for u in fenced_writes if u.get("status") == "complete"][0]
    assert complete["sources"] == []


@pytest.mark.asyncio
async def test_synth_callback_fallback_reply_lands_as_complete(monkeypatch):
    """Phase 3 collapse: the worker no longer stitches specialist outputs
    into a degraded reply on its own. The synth callback in agent.py
    (`_synth_fallback_callback`) is now the only fallback — when it fires
    for an error_code / empty / no-text response, it populates `final_report`
    with a report stitched from specialist state, the mapper emits a normal
    `complete` event, and the worker writes `status='complete'` with no
    special handling. This test exercises that path via a synth emission
    that looks like a normal complete (since the callback would have
    already produced the text)."""
    fallback_reply = (
        "# Research findings\n\n"
        "_Final synthesis didn't produce a response. Full research findings below._\n\n"
        "## Market Landscape\n\nMarket text.\n\n"
    )
    events = [_mk_event({"final_report": fallback_reply}, author="synthesizer")]
    emissions = [
        {"type": "complete", "data": {"reply": fallback_reply, "sources": []}},
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)
    result = await __import__("worker_main").run(_build_run_request(), _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"
    complete = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete) == 1
    assert complete[0]["reply"] == fallback_reply
    # No degraded_reply log event — worker-level stitching is gone.
    assert not any(u.get("status") == "error" for u in fenced_writes)


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
async def test_title_lands_in_same_fenced_write_as_terminal_status(monkeypatch):
    """First-message runs must bundle `title` into the `status='complete'`
    fenced write — not a follow-up write. A split write race-loses the title
    for the Firestore `onSnapshot` observer, which fires `onComplete` on the
    first terminal snapshot and unsubscribes before the title snapshot lands.
    """
    events = [_mk_event({}, author="router")]
    emissions = [
        {"type": "complete", "data": {"reply": "Hello back.", "sources": []}},
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    from worker_main import RunRequest
    body = RunRequest(
        sessionId="sid-1",
        runId="run-1",
        turnIdx=1,
        adkSessionId="adk-1",
        userId="alice",
        queryText="[Date: 2026-04-20] hello",
        isFirstMessage=True,
    )
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"

    complete_writes = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete_writes) == 1
    assert complete_writes[0]["title"] == "test"
    # No follow-up title-only write.
    assert not any("title" in u and "status" not in u for u in fenced_writes)


@pytest.mark.asyncio
async def test_title_task_failure_falls_back_and_completion_still_lands(monkeypatch):
    """If the background title task raises (cancellation, API error, etc.),
    the terminal write must still land with `_fallback_title(queryText)` — a
    failed title must not cost the user their answer. Guards the
    parallelisation: awaiting a failed task at the write site uses the
    deterministic fallback instead of propagating."""
    import worker_main as wm

    events = [_mk_event({}, author="router")]
    emissions = [
        {"type": "complete", "data": {"reply": "Hello back.", "sources": []}},
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    async def _failing_title(_q: str) -> str:
        raise RuntimeError("gemini flash unavailable")
    monkeypatch.setattr(wm, "_generate_title", _failing_title)

    from worker_main import RunRequest
    body = RunRequest(
        sessionId="sid-1",
        runId="run-1",
        turnIdx=1,
        adkSessionId="adk-1",
        userId="alice",
        queryText="[Date: 2026-04-20] What's going on at Noma?",
        isFirstMessage=True,
    )
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"

    complete_writes = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete_writes) == 1
    # Fallback strips the `[Date: …]` prefix and truncates to ≤40 chars.
    assert complete_writes[0]["title"] == wm._fallback_title(body.queryText)
    assert complete_writes[0]["reply"] == "Hello back."


@pytest.mark.asyncio
async def test_title_absent_when_not_first_message(monkeypatch):
    """Non-first-message runs must not carry a `title` field — title gen is
    scoped to the first turn of a conversation."""
    events = [_mk_event({}, author="router")]
    emissions = [
        {"type": "complete", "data": {"reply": "Follow-up.", "sources": []}},
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    body = _build_run_request()  # isFirstMessage=False
    result = await __import__("worker_main").run(body, _fake_request())

    assert result["ok"] is True
    complete_writes = [u for u in fenced_writes if u.get("status") == "complete"]
    assert len(complete_writes) == 1
    assert "title" not in complete_writes[0]


@pytest.mark.asyncio
async def test_note_tasks_are_cancelled_before_turn_summary_is_serialized(monkeypatch):
    import worker_main as wm

    events = [
        _mk_event({}, author="research_orchestrator"),
        _mk_event({"final_report": "Done."}, author="synthesizer"),
    ]
    emissions = [
        {
            "milestones": {
                "context_started": False,
                "plan_ready_text": "Validate pricing and venue signals.",
                "research_started": False,
                "research_result_text": None,
                "drafting_started": False,
            }
        },
        {
            "complete": {"reply": "Done.", "sources": []},
        },
    ]

    fenced_writes, _hb = _install_run_harness(monkeypatch, events=events, emissions=emissions)

    async def _slow_note(**_kwargs) -> str:
        await asyncio.sleep(10)
        return "This should never land."

    order: list[str] = []

    async def _record_cancel(tasks):
        order.append("cancel")
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _record_fenced_update(_sid, _attempt, _worker_id, updates):
        order.append(f"write:{updates.get('status', 'progress')}")
        fenced_writes.append(updates)

    async def _record_fenced_update_session_and_turn(
        _sid, _turn_idx, _attempt, _worker_id, session_updates, turn_updates
    ):
        merged = {**session_updates, **turn_updates}
        order.append(f"write:{merged.get('status', 'progress')}")
        fenced_writes.append(merged)

    monkeypatch.setattr(wm, "_generate_timeline_note", _slow_note)
    monkeypatch.setattr(wm, "_cancel_background_tasks", _record_cancel)
    monkeypatch.setattr(wm, "_fenced_update", _record_fenced_update)
    monkeypatch.setattr(
        wm,
        "_fenced_update_session_and_turn",
        _record_fenced_update_session_and_turn,
    )

    result = await wm.run(_build_run_request(), _fake_request())

    assert result["ok"] is True
    assert order.index("cancel") < order.index("write:complete")


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
        await worker_main._poll_until_resolved("sid-1", 1, "run-1", "w-1")
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


# ── Turn-doc lifecycle (plan §5 / §8 — server-stored sessions) ─────────────
#
# The tests above lean on the harness's merged-dict shortcut to assert
# terminal shape. The tests below pin down the split itself: session doc
# holds metadata (status, updatedAt, title on first turn), turn doc holds
# reply/sources/turnSummary/completedAt. Both writes land via
# `_fenced_update_session_and_turn`, i.e. inside a single transaction.


def _install_split_harness(monkeypatch, *, events, emissions):
    """Variant of `_install_run_harness` that keeps session- and turn-level
    terminal updates separate so tests can assert the data partition
    directly. Returns three lists: single-doc fenced writes (heartbeats /
    adkSessionId persistence), session-side terminal writes, turn-side
    terminal writes."""
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
    monkeypatch.setattr(
        worker_main, "_takeover_txn", lambda *a, **k: {"action": "run", "attempt": 1}
    )

    emission_iter = iter(_translate_emission(e) for e in emissions)

    def fake_map_event(event, state=None):
        try:
            return next(emission_iter)
        except StopIteration:
            return _empty_mapping()

    monkeypatch.setattr(worker_main, "map_event", fake_map_event)

    async def fake_write_event_doc(**kwargs):
        return {"type": kwargs["event_type"], "data": kwargs["data"]}

    monkeypatch.setattr(worker_main, "write_event_doc", fake_write_event_doc)

    progress_writes: list[dict] = []
    session_terminal_writes: list[dict] = []
    turn_terminal_writes: list[dict] = []
    turn_idx_captured: list[int] = []

    async def fake_fenced_update(_sid, _attempt, _worker_id, updates):
        progress_writes.append(updates)

    async def fake_fenced_update_session_and_turn(
        _sid, turn_idx, _attempt, _worker_id, session_updates, turn_updates
    ):
        turn_idx_captured.append(turn_idx)
        session_terminal_writes.append(session_updates)
        turn_terminal_writes.append(turn_updates)

    async def fake_cancel_heartbeat():
        pass

    monkeypatch.setattr(worker_main, "_fenced_update", fake_fenced_update)
    monkeypatch.setattr(
        worker_main,
        "_fenced_update_session_and_turn",
        fake_fenced_update_session_and_turn,
    )
    monkeypatch.setattr(worker_main, "_cancel_heartbeat", fake_cancel_heartbeat)
    monkeypatch.setattr(
        worker_main, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0)
    )

    async def _fake_title(_q: str) -> str:
        return "My Chat"

    monkeypatch.setattr(worker_main, "_generate_title", _fake_title)

    return progress_writes, session_terminal_writes, turn_terminal_writes, turn_idx_captured


@pytest.mark.asyncio
async def test_terminal_success_splits_content_to_turn_doc(monkeypatch):
    """Plan §5: session doc holds metadata (status, updatedAt, title on
    first turn); turn doc holds reply, sources, turnSummary, completedAt.
    The split lands via a single two-doc fenced transaction."""
    import worker_main as wm

    events = [_mk_event({"final_report": "The answer."}, author="synthesizer")]
    emissions = [
        {
            "type": "complete",
            "data": {
                "reply": "The answer.",
                "sources": [{"title": "Src", "url": "https://src.example"}],
            },
        }
    ]

    progress, session_writes, turn_writes, turn_idxs = _install_split_harness(
        monkeypatch, events=events, emissions=emissions
    )

    from worker_main import RunRequest

    body = RunRequest(
        sessionId="sid-1",
        runId="run-1",
        turnIdx=2,
        adkSessionId="adk-1",
        userId="alice",
        queryText="[Date: 2026-04-20] hello",
        isFirstMessage=False,  # not first → no title
    )
    result = await wm.run(body, _fake_request())

    assert result["ok"] is True
    assert result["action"] == "complete"

    # Exactly one terminal two-doc write.
    assert len(session_writes) == 1
    assert len(turn_writes) == 1
    assert turn_idxs == [2]

    # Session-side fields: status, updatedAt. No reply/sources/turnSummary.
    session_u = session_writes[0]
    assert session_u["status"] == "complete"
    assert "updatedAt" in session_u
    for field in ("reply", "sources", "turnSummary", "completedAt"):
        assert field not in session_u, (
            f"{field} must live on the turn doc, not the session doc"
        )
    # No title on follow-up turns.
    assert "title" not in session_u

    # Turn-side fields: status, reply, sources, turnSummary, completedAt.
    turn_u = turn_writes[0]
    assert turn_u["status"] == "complete"
    assert turn_u["reply"] == "The answer."
    assert [s["url"] for s in turn_u["sources"]] == ["https://src.example"]
    assert "turnSummary" in turn_u
    assert "completedAt" in turn_u


@pytest.mark.asyncio
async def test_terminal_success_on_first_turn_writes_title_to_session(monkeypatch):
    """First-turn completion adds `title` to the session-side update
    specifically — the sidebar reads `session.title` under the new schema.
    Title never lands on the turn doc."""
    import worker_main as wm

    events = [_mk_event({"final_report": "Answer."}, author="synthesizer")]
    emissions = [
        {"type": "complete", "data": {"reply": "Answer.", "sources": []}}
    ]

    _p, session_writes, turn_writes, _idxs = _install_split_harness(
        monkeypatch, events=events, emissions=emissions
    )

    from worker_main import RunRequest

    body = RunRequest(
        sessionId="sid-1",
        runId="run-1",
        turnIdx=1,
        adkSessionId="adk-1",
        userId="alice",
        queryText="hello",
        isFirstMessage=True,
    )
    await wm.run(body, _fake_request())

    assert session_writes[0]["title"] == "My Chat"
    assert "title" not in turn_writes[0]


@pytest.mark.asyncio
async def test_terminal_error_propagates_to_both_docs(monkeypatch):
    """Pipeline-error path writes `status='error'` to both session and turn
    docs in the same fenced transaction. Session gets `updatedAt` bump;
    both carry the error reason."""
    import worker_main as wm

    fake_runner = MagicMock()
    fake_runner.run_async = lambda **kwargs: _AsyncIterError(RuntimeError("boom"))

    fake_fs = MagicMock()
    fake_fs.collection.return_value.document.return_value = MagicMock()
    fake_fs.transaction.return_value = MagicMock()

    monkeypatch.setattr(wm, "_runner", fake_runner)
    monkeypatch.setattr(wm, "_fs", fake_fs)
    monkeypatch.setattr(wm, "_session_svc", MagicMock())
    monkeypatch.setattr(
        wm, "_takeover_txn", lambda *a, **k: {"action": "run", "attempt": 1}
    )

    session_writes: list[dict] = []
    turn_writes: list[dict] = []
    turn_idxs: list[int] = []

    async def fake_fenced_update(*_a, **_k):
        pass

    async def fake_fenced_update_session_and_turn(
        _sid, turn_idx, _attempt, _worker_id, session_updates, turn_updates
    ):
        turn_idxs.append(turn_idx)
        session_writes.append(session_updates)
        turn_writes.append(turn_updates)

    async def fake_cancel_heartbeat():
        pass

    monkeypatch.setattr(wm, "_fenced_update", fake_fenced_update)
    monkeypatch.setattr(
        wm, "_fenced_update_session_and_turn", fake_fenced_update_session_and_turn
    )
    monkeypatch.setattr(wm, "_cancel_heartbeat", fake_cancel_heartbeat)
    monkeypatch.setattr(wm, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0))

    body = _build_run_request()  # turnIdx=1
    result = await wm.run(body, _fake_request())

    assert result["ok"] is False
    assert result["action"] == "pipeline_error"

    assert len(session_writes) == 1
    assert len(turn_writes) == 1
    assert turn_idxs == [1]
    assert session_writes[0]["status"] == "error"
    assert "RuntimeError" in session_writes[0]["error"]
    assert "updatedAt" in session_writes[0]
    assert turn_writes[0]["status"] == "error"
    assert "RuntimeError" in turn_writes[0]["error"]


@pytest.mark.asyncio
async def test_sanity_fail_error_propagates_to_both_docs(monkeypatch):
    """Empty-reply sanity-fail path is a terminal error too — must flip
    both session and turn doc to status='error'."""
    import worker_main as wm

    events = [_mk_event({"places_context": "some place"})]
    emissions = [None]  # mapper emits nothing terminal

    _p, session_writes, turn_writes, turn_idxs = _install_split_harness(
        monkeypatch, events=events, emissions=emissions
    )

    body = _build_run_request()
    result = await wm.run(body, _fake_request())

    assert result["ok"] is False
    assert result["action"] == "empty_or_malformed_reply"
    assert len(session_writes) == 1
    assert len(turn_writes) == 1
    assert session_writes[0]["status"] == "error"
    assert session_writes[0]["error"] == "empty_or_malformed_reply"
    assert "updatedAt" in session_writes[0]
    assert turn_writes[0]["status"] == "error"
    assert turn_writes[0]["error"] == "empty_or_malformed_reply"


@pytest.mark.asyncio
async def test_creator_uid_flows_through_to_runner_call(monkeypatch):
    """Verify that `body.userId` (the creator UID populated by agentStream
    on every turn — even follow-ups from other visitors) is what reaches
    the ADK Runner. Under server-stored sessions `session.userId` is never
    overwritten; the submitter UID is tracked separately in
    `session.participants`.

    This is the load-bearing invariant behind
    `VertexAiSessionService.get_session`'s user_id equality check."""
    import worker_main as wm

    captured_user_ids: list[str] = []

    class _CapturingAsyncIter:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    def fake_run_async(**kwargs):
        captured_user_ids.append(kwargs.get("user_id"))
        return _CapturingAsyncIter()

    fake_runner = MagicMock()
    fake_runner.run_async = fake_run_async

    fake_fs = MagicMock()
    fake_fs.collection.return_value.document.return_value = MagicMock()
    fake_fs.transaction.return_value = MagicMock()

    monkeypatch.setattr(wm, "_runner", fake_runner)
    monkeypatch.setattr(wm, "_fs", fake_fs)
    monkeypatch.setattr(wm, "_session_svc", MagicMock())
    monkeypatch.setattr(
        wm, "_takeover_txn", lambda *a, **k: {"action": "run", "attempt": 1}
    )

    async def _noop_fenced(*_a, **_k):
        pass

    monkeypatch.setattr(wm, "_fenced_update", _noop_fenced)
    monkeypatch.setattr(wm, "_fenced_update_session_and_turn", _noop_fenced)

    async def fake_cancel_heartbeat():
        pass

    monkeypatch.setattr(wm, "_cancel_heartbeat", fake_cancel_heartbeat)
    monkeypatch.setattr(wm, "_heartbeat_loop", lambda *a, **k: asyncio.sleep(0))

    from worker_main import RunRequest

    # Simulate a follow-up submitted by visitor bob: agentStream reads the
    # session's stored creator UID (alice) and puts THAT into the task body.
    # So body.userId == "alice" even though the submitter was bob.
    body = RunRequest(
        sessionId="sid-1",
        runId="run-2",
        turnIdx=2,
        adkSessionId="adk-existing",
        userId="alice",  # creator UID from session.userId, per agentStream
        queryText="follow-up",
        isFirstMessage=False,
    )
    await wm.run(body, _fake_request())

    assert captured_user_ids == ["alice"]
