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
    extract_sources_from_grounding,
    map_event,
    write_event_doc,
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
NOTE_MODEL = os.environ.get("NOTE_MODEL", "gemini-2.5-flash")

# Tunables — all match plan §Design-decisions / §Phase 3.
HEARTBEAT_INTERVAL_S = 30
POLL_WAIT_MAX_S = 420  # 7 min — matches plan's active-owner poll ceiling
POLL_INTERVAL_S = 5
STALE_HEARTBEAT_S = 120  # 2 min — takeover threshold
TITLE_TIMEOUT_S = 5.0
NOTE_TIMEOUT_S = 8.0


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
    # Integer turn index allocated by agentStream (1-based). Worker formats
    # to the zero-padded `turns/{turnIdx:04d}` doc key only when addressing
    # the turn doc.
    turnIdx: int
    # Optional: None on first turn — the worker creates the Agent Engine
    # session on first dispatch and writes the id back via fenced update so
    # follow-up turns reuse it.
    adkSessionId: str | None = None
    # Creator UID — the session's stored `userId`. agentStream puts the
    # creator UID (not the submitter UID) in the task body so the worker
    # can address the Vertex Agent Engine session under stable ownership.
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


def _fenced_update_session_and_turn_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    turn_ref: firestore.DocumentReference,
    expected_attempt: int,
    expected_worker_id: str,
    session_updates: dict,
    turn_updates: dict,
) -> None:
    """Two-doc fenced write. Used for terminal session + turn transitions
    (complete / error) so session metadata and turn content update
    atomically. Single transactional-read on the session doc validates
    ownership before either write lands."""
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if (
        data.get("currentAttempt") != expected_attempt
        or data.get("currentWorkerId") != expected_worker_id
    ):
        raise OwnershipLost()
    txn.update(session_ref, session_updates)
    txn.update(turn_ref, turn_updates)


_fenced_update_session_and_turn_txn = firestore.transactional(
    _fenced_update_session_and_turn_logic
)


def _turn_doc_key(turn_idx: int) -> str:
    return f"{turn_idx:04d}"


async def _fenced_update_session_and_turn(
    sid: str,
    turn_idx: int,
    attempt: int,
    worker_id: str,
    session_updates: dict,
    turn_updates: dict,
) -> None:
    assert _fs is not None
    session_ref = _fs.collection("sessions").document(sid)
    turn_ref = session_ref.collection("turns").document(_turn_doc_key(turn_idx))
    await asyncio.to_thread(
        _fenced_update_session_and_turn_txn,
        _fs.transaction(),
        session_ref,
        turn_ref,
        attempt,
        worker_id,
        session_updates,
        turn_updates,
    )


# ── Takeover + active-owner poll ────────────────────────────────────────────


