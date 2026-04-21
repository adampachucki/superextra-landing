"""Reference skeleton for Phase 3's superextra-worker FastAPI handler.

NOT production — this is scaffolding that shows how the pieces in the plan fit
together (atomic takeover + fenced writes + heartbeat task + event loop +
SIGTERM handler). TODO markers indicate where implementation-specific logic
goes. Copy to `agent/worker_main.py` during Phase 3 and fill in the TODOs.

Verified against ADK 1.28 (see spikes/adk_runner_spike.py).

Related docs:
  docs/pipeline-decoupling-plan.md#phase-3
  docs/pipeline-decoupling-spike-results.md#b-event-taxonomy
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.cloud import firestore
from google.genai import types
from pydantic import BaseModel

# Resolve package path for imports — mirror current CLAUDE.md PYTHONPATH=. setup
from superextra_agent.agent import app as adk_app  # noqa: E402
from superextra_agent.firestore_events import map_and_write_event  # noqa: E402

log = logging.getLogger("superextra_worker")
logging.basicConfig(level=logging.INFO)

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_ENGINE_ID = os.environ["AGENT_ENGINE_ID"]  # "2746721333428617216"

# Tunables (all from plan §Design-decisions + spike verdicts)
HEARTBEAT_INTERVAL_S = 30
POLL_WAIT_MAX_S = 420  # 7 min — matches plan's active-owner poll ceiling
POLL_INTERVAL_S = 5
STALE_HEARTBEAT_S = 120  # 2 min — takeover threshold

# Event-driven "did-something-happen" signal, distinct from liveness heartbeat.
# See spike-results doc's B.4 for why we track both.
# ──────────────────────────────────────────────────────────────────────────
_session_svc: VertexAiSessionService | None = None
_runner: Runner | None = None
_fs: firestore.Client | None = None
_heartbeat_task: asyncio.Task | None = None


class RunRequest(BaseModel):
    sessionId: str
    runId: str
    adkSessionId: str
    userId: str
    queryText: str
    isFirstMessage: bool = False
    placeContext: dict | None = None
    history: list | None = None


class OwnershipLost(Exception):
    """Raised when a fenced write detects another worker took over this run."""


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _session_svc, _runner, _fs
    _session_svc = VertexAiSessionService(
        project=PROJECT, location=LOCATION, agent_engine_id=AGENT_ENGINE_ID
    )
    _runner = Runner(app=adk_app, session_service=_session_svc)
    _fs = firestore.Client(project=PROJECT)
    yield


app = FastAPI(lifespan=_lifespan)


# ── Fenced write helper ─────────────────────────────────────────────────────

@firestore.transactional
def _fenced_update_txn(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    expected_attempt: int,
    expected_worker_id: str,
    updates: dict,
) -> None:
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if data.get("currentAttempt") != expected_attempt or data.get("currentWorkerId") != expected_worker_id:
        raise OwnershipLost()
    txn.update(session_ref, updates)


async def _fenced_update(
    sid: str, attempt: int, worker_id: str, updates: dict
) -> None:
    ref = _fs.collection("sessions").document(sid)
    # firestore transactions are sync — offload to thread
    await asyncio.to_thread(_fenced_update_txn, _fs.transaction(), ref, attempt, worker_id, updates)


# ── Takeover + poll ─────────────────────────────────────────────────────────

@firestore.transactional
def _takeover_txn(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    payload_user_id: str,
    run_id: str,
    worker_id: str,
) -> dict:
    """Returns a dict describing the outcome:
      {"action": "run", "attempt": N}  — we took over, start running
      {"action": "poll"}               — another worker active with fresh heartbeat
      {"action": "noop_complete"}      — already complete/error for THIS runId
      {"action": "noop_stale"}         — session has moved to a different (newer) runId; we're a stale redelivery
    """
    snap = session_ref.get(transaction=txn)
    if not snap.exists:
        # agentStream should have created this; reject as a payload error
        raise HTTPException(500, "session doc missing")
    data = snap.to_dict() or {}

    # Defense-in-depth ownership check (plan Phase 3 step 2)
    if data.get("userId") != payload_user_id:
        raise HTTPException(500, "userId mismatch — agentStream bug")

    status = data.get("status")
    current_run = data.get("currentRunId")
    last_hb = data.get("lastHeartbeat")

    # Stale-run guard — critical for preventing an old Cloud Tasks redelivery
    # from clobbering a newer turn's session state. If session's currentRunId
    # differs from this task's runId, the conversation has moved on (user sent
    # a follow-up turn). This worker is a stale redelivery; no-op and let
    # Cloud Tasks mark the task done. See review finding #1.
    if current_run is not None and current_run != run_id:
        return {"action": "noop_stale"}

    if current_run == run_id and status in ("complete", "error"):
        return {"action": "noop_complete"}

    now = datetime.now(timezone.utc)
    hb_fresh = (
        last_hb is not None
        and (now - last_hb.replace(tzinfo=timezone.utc)).total_seconds() < STALE_HEARTBEAT_S
    )
    if status == "running" and current_run == run_id and hb_fresh:
        return {"action": "poll"}

    new_attempt = (data.get("currentAttempt") or 0) + 1
    txn.update(session_ref, {
        "status": "running",
        "currentRunId": run_id,
        "currentAttempt": new_attempt,
        "currentWorkerId": worker_id,
        "lastHeartbeat": firestore.SERVER_TIMESTAMP,
        "lastEventAt": firestore.SERVER_TIMESTAMP,
    })
    return {"action": "run", "attempt": new_attempt}


async def _poll_until_resolved(sid: str, run_id: str, worker_id: str) -> dict:
    """Poll until: status terminal, heartbeat stale (take over), session moves to a newer
    runId (stale redelivery), or ceiling hit."""
    ref = _fs.collection("sessions").document(sid)
    start = asyncio.get_event_loop().time()
    while True:
        await asyncio.sleep(POLL_INTERVAL_S)
        if (asyncio.get_event_loop().time() - start) > POLL_WAIT_MAX_S:
            # Escape hatch — let Cloud Tasks retry later
            raise HTTPException(500, "poll_timeout — active worker still running after 7 min")
        snap = await asyncio.to_thread(ref.get)
        data = snap.to_dict() or {}
        current_run = data.get("currentRunId")
        status = data.get("status")
        # Session has moved to a different runId while we were polling — we're stale, bail.
        if current_run is not None and current_run != run_id:
            return {"action": "noop_stale"}
        if status in ("complete", "error"):
            return {"action": "noop_complete"}
        last_hb = data.get("lastHeartbeat")
        if last_hb is None:
            continue
        age = (datetime.now(timezone.utc) - last_hb.replace(tzinfo=timezone.utc)).total_seconds()
        if age > STALE_HEARTBEAT_S:
            # Original worker died — take over
            try:
                outcome = await asyncio.to_thread(
                    _takeover_txn, _fs.transaction(), ref, data["userId"], run_id, worker_id,
                )
                return outcome
            except OwnershipLost:
                # Someone else got there first — keep polling
                continue


# ── Heartbeat asyncio task ──────────────────────────────────────────────────

async def _heartbeat_loop(sid: str, attempt: int, worker_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            try:
                await _fenced_update(sid, attempt, worker_id, {
                    "lastHeartbeat": firestore.SERVER_TIMESTAMP,
                })
            except OwnershipLost:
                log.warning("heartbeat: ownership lost, stopping loop sid=%s", sid)
                return
    except asyncio.CancelledError:
        pass


async def _cancel_heartbeat() -> None:
    """Safely cancel the heartbeat task with a 1 s grace for its final txn."""
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        try:
            await asyncio.wait_for(_heartbeat_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    _heartbeat_task = None


# ── SIGTERM handler ─────────────────────────────────────────────────────────
# 10 s fixed grace on Cloud Run; do minimal work. See spike-results I for why
# this is only needed for scale-down (not deploy rollouts).

_current_sid: str | None = None
_current_attempt: int | None = None
_current_worker_id: str | None = None


def _sigterm_handler(_signum, _frame) -> None:
    log.warning("SIGTERM received — invalidating heartbeat")
    if not (_current_sid and _current_attempt and _current_worker_id):
        return
    # Run the null-heartbeat write synchronously via a scratch sync client — we
    # can't rely on the event loop being responsive.
    try:
        client = firestore.Client(project=PROJECT)
        ref = client.collection("sessions").document(_current_sid)
        # Not fenced here — SIGTERM is "something catastrophic is happening"
        # and we want retry to take over unambiguously. Accept small risk of
        # overwriting a completed-by-another-worker heartbeat.
        ref.update({"lastHeartbeat": None})
    except Exception:  # noqa: BLE001
        log.exception("SIGTERM heartbeat-null write failed")


signal.signal(signal.SIGTERM, _sigterm_handler)


# ── Main handler ────────────────────────────────────────────────────────────

@app.post("/run")
async def run(body: RunRequest, request: Request) -> dict:
    global _heartbeat_task, _current_sid, _current_attempt, _current_worker_id

    # Cloud Run IAM has already authenticated — no in-handler token verification
    # (see plan Phase 3 step 1 + spike C). Pull task metadata for logging.
    task_name = request.headers.get("x-cloudtasks-taskname", "unknown")
    retry_count = request.headers.get("x-cloudtasks-taskretrycount", "0")
    worker_id = str(uuid.uuid4())

    sid = body.sessionId
    run_id = body.runId
    session_ref = _fs.collection("sessions").document(sid)

    log.info("run: sid=%s runId=%s task=%s retry=%s worker=%s",
             sid, run_id, task_name, retry_count, worker_id)

    # 1. Takeover transaction
    try:
        outcome = await asyncio.to_thread(
            _takeover_txn, _fs.transaction(), session_ref, body.userId, run_id, worker_id,
        )
    except OwnershipLost:
        # Rare: concurrent takeover race — defer to Cloud Tasks retry
        raise HTTPException(500, "concurrent_takeover_race")

    if outcome["action"] == "noop_complete":
        return {"ok": True, "action": "noop"}

    if outcome["action"] == "noop_stale":
        log.info("noop_stale: session has moved to a newer runId sid=%s stale_run=%s", sid, run_id)
        return {"ok": True, "action": "noop_stale"}

    if outcome["action"] == "poll":
        outcome = await _poll_until_resolved(sid, run_id, worker_id)
        if outcome["action"] == "noop_complete":
            return {"ok": True, "action": "noop_after_poll"}
        if outcome["action"] == "noop_stale":
            return {"ok": True, "action": "noop_stale_after_poll"}

    attempt = outcome["attempt"]
    _current_sid, _current_attempt, _current_worker_id = sid, attempt, worker_id

    # 2. Start heartbeat task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop(sid, attempt, worker_id))

    # 3. Run ADK pipeline via in-process Runner
    message = types.Content(role="user", parts=[types.Part(text=body.queryText)])
    seq_in_attempt = 0
    final_reply: str | None = None
    final_sources: list[dict] = []
    try:
        async for event in _runner.run_async(
            user_id=body.userId, session_id=body.adkSessionId, new_message=message
        ):
            seq_in_attempt += 1
            # Map + write the event in a single call. mapper decides what (if
            # anything) to emit to Firestore. See Phase 2 / firestore_events.py.
            await map_and_write_event(
                fs=_fs, sid=sid, user_id=body.userId, run_id=run_id,
                attempt=attempt, seq_in_attempt=seq_in_attempt, event=event,
            )
            # Bump lastEventAt — the "progress beat" that watchdog uses to
            # detect wedged-but-alive pipelines (spike-results B.4).
            try:
                await _fenced_update(sid, attempt, worker_id, {
                    "lastEventAt": firestore.SERVER_TIMESTAMP,
                })
            except OwnershipLost:
                log.warning("ownership lost mid-run sid=%s", sid)
                return {"ok": True, "action": "abandoned"}

            # Capture final_report when it lands in state_delta (plan Phase 3 step 7)
            if event.actions and event.actions.state_delta:
                sd = event.actions.state_delta
                if "final_report" in sd:
                    final_reply = sd["final_report"]
                    # TODO: extract sources from specialist result text
                    # (use helper from firestore_events.py)

    except Exception as e:  # noqa: BLE001
        # Cancel heartbeat BEFORE terminal write (plan Phase 3 step 3 cancel-order)
        await _cancel_heartbeat()
        try:
            await _fenced_update(sid, attempt, worker_id, {
                "status": "error", "error": f"{type(e).__name__}: {e}",
            })
        except OwnershipLost:
            pass
        # Return 500 so Cloud Tasks retries on transient infra errors.
        # TODO: distinguish transient vs terminal; for terminal (deterministic
        # bugs), return 200 so no retry cycles through the same failure.
        raise HTTPException(500, "pipeline_failed")

    # 4. Cancel heartbeat, then sanity check + final write
    await _cancel_heartbeat()

    # Reply sanity check (plan Phase 3 step 7)
    if not final_reply or len(final_reply) < 100 or final_reply.startswith("Error:"):
        try:
            await _fenced_update(sid, attempt, worker_id, {
                "status": "error",
                "error": "empty_or_malformed_reply",
            })
        except OwnershipLost:
            pass
        return {"ok": False, "reason": "sanity_check_failed"}

    # Terminal write FIRST — don't delay completion behind title generation.
    try:
        await _fenced_update(sid, attempt, worker_id, {
            "status": "complete",
            "reply": final_reply,
            "sources": final_sources,
        })
    except OwnershipLost:
        log.warning("ownership lost before final write sid=%s", sid)
        return {"ok": True, "action": "abandoned"}

    # Best-effort title (first message only). Never blocks completion — terminal
    # status was already written above.
    if body.isFirstMessage:
        title: str | None = None
        try:
            # TODO: _generate_title should wrap a Gemini 2.5 Flash call in a
            # short timeout (~5s) and return str | None.
            # title = await asyncio.wait_for(_generate_title(body.queryText), timeout=5.0)
            pass
        except Exception:  # noqa: BLE001
            title = None
        if not title:
            # Deterministic fallback: strip [Date:]/[Context:] prefixes, take first 40 chars
            cleaned = body.queryText
            for prefix in ("[Date:", "[Context:"):
                while cleaned.startswith(prefix):
                    end = cleaned.find("] ")
                    cleaned = cleaned[end + 2:] if end != -1 else cleaned[len(prefix):]
            title = cleaned.strip()[:40] or "Untitled"
        try:
            await _fenced_update(sid, attempt, worker_id, {"title": title})
        except OwnershipLost:
            pass  # Completion write already landed; losing title here is OK.

    return {"ok": True, "action": "complete"}


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
