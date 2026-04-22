"""superextra-worker — FastAPI handler that runs one pipeline turn.

Receives a Cloud Tasks dispatch, runs the in-process ADK Runner end-to-end,
writes progress + completion to Firestore via Admin SDK. Idempotent via
atomic takeover + ownership fencing.

See `docs/pipeline-decoupling-plan.md` §Phase 3 for the full design. Short
version:

- Cloud Run IAM auth only — no in-handler token verification (only Cloud Tasks
  with OIDC can reach this service).
- Takeover transaction + stale-run guard prevents duplicate dispatches from
  colliding or clobbering a newer turn.
- Heartbeat asyncio task writes `lastHeartbeat` every 30 s via fenced update.
- Each event the ADK Runner emits → mapped to a Firestore doc + bumps
  `lastEventAt` (the second liveness signal the watchdog checks).
- Errors split three ways: ownership-lost / Firestore-transient → 500
  (Cloud Tasks retries); caught pipeline exceptions → 200 after writing
  `status=error` (no retry for deterministic bugs).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import firestore
from google.genai import Client as GenaiClient, types
from pydantic import BaseModel, Field

from superextra_agent.log_ctx import worker_sid as _worker_sid_ctx
from superextra_agent.agent import app as adk_app
from superextra_agent.firestore_events import (
    map_and_write_event,
)


# ── Structured logging ──────────────────────────────────────────────────────
#
# Cloud Logging auto-parses JSON written to stdout and keys log entries by the
# well-known fields below. Severity + message are standard; sid/runId/attempt/
# taskName/workerId are our own correlation keys (searchable via
# `jsonPayload.sid="..."`). `logging.googleapis.com/trace` enables trace
# correlation in the Cloud Logs explorer — Cloud Run injects
# `X-Cloud-Trace-Context` on every inbound request which we surface via an
# `extra={"trace": ...}` kwarg on the log call.


_STRUCTURED_LOG_KEYS = ("sid", "runId", "attempt", "cloudTaskName", "workerId", "event", "reason")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in _STRUCTURED_LOG_KEYS:
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        trace = getattr(record, "trace", None)
        if trace:
            # Cloud Logging-specific key — gets picked up and used to join log
            # entries to traces in the UI.
            payload["logging.googleapis.com/trace"] = trace
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    root = logging.getLogger()
    # Replace any prior handlers (`uvicorn` adds its own during lifespan).
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Let noisy libs log at WARN unless explicitly overridden.
    for name in ("httpx", "httpcore", "google.auth", "google.api_core"):
        logging.getLogger(name).setLevel(logging.WARNING)


_configure_logging()
log = logging.getLogger("superextra_worker")


def _trace_from_header(value: str | None) -> str | None:
    """Convert `X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=flag` → the
    fully-qualified trace resource name Cloud Logging expects."""
    if not value:
        return None
    trace_id = value.split("/", 1)[0]
    if not trace_id:
        return None
    return f"projects/{PROJECT}/traces/{trace_id}"

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "2746721333428617216")
TITLE_MODEL = os.environ.get("TITLE_MODEL", "gemini-2.5-flash")

# Tunables — all match plan §Design-decisions / §Phase 3.
HEARTBEAT_INTERVAL_S = 30
POLL_WAIT_MAX_S = 420  # 7 min — matches plan's active-owner poll ceiling
POLL_INTERVAL_S = 5
STALE_HEARTBEAT_S = 120  # 2 min — takeover threshold
TITLE_TIMEOUT_S = 5.0


# ── Module singletons, initialised in lifespan ─────────────────────────────

_session_svc: VertexAiSessionService | None = None
_runner: Runner | None = None
_fs: firestore.Client | None = None
_genai_client: GenaiClient | None = None
_heartbeat_task: asyncio.Task | None = None

# Tracks which run the *current request* owns, so the SIGTERM handler can
# invalidate its heartbeat without hunting through Firestore state.
_current_sid: str | None = None
_current_attempt: int | None = None
_current_worker_id: str | None = None


class RunRequest(BaseModel):
    sessionId: str
    runId: str
    # Optional: None on first turn — the worker creates the Agent Engine
    # session on first dispatch and writes the id back via fenced update so
    # follow-up turns reuse it.
    adkSessionId: str | None = None
    userId: str
    queryText: str
    isFirstMessage: bool = Field(default=False)
    placeContext: dict | None = None
    history: list | None = None


class OwnershipLost(Exception):
    """Raised when a fenced write detects another worker has taken over this
    run (currentAttempt or currentWorkerId no longer matches). The worker
    should bail cleanly; the other worker's writes are canonical."""


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _session_svc, _runner, _fs, _genai_client
    _session_svc = VertexAiSessionService(
        project=PROJECT, location=LOCATION, agent_engine_id=AGENT_ENGINE_ID
    )
    _runner = Runner(app=adk_app, session_service=_session_svc)
    _fs = firestore.Client(project=PROJECT)
    # Title generation uses a vanilla GenAI client (not through ADK) — route
    # to the global endpoint so flash 2.5 is available.
    _genai_client = GenaiClient(
        vertexai=True, project=PROJECT, location="global"
    )
    log.info(
        "worker ready",
        extra={
            "event": "worker_ready",
            "cloudTaskName": f"project={PROJECT} location={LOCATION} agent_engine={AGENT_ENGINE_ID}",
        },
    )
    yield