def _takeover_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    turn_ref: firestore.DocumentReference,
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

    On "run" the transaction ALSO marks `turn_ref.status='running'` so
    session and turn doc transition atomically. agentStream wrote the turn
    doc at `pending` when enqueuing; takeover is the single place that
    advances it to running.
    """
    snap = session_ref.get(transaction=txn)
    if not snap.exists:
        # agentStream (Phase 4) creates the doc before enqueuing. Missing doc
        # = payload bug → treat as fatal so Cloud Tasks retries surface it.
        raise HTTPException(status_code=500, detail="session doc missing")
    data = snap.to_dict() or {}

    # Defense-in-depth: agentStream already checked userId, but the worker
    # checks again in case of a payload mismatch. Under server-stored
    # sessions, agentStream puts `session.userId` (the stored creator UID)
    # into the task body — so submitter-vs-creator is invisible here; the
    # two sides must agree on the creator UID.
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
    txn.update(turn_ref, {"status": "running"})
    return {"action": "run", "attempt": new_attempt}


_takeover_txn = firestore.transactional(_takeover_logic)


async def _poll_until_resolved(
    sid: str, turn_idx: int, run_id: str, worker_id: str
) -> dict:
    """Wait while another worker owns this run. Bail when:

    - status goes terminal (other worker finished or watchdog errored) → noop
    - currentRunId advances (session moved) → noop_stale
    - heartbeat goes stale → attempt takeover
    - 7-min ceiling → 500 (Cloud Tasks retries later)
    """
    assert _fs is not None
    ref = _fs.collection("sessions").document(sid)
    turn_ref = ref.collection("turns").document(_turn_doc_key(turn_idx))
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
                    turn_ref,
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


# ── Timeline notes + summary ───────────────────────────────────────────────


def _notes_llm_disabled() -> bool:
    return os.environ.get("DISABLE_NOTE_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def _deterministic_note(milestone: str) -> str:
    return {
        "context_start": "I'm checking the venue and likely peer set before drafting the answer.",
        "plan_ready": "I'm narrowing the research path before validating the strongest signals.",
        "research_placeholder": "I'm validating the strongest signals across source and review coverage.",
        "research_result": "I'm comparing the strongest evidence across sources before drafting the answer.",
    }[milestone]


def _clean_note_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.strip().split())
    cleaned = re.sub(r"^[\"'`]+|[\"'`]+$", "", cleaned)
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned).strip()
    if not cleaned:
        return None
    if len(cleaned.split()) > 28:
        return None
    if "\n" in cleaned:
        return None
    return cleaned


async def _generate_timeline_note(*, milestone: str, query_text: str, input_text: str) -> str:
    if _notes_llm_disabled():
        return _deterministic_note(milestone)
    assert _genai_client is not None
    prompt = (
        "Write one short first-person research-progress update for a timeline.\n"
        "Rules:\n"
        "- One sentence only\n"
        "- Maximum 28 words\n"
        "- Use the SAME LANGUAGE as the user message\n"
        "- No markdown, no bullets, no quotes\n"
        "- No raw tool names or internal agent names\n"
        "- Do not promise work that has not started\n"
        "- Sound calm and concrete\n\n"
        f"User message:\n{_strip_query_prefixes(query_text)}\n\n"
        f"Milestone: {milestone}\n\n"
        f"Material to summarize:\n{input_text}"
    )
    try:
        async def _call() -> str:
            resp = await _genai_client.aio.models.generate_content(
                model=NOTE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    temperature=0,
                    candidate_count=1,
                ),
            )
            return _clean_note_text(getattr(resp, "text", None)) or _deterministic_note(milestone)

        return await asyncio.wait_for(_call(), timeout=NOTE_TIMEOUT_S)
    except Exception:  # noqa: BLE001
        log.warning("timeline note generation failed; using deterministic fallback", exc_info=True)
        return _deterministic_note(milestone)


def _iter_parts(event: Any) -> list[Any]:
    content = getattr(event, "content", None)
    return list(getattr(content, "parts", None) or [])


def _iter_function_calls(event: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for part in _iter_parts(event):
        fc = getattr(part, "function_call", None)
        if not fc or not getattr(fc, "name", None):
            continue
        args = getattr(fc, "args", None) or {}
        out.append((fc.name, args if isinstance(args, dict) else {}))
    return out


def _iter_function_responses(event: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for part in _iter_parts(event):
        fr = getattr(part, "function_response", None)
        if not fr or not getattr(fr, "name", None):
            continue
        response = getattr(fr, "response", None) or {}
        out.append((fr.name, response if isinstance(response, dict) else {}))
    return out


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _normalize_url(url: str) -> str:
    return url.strip()


class TurnSummaryBuilder:
    def __init__(self, *, started_at_ms: int):
        self.started_at_ms = started_at_ms
        self.web_queries: set[str] = set()
        self.sources: set[str] = set()
        self.venues: set[str] = set()
        self.platforms: set[str] = set()
        self.detail_dedupe: set[tuple[str, str, str]] = set()
        self.notes: list[dict[str, Any]] = []
        self.pending_plan_fallback: dict[str, Any] | None = None
        self.pending_research_fallback: dict[str, Any] | None = None
        self.context_note_emitted = False
        self.plan_note_emitted = False
        self.research_placeholder_emitted = False
        self.research_note_emitted = False
        self.drafting_emitted = False

    def observe_event(self, event: Any, state: dict[str, Any]) -> None:
        for name, args in _iter_function_calls(event):
            if name == "google_search":
                query = args.get("query")
                if isinstance(query, str) and query.strip():
                    self.web_queries.add(_normalize_query(query))
            elif name == "fetch_web_content":
                url = args.get("url")
                if isinstance(url, str) and url.strip():
                    self.sources.add(_normalize_url(url))
            elif name == "get_google_reviews":
                place_id = args.get("place_id")
                if isinstance(place_id, str) and place_id.strip():
                    self.venues.add(place_id.strip())
                    self.sources.add(_normalize_url(f"https://www.google.com/maps/place/?q=place_id:{place_id.strip()}"))
            elif name == "get_restaurant_details":
                place_id = args.get("place_id")
                if isinstance(place_id, str) and place_id.strip():
                    self.venues.add(place_id.strip())
            elif name == "get_batch_restaurant_details":
                place_ids = args.get("place_ids")
                if isinstance(place_ids, list):
                    for place_id in place_ids:
                        if isinstance(place_id, str) and place_id.strip():
                            self.venues.add(place_id.strip())

        for source in extract_sources_from_grounding(event):
            url = source.get("url")
            if isinstance(url, str) and url.strip():
                self.sources.add(_normalize_url(url))

        sd = (event.actions.state_delta if getattr(event, "actions", None) else None) or {}
        if isinstance(sd, dict):
            for key, value in sd.items():
                if key.startswith("_place_name_") and isinstance(value, str) and value.strip():
                    self.venues.add(value.strip().lower())

        for name, response in _iter_function_responses(event):
            status = str(response.get("status") or "").strip().lower()
            if name in ("search_restaurants", "find_nearby_restaurants") and status == "success":
                results = response.get("results")
                if isinstance(results, list):
                    for result in results:
                        if not isinstance(result, dict):
                            continue
                        rid = result.get("id")
                        if isinstance(rid, str) and rid.strip():
                            self.venues.add(rid.strip())
                        display_name = ((result.get("displayName") or {}) if isinstance(result.get("displayName"), dict) else {})
                        text = display_name.get("text")
                        if isinstance(text, str) and text.strip():
                            self.venues.add(text.strip().lower())
            elif name == "find_tripadvisor_restaurant":
                trip_link = response.get("tripadvisor_link")
                if isinstance(trip_link, str) and trip_link.strip():
                    self.sources.add(_normalize_url(trip_link))
                venue_name = response.get("name")
                if isinstance(venue_name, str) and venue_name.strip():
                    self.venues.add(venue_name.strip().lower())
            elif name == "get_restaurant_details" and status == "success":
                place = response.get("place")
                if isinstance(place, dict):
                    display_name = place.get("displayName")
                    if isinstance(display_name, dict):
                        text = display_name.get("text")
                        if isinstance(text, str) and text.strip():
                            self.venues.add(text.strip().lower())

    def accept_detail(self, event: dict[str, Any]) -> bool:
        key = (
            str(event.get("group") or ""),
            str(event.get("family") or ""),
            str(event.get("text") or ""),
        )
        if key in self.detail_dedupe:
            return False
        self.detail_dedupe.add(key)
        family = event.get("family")
        if isinstance(family, str) and family and family != "Warnings":
            self.platforms.add(family)
        return True

    def counts_snapshot(self) -> dict[str, int]:
        return {
            "webQueries": len(self.web_queries),
            "sources": len(self.sources),
            "venues": len(self.venues),
            "platforms": len(self.platforms),
        }

    def add_note(
        self,
        *,
        milestone: str,
        text: str,
        note_source: str,
        counts: dict[str, int] | None = None,
        live_only: bool = False,
    ) -> dict[str, Any] | None:
        if milestone == "context_start" and self.context_note_emitted:
            return None
        if milestone == "plan_ready" and self.plan_note_emitted:
            return None
        if milestone == "research_placeholder" and self.research_placeholder_emitted:
            return None
        if milestone == "research_result" and self.research_note_emitted:
            return None

        snapshot = counts or self.counts_snapshot()
        note = {
            "milestone": milestone,
            "text": text,
            "noteSource": note_source,
            "counts": snapshot,
            "liveOnly": live_only,
        }
        self.notes.append(note)
        if milestone == "context_start":
            self.context_note_emitted = True
        elif milestone == "plan_ready":
            self.plan_note_emitted = True
            self.pending_plan_fallback = None
        elif milestone == "research_placeholder":
            self.research_placeholder_emitted = True
        elif milestone == "research_result":
            self.research_note_emitted = True
            self.pending_research_fallback = None
        return {
            "kind": "note",
            "id": f"note:{milestone}:{len(self.notes)}",
            "text": text,
            "noteSource": note_source,
            "counts": snapshot,
        }

    def mark_drafting(self) -> bool:
        if self.drafting_emitted:
            return False
        self.drafting_emitted = True
        return True

    def finalize_notes(self) -> list[dict[str, Any]]:
        if self.pending_plan_fallback and not self.plan_note_emitted:
            fallback = self.pending_plan_fallback
            self.notes.append(
                {
                    "milestone": "plan_ready",
                    "text": fallback["text"],
                    "noteSource": "deterministic",
                    "counts": fallback["counts"],
                    "liveOnly": False,
                }
            )
            self.plan_note_emitted = True
        if self.pending_research_fallback and not self.research_note_emitted and not self.research_placeholder_emitted:
            fallback = self.pending_research_fallback
            self.notes.append(
                {
                    "milestone": "research_result",
                    "text": fallback["text"],
                    "noteSource": "deterministic",
                    "counts": fallback["counts"],
                    "liveOnly": False,
                }
            )
            self.research_note_emitted = True

        notes = list(self.notes)
        if self.research_note_emitted:
            notes = [n for n in notes if n["milestone"] != "research_placeholder" or not n.get("liveOnly")]
        kept = []
        for note in notes:
            kept.append(
                {
                    "text": note["text"],
                    "noteSource": note["noteSource"],
                    "counts": note["counts"],
                }
            )
        return kept[:4]

    def build_summary(self) -> dict[str, Any]:
        finished_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return {
            "startedAtMs": self.started_at_ms,
            "finishedAtMs": finished_at_ms,
            "elapsedMs": max(0, finished_at_ms - self.started_at_ms),
            "notes": self.finalize_notes(),
            "finalCounts": self.counts_snapshot(),
        }


class TimelineWriter:
    def __init__(
        self,
        *,
        fs: firestore.Client,
        sid: str,
        user_id: str,
        run_id: str,
        attempt: int,
    ):
        self._fs = fs
        self._sid = sid
        self._user_id = user_id
        self._run_id = run_id
        self._attempt = attempt
        self._seq_in_attempt = 0
        self._lock = asyncio.Lock()
        self.closed = False

    async def write_timeline(self, data: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            if self.closed:
                return None
            self._seq_in_attempt += 1
            return await write_event_doc(
                fs=self._fs,
                sid=self._sid,
                user_id=self._user_id,
                run_id=self._run_id,
                attempt=self._attempt,
                seq_in_attempt=self._seq_in_attempt,
                event_type="timeline",
                data=data,
            )

    async def close(self) -> None:
        async with self._lock:
            self.closed = True

    @property
    def seq_in_attempt(self) -> int:
        return self._seq_in_attempt


async def _emit_note_task(
    *,
    writer: TimelineWriter,
    builder: TurnSummaryBuilder,
    milestone: str,
    query_text: str,
    input_text: str,
    counts_snapshot: dict[str, int],
    live_only: bool = False,
) -> None:
    if writer.closed:
        return
    text = await _generate_timeline_note(
        milestone=milestone,
        query_text=query_text,
        input_text=input_text,
    )
    note = builder.add_note(
        milestone=milestone,
        text=text,
        note_source="llm" if not _notes_llm_disabled() and text != _deterministic_note(milestone) else "deterministic",
        counts=counts_snapshot,
        live_only=live_only,
    )
    if note is not None:
        await writer.write_timeline(note)


async def _cancel_background_tasks(tasks: list[asyncio.Task[Any]]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


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
    # Thread sid through to logs emitted inside ADK callbacks
    # (`_synth_fallback_callback` synth_outcome events) so rate queries can
    # filter load-test sids.
    _worker_sid_ctx.set(sid)
    assert _fs is not None
    session_ref = _fs.collection("sessions").document(sid)
    turn_idx = body.turnIdx
    turn_ref = session_ref.collection("turns").document(_turn_doc_key(turn_idx))

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
            turn_ref,
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
        outcome = await _poll_until_resolved(sid, turn_idx, run_id, worker_id)
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
    specialist_sources: list[dict] = []
    specialist_sources_seen: set[str] = set()
    final_reply: str | None = None
    final_sources: list[dict] = []
    mapping_state: dict[str, Any] = {"place_names": {}}
    timeline_builder = TurnSummaryBuilder(
        started_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000)
    )
    timeline_writer = TimelineWriter(
        fs=_fs,
        sid=sid,
        user_id=body.userId,
        run_id=run_id,
        attempt=attempt,
    )
    note_tasks: list[asyncio.Task[None]] = []
    message = types.Content(role="user", parts=[types.Part(text=body.queryText)])
    assert _runner is not None
    try:
        async for event in _runner.run_async(
            user_id=body.userId,
            session_id=adk_session_id,
            new_message=message,
        ):
            mapped = map_event(event, mapping_state)
            timeline_builder.observe_event(event, mapping_state)
            for timeline_event in mapped["timeline_events"]:
                kind = timeline_event.get("kind")
                if kind == "detail" and not timeline_builder.accept_detail(timeline_event):
                    continue
                if kind == "drafting" and not timeline_builder.mark_drafting():
                    continue
                await timeline_writer.write_timeline(timeline_event)
            await _fenced_update(
                sid, attempt, worker_id,
                {"lastEventAt": firestore.SERVER_TIMESTAMP},
            )
            for entry in mapped.get("grounding_sources") or []:
                _merge_source(specialist_sources, specialist_sources_seen, entry)
            # Also drain structured-tool sources written by review_analyst's
            # tools (TripAdvisor / Google Reviews) — grounding metadata
            # doesn't cover API-backed providers. Each tool call writes a
            # UNIQUE state key (`_tool_src_<uuid>`) so parallel tool calls
            # that ADK batches into one event's state_delta all survive
            # as distinct entries. Cross-turn leakage is impossible because
            # follow-up events don't write to stale keys, so they never
            # appear in the next event's state_delta.
            sd = (event.actions.state_delta if event.actions else None) or {}
            for key, value in sd.items():
                if key.startswith("_tool_src_"):
                    _merge_source(specialist_sources, specialist_sources_seen, value)

            milestones = mapped["milestones"]
            if milestones.get("context_started") and not timeline_builder.context_note_emitted:
                note = timeline_builder.add_note(
                    milestone="context_start",
                    text=_deterministic_note("context_start"),
                    note_source="deterministic",
                )
                if note is not None:
                    await timeline_writer.write_timeline(note)

            if milestones.get("plan_ready_text") and not timeline_builder.plan_note_emitted and timeline_builder.pending_plan_fallback is None:
                counts_snapshot = timeline_builder.counts_snapshot()
                timeline_builder.pending_plan_fallback = {
                    "text": _deterministic_note("plan_ready"),
                    "counts": counts_snapshot,
                }
                note_tasks.append(
                    asyncio.create_task(
                        _emit_note_task(
                            writer=timeline_writer,
                            builder=timeline_builder,
                            milestone="plan_ready",
                            query_text=body.queryText,
                            input_text=str(milestones["plan_ready_text"])[:1500],
                            counts_snapshot=counts_snapshot,
                        )
                    )
                )

            if milestones.get("research_started") and not timeline_builder.research_placeholder_emitted:
                note = timeline_builder.add_note(
                    milestone="research_placeholder",
                    text=_deterministic_note("research_placeholder"),
                    note_source="deterministic",
                    live_only=True,
                )
                if note is not None:
                    await timeline_writer.write_timeline(note)

            if milestones.get("research_result_text") and not timeline_builder.research_note_emitted and timeline_builder.pending_research_fallback is None:
                counts_snapshot = timeline_builder.counts_snapshot()
                timeline_builder.pending_research_fallback = {
                    "text": _deterministic_note("research_result"),
                    "counts": counts_snapshot,
                }
                note_tasks.append(
                    asyncio.create_task(
                        _emit_note_task(
                            writer=timeline_writer,
                            builder=timeline_builder,
                            milestone="research_result",
                            query_text=body.queryText,
                            input_text=str(milestones["research_result_text"])[:1500],
                            counts_snapshot=counts_snapshot,
                        )
                    )
                )

            if mapped.get("complete") is not None and final_reply is None:
                data = mapped["complete"]
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
        await timeline_writer.close()
        await _cancel_background_tasks(note_tasks)
        log.warning("ownership lost mid-run", extra={**log_ctx, "event": "ownership_lost"})
        raise HTTPException(status_code=500, detail="ownership_lost")

    except GoogleAPICallError as e:
        # Transient infrastructure error — don't write status=error, let
        # Cloud Tasks retry on a fresh attempt.
        await timeline_writer.close()
        await _cancel_background_tasks(note_tasks)
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
        await timeline_writer.close()
        await _cancel_background_tasks(note_tasks)
        err_msg = f"{type(e).__name__}: {str(e)[:500]}"
        log.exception("pipeline error", extra={**log_ctx, "event": "pipeline_error"})
        try:
            await _fenced_update_session_and_turn(
                sid,
                turn_idx,
                attempt,
                worker_id,
                {
                    "status": "error",
                    "error": err_msg,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                {"status": "error", "error": err_msg},
            )
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

    # 4. Sanity check before declaring complete. Single stripped non-empty
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
            await _fenced_update_session_and_turn(
                sid,
                turn_idx,
                attempt,
                worker_id,
                {
                    "status": "error",
                    "error": reason,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                {"status": "error", "error": reason},
            )
        except OwnershipLost:
            pass
        return {"ok": False, "action": reason}

    # 5. Commit the terminal write. `_synth_fallback_callback` in agent.py
    # guarantees `final_report` is populated whenever the model call returns
    # (error_code, empty content, or no text all produce a text-only fallback
    # from specialist state), so the worker no longer needs its own degraded-
    # reply stitching layer. The sanity gate above catches the one residual
    # case: no `complete` event ever emitted at all.
    #
    # Under server-stored sessions (plan §5) the session doc holds only
    # metadata + operational state; reply/sources/turnSummary live on the
    # per-turn doc. The session+turn pair is updated in a single fenced
    # transaction so the two can't disagree for more than a Firestore commit
    # window. Title still lands on the session doc (first turn only) because
    # the sidebar listener reads it from there.
    await timeline_writer.close()
    await _cancel_background_tasks(note_tasks)

    session_terminal_update: dict = {
        "status": "complete",
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if title_task is not None:
        try:
            session_terminal_update["title"] = await title_task
        except Exception:  # noqa: BLE001
            session_terminal_update["title"] = _fallback_title(body.queryText)

    turn_terminal_update: dict = {
        "status": "complete",
        "reply": final_reply,
        "sources": final_sources,
        "turnSummary": timeline_builder.build_summary(),
        "completedAt": firestore.SERVER_TIMESTAMP,
    }

    try:
        await _fenced_update_session_and_turn(
            sid,
            turn_idx,
            attempt,
            worker_id,
            session_terminal_update,
            turn_terminal_update,
        )
    except OwnershipLost:
        log.warning("ownership lost before final write sid=%s", sid)
        return {"ok": True, "action": "abandoned_before_complete"}

    log.info(
        "run complete",
        extra={**log_ctx, "event": "run_complete", "cloudTaskName": f"{log_ctx['cloudTaskName']} events={timeline_writer.seq_in_attempt}"},
    )
    return {"ok": True, "action": "complete", "events": timeline_writer.seq_in_attempt}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
