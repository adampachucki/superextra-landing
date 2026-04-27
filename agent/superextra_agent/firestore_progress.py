"""`FirestoreProgressPlugin` — runs inside Vertex AI Agent Engine.

Replaces the legacy Cloud Run worker (`worker_main.py`). For each
root-runner invocation:

  - **before_run**: builds a ``GearRunState``, claims the run via fenced
    Firestore transaction (``status='queued' → 'running'``), spawns a
    30 s heartbeat, optionally spawns a title task on the first turn.
  - **on_event**: feeds each ADK event through ``GearRunState.observe_event``,
    writes resulting timeline events + bumps ``lastEventAt`` (best-effort).
  - **after_run**: cancels heartbeat first, drains note tasks, builds the
    terminal payload, writes session+turn atomically with a bounded retry.

Three classes of write, three error semantics (plan §"Write-class taxonomy"):

  - **Critical** (claim, terminal): retried on transient Firestore errors;
    OwnershipLost surfaces immediately.
  - **Heartbeat**: no inner retry — the 30 s tick interval IS the retry,
    matching ``worker_main.py:438-449``.
  - **Best-effort** (timeline events, lastEventAt bumps): swallowed,
    logged; never halt the run.

Plugin granularity (plan §4.2.2): production agents use
``SequentialAgent``/``ParallelAgent`` composition, NOT ``AgentTool``. ADK
fires plugin run-level callbacks once per root-runner invocation, so
``claim_invocation`` runs ONCE per turn and the heartbeat lives for the
full 7–15 min pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, Optional

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.plugins.base_plugin import BasePlugin
from google.api_core.exceptions import DeadlineExceeded, GoogleAPICallError, RetryError
from google.cloud import firestore
from google.genai import types
from typing_extensions import override

from .gear_run_state import GearRunState
from .notes import _generate_title

log = logging.getLogger(__name__)


class OwnershipLost(Exception):
    """A fenced write detected the session has moved on (currentRunId
    diverged, or status no longer 'running'/'queued'). The caller should
    bail without retry — definitive ownership signal, not transient.
    """


# ── Fenced Firestore writes ──────────────────────────────────────────────────


def _claim_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    turn_ref: firestore.DocumentReference,
    expected_run_id: str,
) -> None:
    """Predicates: session ``currentRunId == expected_run_id`` AND
    session ``status == 'queued'`` AND turn ``status == 'pending'``.
    On match: write session ``status='running'`` + heartbeat timestamps,
    turn ``status='running'``. Mirrors ``worker_main.py:355-363`` with
    GEAR's simpler fence keys."""
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if data.get("currentRunId") != expected_run_id:
        raise OwnershipLost(
            f"runId mismatch: expected={expected_run_id} actual={data.get('currentRunId')!r}"
        )
    if data.get("status") != "queued":
        raise OwnershipLost(
            f"status mismatch: expected=queued actual={data.get('status')!r}"
        )
    turn_snap = turn_ref.get(transaction=txn)
    turn_data = turn_snap.to_dict() or {}
    if turn_data.get("status") != "pending":
        raise OwnershipLost(
            f"turn.status mismatch: expected=pending actual={turn_data.get('status')!r}"
        )
    txn.update(
        session_ref,
        {
            "status": "running",
            "lastHeartbeat": firestore.SERVER_TIMESTAMP,
            "lastEventAt": firestore.SERVER_TIMESTAMP,
        },
    )
    txn.update(turn_ref, {"status": "running"})


_claim_txn = firestore.transactional(_claim_logic)


async def claim_invocation(fs: firestore.Client, state: GearRunState) -> None:
    """Take ownership of the run. Raises ``OwnershipLost`` on predicate
    mismatch — caller's responsibility to short-circuit cleanly via
    ``_halt_content()``."""
    session_ref = fs.collection("sessions").document(state.sid)
    turn_ref = session_ref.collection("turns").document(f"{state.turn_idx:04d}")
    await asyncio.to_thread(
        _claim_txn, fs.transaction(), session_ref, turn_ref, state.run_id
    )