app = FastAPI(lifespan=_lifespan)


# ── Fenced update primitive ─────────────────────────────────────────────────


def _fenced_update_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    expected_attempt: int,
    expected_worker_id: str,
    updates: dict,
) -> None:
    """Pure logic — callable directly from tests. Production calls go through
    ``_fenced_update_txn`` which is ``firestore.transactional`` wrapped so
    Firestore handles contention retries."""
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if (
        data.get("currentAttempt") != expected_attempt
        or data.get("currentWorkerId") != expected_worker_id
    ):
        raise OwnershipLost()
    txn.update(session_ref, updates)


_fenced_update_txn = firestore.transactional(_fenced_update_logic)


async def _fenced_update(
    sid: str, attempt: int, worker_id: str, updates: dict
) -> None:
    assert _fs is not None
    ref = _fs.collection("sessions").document(sid)
    await asyncio.to_thread(
        _fenced_update_txn, _fs.transaction(), ref, attempt, worker_id, updates
    )


# ── Takeover + active-owner poll ────────────────────────────────────────────


def _takeover_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    payload_user_id: str,
    run_id: str,
    worker_id: str,
) -> dict:
    """Decide what this worker should do based on current session state.

    Returns one of:
        {"action": "run", "attempt": N}  — we took over, go run
        {"action": "poll"}               — another worker active with fresh HB
        {"action": "noop_complete"}      — terminal for THIS runId already
        {"action": "noop_stale"}         — session moved to a newer runId;
                                           we're a stale redelivery
    """
    snap = session_ref.get(transaction=txn)
    if not snap.exists:
        # agentStream (Phase 4) creates the doc before enqueuing. Missing doc
        # = payload bug → treat as fatal so Cloud Tasks retries surface it.
        raise HTTPException(status_code=500, detail="session doc missing")
    data = snap.to_dict() or {}

    # Defense-in-depth: agentStream already checked userId, but the worker
    # checks again in case of a payload mismatch.
    if data.get("userId") != payload_user_id:
        raise HTTPException(status_code=500, detail="userId mismatch — agentStream bug")

    status = data.get("status")
    current_run = data.get("currentRunId")
    last_hb = data.get("lastHeartbeat")

    # Stale-run guard (plan review finding #1): if the conversation has
    # advanced to a different runId while this dispatch sat in Cloud Tasks'
    # queue, the session has moved on. Do nothing — do NOT overwrite
    # currentRunId, status, or any per-turn fields.
    if current_run is not None and current_run != run_id:
        return {"action": "noop_stale"}

    if current_run == run_id and status in ("complete", "error"):
        return {"action": "noop_complete"}

    now = datetime.now(timezone.utc)
    hb_fresh = (
        last_hb is not None
        and (now - _aware(last_hb)).total_seconds() < STALE_HEARTBEAT_S
    )
    if status == "running" and current_run == run_id and hb_fresh:
        return {"action": "poll"}

    # Take over. We do NOT rewrite `currentRunId` here — the stale-run guard
    # above ensures `currentRunId == run_id` already when we reach this
    # branch (agentStream set it during enqueue).
    new_attempt = int(data.get("currentAttempt") or 0) + 1
    txn.update(session_ref, {
        "status": "running",
        "currentAttempt": new_attempt,
        "currentWorkerId": worker_id,
        "lastHeartbeat": firestore.SERVER_TIMESTAMP,
        "lastEventAt": firestore.SERVER_TIMESTAMP,
    })
    return {"action": "run", "attempt": new_attempt}


_takeover_txn = firestore.transactional(_takeover_logic)


async def _poll_until_resolved(sid: str, run_id: str, worker_id: str) -> dict:
    """Wait while another worker owns this run. Bail when:

    - status goes terminal (other worker finished or watchdog errored) → noop
    - currentRunId advances (session moved) → noop_stale
    - heartbeat goes stale → attempt takeover
    - 7-min ceiling → 500 (Cloud Tasks retries later)
    """
    assert _fs is not None
    ref = _fs.collection("sessions").document(sid)
    start = asyncio.get_event_loop().time()
    while True:
        await asyncio.sleep(POLL_INTERVAL_S)
        if (asyncio.get_event_loop().time() - start) > POLL_WAIT_MAX_S:
            raise HTTPException(
                status_code=500,
                detail="poll_timeout — active worker still running after 7 min",
            )
        snap = await asyncio.to_thread(ref.get)
        data = snap.to_dict() or {}
        current_run = data.get("currentRunId")
        status = data.get("status")
        if current_run is not None and current_run != run_id:
            return {"action": "noop_stale"}
        if status in ("complete", "error"):
            return {"action": "noop_complete"}
        last_hb = data.get("lastHeartbeat")
        if last_hb is None:
            continue
        age = (datetime.now(timezone.utc) - _aware(last_hb)).total_seconds()
        if age > STALE_HEARTBEAT_S:
            try:
                outcome = await asyncio.to_thread(
                    _takeover_txn,
                    _fs.transaction(),
                    ref,
                    data["userId"],
                    run_id,
                    worker_id,
                )
                return outcome
            except OwnershipLost:
                # Another worker beat us; keep polling.
                continue


def _aware(ts: Any) -> datetime:
    """Firestore timestamps come back as datetime, usually tz-aware already."""
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        return ts
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=timezone.utc)
    # Firestore sometimes returns google.protobuf.timestamp_pb2; its __repr__
    # is a datetime. Fall back to now() to avoid bad comparisons.
    return datetime.now(timezone.utc)


# ── Heartbeat task ──────────────────────────────────────────────────────────