def _fenced_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    turn_ref: firestore.DocumentReference | None,
    expected_run_id: str,
    session_updates: dict,
    turn_updates: dict | None,
) -> None:
    """Predicates: ``currentRunId == expected_run_id`` AND
    ``status == 'running'``. The status predicate prevents resurrecting a
    run that the watchdog or pre-handoff cleanup already flipped to
    'error'. Mirrors ``worker_main.py:341`` no-op-on-terminal pattern.
    """
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if data.get("currentRunId") != expected_run_id:
        raise OwnershipLost(
            f"runId: expected={expected_run_id} actual={data.get('currentRunId')!r}"
        )
    if data.get("status") != "running":
        raise OwnershipLost(
            f"status: expected=running actual={data.get('status')!r}"
        )
    txn.update(session_ref, session_updates)
    if turn_ref is not None and turn_updates is not None:
        txn.update(turn_ref, turn_updates)


_fenced_txn = firestore.transactional(_fenced_logic)


async def fenced_session_and_turn_update(
    fs: firestore.Client,
    state: GearRunState,
    session_updates: dict,
    turn_updates: dict,
) -> None:
    """Two-doc fenced write — used for terminal complete/error transitions
    so session metadata and turn content land atomically."""
    session_ref = fs.collection("sessions").document(state.sid)
    turn_ref = session_ref.collection("turns").document(f"{state.turn_idx:04d}")
    await asyncio.to_thread(
        _fenced_txn,
        fs.transaction(),
        session_ref,
        turn_ref,
        state.run_id,
        session_updates,
        turn_updates,
    )


async def fenced_session_update(
    fs: firestore.Client,
    state: GearRunState,
    session_updates: dict,
) -> None:
    """Single-doc fenced write — used for heartbeat ticks and
    ``lastEventAt`` bumps where the turn doc isn't touched."""
    session_ref = fs.collection("sessions").document(state.sid)
    await asyncio.to_thread(
        _fenced_txn,
        fs.transaction(),
        session_ref,
        None,
        state.run_id,
        session_updates,
        None,
    )


# ── Bounded retry on critical writes ─────────────────────────────────────────


async def _retry_critical(
    coro_factory: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.25,
) -> Any:
    """Retry transient Firestore errors with exponential backoff, plus
    a small random jitter. NEVER retries ``OwnershipLost`` — that's a
    definitive ownership signal, not transient. Used at the two call
    sites where transient failure causes a bad user outcome:
    ``claim_invocation`` and the terminal fenced write.
    """
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except OwnershipLost:
            raise
        except (GoogleAPICallError, RetryError, DeadlineExceeded):
            if attempt == max_attempts - 1:
                raise
            # Exponential backoff with jitter — small enough to fit
            # comfortably under the heartbeat tick budget.
            delay = base_delay * (2**attempt) * (0.5 + random.random())
            await asyncio.sleep(delay)


# ── Heartbeat loop ───────────────────────────────────────────────────────────


HEARTBEAT_INTERVAL_S = 30