async def _heartbeat_loop(sid: str, attempt: int, worker_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            try:
                await _fenced_update(
                    sid, attempt, worker_id,
                    {"lastHeartbeat": firestore.SERVER_TIMESTAMP},
                )
            except OwnershipLost:
                log.warning("heartbeat: ownership lost, stopping loop sid=%s", sid)
                return
            except Exception:  # noqa: BLE001
                # Transient Firestore blip — keep pulsing; retries + 500
                # behaviour come from the main request path.
                log.exception("heartbeat tick failed sid=%s", sid)
    except asyncio.CancelledError:
        pass


async def _cancel_heartbeat() -> None:
    """Cancel the heartbeat task BEFORE any terminal write so a late tick
    can't clobber `status=complete`/`error` with a fresh timestamp."""
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        try:
            await asyncio.wait_for(_heartbeat_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    _heartbeat_task = None


# ── Title generation (best-effort, first turn only) ─────────────────────────


_QUERY_CONTEXT_PREFIXES = ("[Date:", "[Context:")


def _strip_query_prefixes(text: str) -> str:
    """Remove agentStream-added [Date: ...] and [Context: ...] prefixes so the
    fallback title isn't just "[Date: 2026-04-20]"."""
    cleaned = text
    while True:
        cleaned = cleaned.lstrip()
        if not any(cleaned.startswith(p) for p in _QUERY_CONTEXT_PREFIXES):
            break
        end = cleaned.find("]")
        if end == -1:
            break
        cleaned = cleaned[end + 1:]
    return cleaned.strip()


def _fallback_title(query_text: str) -> str:
    cleaned = _strip_query_prefixes(query_text)
    if not cleaned:
        return "Untitled"
    return cleaned[:40] if len(cleaned) <= 40 else cleaned[:40].rsplit(" ", 1)[0]


async def _generate_title(query_text: str) -> str:
    """≤ TITLE_TIMEOUT_S call to Gemini Flash. Returns a short title or the
    deterministic fallback on any error / timeout."""
    assert _genai_client is not None
    cleaned_query = _strip_query_prefixes(query_text)
    prompt = (
        "Summarize this message into a short title, max 4 words.\n"
        "Rules:\n"
        "- Use the SAME LANGUAGE as the message\n"
        "- No markdown, no quotes, no punctuation, no numbering\n"
        "- Do not answer the question — just label the topic\n"
        "- Reply with ONLY the title, nothing else\n\n"
        f"Message: \"{cleaned_query}\""
    )
    try:
        async def _call() -> str | None:
            resp = await _genai_client.aio.models.generate_content(
                model=TITLE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            )
            text = getattr(resp, "text", None)
            if not text:
                return None
            # Strip common noise: quotes, markdown, leading numbering.
            raw = text.strip()
            raw = re.sub(r"^[\"'`]+|[\"'`]+$", "", raw)
            raw = re.sub(r"[*#_`~>\-]", "", raw)
            raw = re.sub(r"^\d+\.\s*", "", raw).strip()
            words = raw.split()
            if not words or len(words) > 8:
                return None
            return " ".join(words[:4])

        result = await asyncio.wait_for(_call(), timeout=TITLE_TIMEOUT_S)
        return result or _fallback_title(query_text)
    except Exception:  # noqa: BLE001
        log.warning("title generation failed, using deterministic fallback", exc_info=True)
        return _fallback_title(query_text)


# ── Source accumulator ──────────────────────────────────────────────────────


def _merge_source(sources: list[dict], seen: set[str], entry: dict) -> None:
    """Append ``entry`` to ``sources`` if its URL hasn't been seen yet.
    Mutates both in place. Used by the event-loop accumulator."""
    if not isinstance(entry, dict):
        return
    url = entry.get("url")
    if not url or url in seen:
        return
    seen.add(url)
    sources.append(entry)


# Last-resort stitching of specialist outputs when the synthesizer
# silently returns nothing and the agent.py empty-response guard did
# not fire. Mirrors `_build_fallback_report` in `superextra_agent.agent`
# but reads from the worker-accumulated state_delta dict, not an ADK
# callback_context. Returns empty string when no specialist produced
# usable output — caller falls through to status='error'.
_DEGRADED_SECTIONS: list[tuple[str, str]] = [
    ("market_result", "Market Landscape"),
    ("pricing_result", "Menu & Pricing"),
    ("revenue_result", "Revenue & Sales"),
    ("guest_result", "Guest Intelligence"),
    ("location_result", "Location & Traffic"),
    ("ops_result", "Operations"),
    ("marketing_result", "Marketing & Digital"),
    ("review_result", "Review Analysis"),
    ("dynamic_result_1", "Additional Research"),
    ("dynamic_result_2", "Gap Research"),
]


def _build_degraded_reply(accumulated_state: dict) -> str:
    parts: list[str] = [
        "# Research findings\n\n",
        "_Note: final synthesis did not produce a response. "
        "The detailed specialist findings below are the raw research "
        "captured before synthesis returned._\n\n",
    ]
    had_content = False
    for key, label in _DEGRADED_SECTIONS:
        val = accumulated_state.get(key)
        if not isinstance(val, str) or not val.strip() or val.strip() == "NOT_RELEVANT":
            continue
        had_content = True
        parts.append(f"## {label}\n\n{val}\n\n")
    return "".join(parts) if had_content else ""


# ── SIGTERM handler ─────────────────────────────────────────────────────────


def _sigterm_handler(_signum: int, _frame: Any) -> None:
    """Cloud Run sends SIGTERM with a fixed 10 s grace. We only null out the
    heartbeat so the next retry's takeover doesn't have to wait the full
    2-min stale window.

    Runs synchronously because the event loop may not be responsive at this
    point. Accepts the small risk of racing with a completed-by-another-worker
    heartbeat — retry + fence will sort it out.

    Reuses the module-level `_fs` client — `google-cloud-firestore` clients
    are documented thread-safe, so sharing with the event-loop's
    `to_thread`-dispatched Firestore calls serialises cleanly at the gRPC
    channel. A fresh client per SIGTERM would waste a chunk of the 10 s
    grace on channel setup.
    """
    if not (_current_sid and _current_attempt is not None and _current_worker_id):
        return
    log.warning("SIGTERM — invalidating heartbeat sid=%s", _current_sid)
    try:
        client = _fs if _fs is not None else firestore.Client(project=PROJECT)
        ref = client.collection("sessions").document(_current_sid)
        ref.update({"lastHeartbeat": None})
    except Exception:  # noqa: BLE001
        log.exception("SIGTERM heartbeat-null write failed")


signal.signal(signal.SIGTERM, _sigterm_handler)


# ── /run handler ────────────────────────────────────────────────────────────


@app.post("/run")
async def run(body: RunRequest, request: Request) -> dict:
    global _heartbeat_task, _current_sid, _current_attempt, _current_worker_id

    # Cloud Run IAM has already authenticated. No in-handler token check —
    # Cloud Tasks is the only principal with run.invoker on this service
    # (Phase 6 IAM).
    task_name = request.headers.get("x-cloudtasks-taskname", "unknown")
    retry_count = request.headers.get("x-cloudtasks-taskretrycount", "0")
    worker_id = str(uuid.uuid4())
    trace = _trace_from_header(request.headers.get("x-cloud-trace-context"))

    sid = body.sessionId
    run_id = body.runId
    # Thread sid through to logs emitted inside ADK callbacks (_embed_chart_images
    # synth_outcome events) so Phase 2 rate queries can filter load-test sids.
    _worker_sid_ctx.set(sid)
    assert _fs is not None
    session_ref = _fs.collection("sessions").document(sid)

    # Every downstream log benefits from the run-correlation keys; build a
    # dict once and spread it into `extra` at each call site.
    log_ctx = {
        "sid": sid,
        "runId": run_id,
        "cloudTaskName": task_name,
        "workerId": worker_id,
        **({"trace": trace} if trace else {}),
    }
    log.info(
        "run start",
        extra={
            **log_ctx,
            "event": "run_start",
            "attempt": int(retry_count or 0),
        },
    )

    # 1. Takeover (+ poll if another worker is actively running).
    try:
        outcome = await asyncio.to_thread(
            _takeover_txn,
            _fs.transaction(),
            session_ref,
            body.userId,
            run_id,
            worker_id,
        )
    except OwnershipLost:
        # Concurrent takeover race — let Cloud Tasks retry.
        raise HTTPException(status_code=500, detail="concurrent_takeover_race")

    if outcome["action"] == "noop_complete":
        log.info("noop_complete", extra={**log_ctx, "event": "noop_complete"})
        return {"ok": True, "action": "noop_complete"}

    if outcome["action"] == "noop_stale":
        log.info("noop_stale", extra={**log_ctx, "event": "noop_stale"})
        return {"ok": True, "action": "noop_stale"}

    if outcome["action"] == "poll":
        outcome = await _poll_until_resolved(sid, run_id, worker_id)
        if outcome["action"] == "noop_complete":
            return {"ok": True, "action": "noop_complete_after_poll"}
        if outcome["action"] == "noop_stale":
            return {"ok": True, "action": "noop_stale_after_poll"}

    attempt = int(outcome["attempt"])
    _current_sid, _current_attempt, _current_worker_id = sid, attempt, worker_id
    log_ctx["attempt"] = attempt

    # 2. Start the heartbeat pulse.
    _heartbeat_task = asyncio.create_task(_heartbeat_loop(sid, attempt, worker_id))

    # 2.1. Fire title gen in parallel with the pipeline — depends only on
    # queryText, so there's no reason to serialise it behind the pipeline.
    # Awaited at the terminal write; merged into the same fenced txn.
    title_task: "asyncio.Task[str] | None" = (
        asyncio.create_task(_generate_title(body.queryText))
        if body.isFirstMessage
        else None
    )

    # 2.5. Ensure an Agent Engine session exists. agentStream passes
    # `adkSessionId=null` on first turn — we create it here so the Cloud
    # Function stays out of the Agent Engine API surface. Follow-up turns
    # reuse the existing id (agentStream reads it from Firestore).
    adk_session_id = body.adkSessionId
    if not adk_session_id:
        assert _session_svc is not None
        created = await _session_svc.create_session(
            app_name=adk_app.name, user_id=body.userId
        )
        adk_session_id = created.id
        log.info(
            "created agent engine session",
            extra={
                **log_ctx,
                "event": "adk_session_created",
                "cloudTaskName": f"{log_ctx['cloudTaskName']} adk_session={adk_session_id}",
            },
        )
        # Persist the id so follow-up turns skip this step. Fenced so a
        # racing stale worker can't clobber with its own id.
        try:
            await _fenced_update(
                sid, attempt, worker_id, {"adkSessionId": adk_session_id}
            )
        except OwnershipLost:
            await _cancel_heartbeat()
            log.warning("ownership lost before adkSessionId write sid=%s", sid)
            raise HTTPException(status_code=500, detail="ownership_lost")

    # 3. Consume events from the in-process Runner.
    accumulated_state: dict[str, Any] = {}
    specialist_sources: list[dict] = []
    specialist_sources_seen: set[str] = set()
    final_reply: str | None = None
    final_sources: list[dict] = []
    seq_in_attempt = 0
    message = types.Content(role="user", parts=[types.Part(text=body.queryText)])
    assert _runner is not None
    try:
        async for event in _runner.run_async(
            user_id=body.userId,
            session_id=adk_session_id,
            new_message=message,
        ):
            seq_in_attempt += 1
            emitted = await map_and_write_event(
                fs=_fs, sid=sid, user_id=body.userId, run_id=run_id,
                attempt=attempt, seq_in_attempt=seq_in_attempt, event=event,
            )
            await _fenced_update(
                sid, attempt, worker_id,
                {"lastEventAt": firestore.SERVER_TIMESTAMP},
            )
            # Accumulate specialist/synth outputs across the loop. At terminal
            # time we need every specialist's output_key in one place to
            # harvest sources — per-event state_delta only carries the delta.
            sd = (event.actions.state_delta if event.actions else None) or {}
            for key, value in sd.items():
                if isinstance(value, str):
                    accumulated_state[key] = value
            # Accumulate sources from specialist (and gap researcher) completion
            # activity events. `_map_specialist` already extracts them from
            # grounding_metadata at emission time; we just carry the union
            # forward so the terminal reply can include every specialist's
            # sources, not only whatever the synth event carries.
            if emitted is not None and emitted.get("type") == "activity":
                data = emitted.get("data") or {}
                if data.get("status") == "complete":
                    for entry in data.get("sources") or []:
                        _merge_source(specialist_sources, specialist_sources_seen, entry)
            # Promote the first terminal `complete` event the mapper emits
            # (router clarification OR synthesiser final). Reuse the mapper's
            # decision as the source of truth for what counts as terminal —
            # avoids re-walking state_delta in two places.
            if (
                emitted is not None
                and emitted.get("type") == "complete"
                and final_reply is None
            ):
                data = emitted.get("data") or {}
                reply = data.get("reply")
                if isinstance(reply, str):
                    final_reply = reply
                    mapper_sources = data.get("sources") or []
                    # Dedup across mapper-extracted + specialist-accumulated.
                    seen: set[str] = set()
                    merged: list[dict] = []
                    for s in list(mapper_sources) + list(specialist_sources):
                        url = s.get("url") if isinstance(s, dict) else None
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        merged.append(s)
                    final_sources = merged

    except OwnershipLost:
        # Another worker fenced us out — their writes are canonical. Let
        # Cloud Tasks see a 500 so the retry can poll/takeover correctly.
        log.warning("ownership lost mid-run", extra={**log_ctx, "event": "ownership_lost"})
        raise HTTPException(status_code=500, detail="ownership_lost")

    except GoogleAPICallError as e:
        # Transient infrastructure error — don't write status=error, let
        # Cloud Tasks retry on a fresh attempt.
        log.exception(
            "google API error during pipeline",
            extra={**log_ctx, "event": "google_api_error"},
        )
        raise HTTPException(status_code=500, detail=f"google_api_error: {type(e).__name__}")

    except asyncio.CancelledError:
        # Runtime cancellation (Cloud Run shutdown, upstream disconnect).
        # The `finally` below best-effort-cancels the heartbeat before we
        # re-raise; no status write — we don't own the completion.
        raise

    except Exception as e:  # noqa: BLE001
        # Pipeline-layer exception (ADK runner, specialist, synthesiser).
        # Write status=error and return 200 — no retries for deterministic
        # bugs. The watchdog won't flag this (status is terminal).
        # Cancel heartbeat BEFORE the fenced error write so a late tick
        # can't clobber status=error with a fresh timestamp.
        await _cancel_heartbeat()
        err_msg = f"{type(e).__name__}: {str(e)[:500]}"
        log.exception("pipeline error", extra={**log_ctx, "event": "pipeline_error"})
        try:
            await _fenced_update(sid, attempt, worker_id, {
                "status": "error",
                "error": err_msg,
            })
        except OwnershipLost:
            log.warning("could not write error state; another worker owns sid=%s", sid)
        except Exception:  # noqa: BLE001
            log.exception("failed to write error state sid=%s", sid)
        return {"ok": False, "action": "pipeline_error", "error": err_msg}

    finally:
        # Idempotent — covers success, OwnershipLost/GoogleAPICallError
        # reraise, and CancelledError propagation. The Exception branch
        # above already cancels before its error write to preserve
        # cancel-order; running here afterwards is a safe no-op.
        await _cancel_heartbeat()

    # 4. Last-resort fallback: if we exited the loop with no final_reply
    # (synthesizer emitted a final event with no state_delta AND no parts AND
    # the agent.py empty-response guard didn't fire — vanishingly unlikely
    # but possible), synthesize a degraded reply from whatever specialist
    # outputs we accumulated. Prefer delivering usable content over
    # `status='error'`. See docs/pipeline-decoupling-implementation-review-
    # 2026-04-21.md P1.
    if not final_reply or not final_reply.strip():
        degraded = _build_degraded_reply(accumulated_state)
        if degraded:
            log.warning(
                "synthesizer produced no reply — delivering degraded reply from accumulated state",
                extra={**log_ctx, "event": "degraded_reply"},
            )
            final_reply = degraded
            final_sources = list(specialist_sources)

    # 5. Sanity check before declaring complete. Single stripped non-empty
    # check — `_map_synthesizer` / `_has_state_delta` only filter `if not
    # value`, so whitespace-only `final_report` would slip through without
    # `.strip()`. We dropped the old len<100 and `startswith("Error:")`
    # guards: the former false-rejected router clarifications; the latter
    # was ADK /run_sse synthetic-error legacy, moot via in-process Runner.

    if not final_reply or not final_reply.strip():
        reason = "empty_or_malformed_reply"
        log.warning(
            "reply sanity check failed",
            extra={**log_ctx, "event": "reply_sanity_failed"},
        )
        try:
            await _fenced_update(sid, attempt, worker_id, {
                "status": "error",
                "error": reason,
            })
        except OwnershipLost:
            pass
        return {"ok": False, "action": reason}

    # 5. Commit the terminal write. Title must land in the same fenced txn
    # as status/reply/sources — a split write races the client onSnapshot
    # observer, which unsubscribes on the first terminal snapshot (see
    # firestore-stream.ts:165-174). Fall back to the deterministic title
    # on task failure so a degraded title never costs the user their reply.
    terminal_update: dict = {
        "status": "complete",
        "reply": final_reply,
        "sources": final_sources,
    }
    if title_task is not None:
        try:
            terminal_update["title"] = await title_task
        except Exception:  # noqa: BLE001
            terminal_update["title"] = _fallback_title(body.queryText)

    try:
        await _fenced_update(sid, attempt, worker_id, terminal_update)
    except OwnershipLost:
        log.warning("ownership lost before final write sid=%s", sid)
        return {"ok": True, "action": "abandoned_before_complete"}

    log.info(
        "run complete",
        extra={**log_ctx, "event": "run_complete", "cloudTaskName": f"{log_ctx['cloudTaskName']} events={seq_in_attempt}"},
    )
    return {"ok": True, "action": "complete", "events": seq_in_attempt}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