async def _heartbeat_loop(fs: firestore.Client, state: GearRunState) -> None:
    """30 s tick → fenced heartbeat write. Mirrors ``worker_main.py:434-451``.
    Transient blips logged + continued; ``OwnershipLost`` exits cleanly.
    Cancellation is silent (caller awaits with timeout in ``stop_heartbeat``).
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            try:
                await fenced_session_update(
                    fs, state, {"lastHeartbeat": firestore.SERVER_TIMESTAMP}
                )
            except OwnershipLost:
                log.warning(
                    "heartbeat: ownership lost, exiting loop sid=%s runId=%s",
                    state.sid,
                    state.run_id,
                )
                return
            except Exception:  # noqa: BLE001
                # Transient Firestore blip — keep pulsing. The 30 s tick
                # IS the natural retry path.
                log.exception(
                    "heartbeat tick failed sid=%s runId=%s; continuing",
                    state.sid,
                    state.run_id,
                )
    except asyncio.CancelledError:
        pass


# ── Helpers ──────────────────────────────────────────────────────────────────


def _halt_content(reason: str) -> types.Content:
    """`before_run_callback` returning a ``types.Content`` triggers ADK's
    early-exit branch at ``runners.py:819``. Returning anything else
    (Event, None, raised exception) does NOT take that branch.
    """
    return types.Content(
        role="model",
        parts=[types.Part(text=f"[run halted: {reason}]")],
    )


def _query_text(invocation_context: InvocationContext) -> str:
    uc = getattr(invocation_context, "user_content", None)
    if uc is None:
        return ""
    parts = getattr(uc, "parts", None) or []
    out: list[str] = []
    for p in parts:
        text = getattr(p, "text", None)
        if isinstance(text, str) and text:
            out.append(text)
    return "\n".join(out)


def _build_state(
    fs: firestore.Client, invocation_context: InvocationContext
) -> Optional[GearRunState]:
    """Read sid + (runId, turnIdx, userId) from session.state — placed
    there by agentStream's ``:appendEvent`` (plan §5.1 stateDelta). Return
    ``None`` if the required keys are missing — the plugin then
    short-circuits via halt-content rather than crashing the runner.
    """
    session = getattr(invocation_context, "session", None)
    if session is None:
        log.error("plugin invoked without a session — cannot build state")
        return None
    state_dict = (getattr(session, "state", None) or {}) if session else {}
    run_id = state_dict.get("runId")
    turn_idx = state_dict.get("turnIdx")
    if not isinstance(run_id, str) or not run_id:
        log.error("session.state missing runId; cannot build GearRunState")
        return None
    if not isinstance(turn_idx, int):
        log.error("session.state missing/invalid turnIdx; cannot build GearRunState")
        return None
    sid = (session.id if hasattr(session, "id") else None) or ""
    # ADK creates the session under id `se-{sid}` (plan §"Verified-not-working":
    # sessionId regex disallows underscores, so agentStream prepends `se-`).
    # Strip the prefix to recover the Firestore session id.
    if sid.startswith("se-"):
        firestore_sid = sid[len("se-") :]
    else:
        firestore_sid = sid
    user_id = getattr(invocation_context, "user_id", None) or ""
    return GearRunState(
        sid=firestore_sid,
        invocation_id=invocation_context.invocation_id,
        run_id=run_id,
        turn_idx=turn_idx,
        user_id=user_id,
        query_text=_query_text(invocation_context),
        fs=fs,
    )


# ── Plugin ───────────────────────────────────────────────────────────────────


class FirestoreProgressPlugin(BasePlugin):
    """ADK plugin that mirrors the legacy worker's per-event Firestore
    writes for runs hosted on Vertex AI Agent Engine."""

    def __init__(self, project: str) -> None:
        super().__init__(name="firestore_progress")
        self._project = project
        self._fs: firestore.Client | None = None
        self._states: dict[str, GearRunState] = {}

    def _client(self) -> firestore.Client:
        # Lazy-init inside the request context so per-request creds resolve
        # cleanly (matches the probe plugin pattern at
        # `agent/probe/probe_plugin.py:44-50`).
        if self._fs is None:
            self._fs = firestore.Client(project=self._project)
        return self._fs

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext):
        fs = self._client()
        state = _build_state(fs, invocation_context)
        if state is None:
            # No gear-context runId in session.state. Two cases:
            #   1. Legacy Cloud Run worker is running the same App — it
            #      doesn't set runId into ADK session.state, so the plugin
            #      simply has nothing to mirror. Returning None lets the
            #      runner proceed normally; the worker writes progress
            #      itself via its own Firestore writes.
            #   2. A genuinely malformed gear handoff arrived without
            #      runId. The agentStream txn upsert already wrote the
            #      session doc with currentRunId, so the watchdog will
            #      catch any stuck state at the 5-min lastEventAt fence.
            # Halting here was the wrong choice — it killed the legacy
            # cloudrun path the moment the plugin landed globally on App.
            return None

        try:
            await _retry_critical(lambda: claim_invocation(fs, state))
        except OwnershipLost as e:
            log.warning(
                "claim_invocation lost sid=%s runId=%s: %s",
                state.sid,
                state.run_id,
                e,
            )
            return _halt_content("invocation_not_claimable")
        except Exception as e:  # noqa: BLE001
            log.error(
                "claim_invocation exhausted sid=%s runId=%s: %s",
                state.sid,
                state.run_id,
                e,
                exc_info=True,
            )
            return _halt_content("claim_exhausted")

        # On the first turn of the session, spawn the title task. We
        # derive isFirstMessage from turnIdx == 1 (agentStream allocates
        # turnIdx 1-based).
        if state.turn_idx == 1:
            state.title_task = asyncio.create_task(_generate_title(state.query_text))

        self._states[invocation_context.invocation_id] = state
        state.heartbeat_task = asyncio.create_task(_heartbeat_loop(fs, state))
        return None

    @override
    async def on_event_callback(
        self, *, invocation_context: InvocationContext, event: Event
    ):
        per = self._states.get(invocation_context.invocation_id)
        if per is None:
            # Plugin saw an event for an invocation that wasn't claimed —
            # before_run must have short-circuited. Ignore.
            return None

        # observe_event maps an ADK event into 0+ timeline rows and mutates
        # accumulator state. A mapper bug must not kill the run — receiving
        # an event already proves the pipeline is alive, so we still bump
        # lastEventAt below even when mapping fails.
        try:
            timeline_events = per.observe_event(event)
        except Exception:  # noqa: BLE001
            log.exception(
                "observe_event failed sid=%s runId=%s; continuing without timeline write",
                per.sid,
                per.run_id,
            )
            timeline_events = []

        # Best-effort timeline writes. TimelineWriter has its own internal
        # lock so concurrent writers don't interleave.
        for ev in timeline_events:
            try:
                await per.timeline_writer.write_timeline(ev)
            except Exception:  # noqa: BLE001
                log.exception(
                    "timeline write failed sid=%s runId=%s; continuing",
                    per.sid,
                    per.run_id,
                )

        # Best-effort lastEventAt bump — fenced so a flipped session
        # doesn't get re-bumped after watchdog/cleanup wrote 'error'.
        try:
            await fenced_session_update(
                self._client(), per, {"lastEventAt": firestore.SERVER_TIMESTAMP}
            )
        except OwnershipLost:
            # Run was flipped while we were processing this event. Don't
            # fight back; subsequent events will hit the same fence and
            # the run will wind down via after_run_callback.
            pass
        except Exception:  # noqa: BLE001
            log.exception(
                "lastEventAt bump failed sid=%s runId=%s; continuing",
                per.sid,
                per.run_id,
            )
        return None

    @override
    async def after_run_callback(self, *, invocation_context: InvocationContext):
        per = self._states.pop(invocation_context.invocation_id, None)
        if per is None:
            return None

        # Order matters and matches worker_main.py:1283 / :1328-1357:
        #   1. stop_heartbeat — late ticks can't clobber the terminal write
        #   2. finalize — drains notes (with cancel-stragglers + gather),
        #      closes writer, awaits title with timeout, builds payload
        #   3. fenced terminal write with bounded retry on transient
        #      Firestore errors (the answer is in process memory only;
        #      losing it on a retry-exhausted blip is unrecoverable).
        await per.stop_heartbeat()
        try:
            session_update, turn_update, _status = await per.finalize()
        except Exception:  # noqa: BLE001
            log.exception(
                "finalize crashed sid=%s runId=%s",
                per.sid,
                per.run_id,
            )
            # Best-effort terminal error write so the user sees an error
            # within ~1 s instead of waiting for watchdog (5 min) to flip
            # `pipeline_wedged`. Wraps `_retry_critical` to match the same
            # transient-Firestore retry semantics every other terminal
            # write enjoys (F2 P2 from the post-review plan).
            try:
                await _retry_critical(
                    lambda: fenced_session_and_turn_update(
                        self._client(),
                        per,
                        {
                            "status": "error",
                            "error": "finalize_failed",
                            "updatedAt": firestore.SERVER_TIMESTAMP,
                        },
                        {"status": "error", "error": "finalize_failed"},
                    )
                )
            except OwnershipLost:
                # Run was already flipped (watchdog or cleanup). Don't
                # resurrect.
                pass
            except Exception:  # noqa: BLE001
                log.exception(
                    "finalize_failed terminal write also failed sid=%s runId=%s",
                    per.sid,
                    per.run_id,
                )
            return None

        try:
            await _retry_critical(
                lambda: fenced_session_and_turn_update(
                    self._client(), per, session_update, turn_update
                )
            )
        except OwnershipLost:
            log.warning(
                "ownership lost before terminal write sid=%s runId=%s; not resurrecting",
                per.sid,
                per.run_id,
            )
        except Exception as e:  # noqa: BLE001
            # Retry exhausted on a transient Firestore error. Run stays
            # in 'running' until watchdog catches lastEventAt staleness
            # at the 5 min threshold and flips to status='error' with
            # reason 'pipeline_wedged'. The answer is lost in this rare
            # double-failure case.
            log.error(
                "terminal_write_exhausted sid=%s runId=%s reply_len=%s: %s",
                per.sid,
                per.run_id,
                len(per.final_reply or ""),
                e,
                exc_info=True,
            )
        return None
