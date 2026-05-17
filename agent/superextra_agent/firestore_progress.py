"""`FirestoreProgressPlugin` — runs inside Vertex AI Agent Engine.

For each root-runner invocation:

  - **before_run**: builds a ``GearRunState``, claims the run via fenced
    Firestore transaction (``status='queued' → 'running'``), spawns a
    30 s heartbeat, optionally spawns a title task on the first turn.
  - **tool hooks**: write typed tool-call/result pills through the accumulator.
  - **on_event**: feeds non-tool ADK event concerns through
    ``GearRunState.observe_event`` and bumps ``lastEventAt`` (best-effort).
  - **after_run**: cancels heartbeat first, builds the terminal payload,
    writes session+turn atomically with a bounded retry.

Three classes of write, three error semantics (plan §"Write-class taxonomy"):

  - **Critical** (claim, terminal): retried on transient Firestore errors;
    OwnershipLost surfaces immediately.
  - **Heartbeat**: no inner retry — the 30 s tick interval IS the retry.
  - **Best-effort** (timeline events, lastEventAt bumps): swallowed,
    logged; never halt the run.

Plugin granularity: production uses a top-level ``SequentialAgent`` with
specialists called through ``AgentTool``. ADK fires run-level callbacks for
each AgentTool child runner, so nested ``before_run``/``after_run`` callbacks
are lifecycle no-ops. Per-event callbacks from child runners are routed back
to the parent ``GearRunState`` by ``runId`` so live activity still reflects
specialist work without a second progress path.
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

from .cloud_logging import emit_cloud_log
from .correlation import (
    annotate_current_span,
    build_run_correlation,
    is_nested_invocation,
    normalize_firestore_sid,
    run_id_from_context,
    turn_idx_from_context,
)
from .firestore_events import (
    build_fetched_source,
    map_tool_call,
    map_tool_error,
    map_tool_result,
)
from .gear_run_state import GearRunState
from .notes import _generate_title
from .web_tools import (
    clear_fetch_cache_for_run,
    set_fetch_run_id,
)

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
    turn ``status='running'``."""
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


async def write_run_started_event(state: GearRunState) -> None:
    """Persist one immediate timeline row after a run is claimed.

    Gemini thought summaries can arrive only when a short continuation model
    call finishes. This row gives the UI real progress as soon as the Agent
    Engine owns the run, without fabricating model reasoning.
    """
    try:
        text = "Continuing research" if state.turn_idx > 1 else "Starting research"
        await state.observe_typed_pill(
            {
                "kind": "detail",
                "id": f"run-start:{state.run_id}",
                "group": "platform",
                "family": "Analysis",
                "text": text,
            }
        )
    except Exception:  # noqa: BLE001
        log.exception(
            "run-start timeline write failed sid=%s runId=%s; continuing",
            state.sid,
            state.run_id,
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
    'error'.
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
    """30 s tick → fenced heartbeat write. Transient blips logged + continued;
    ``OwnershipLost`` exits cleanly. Cancellation is silent (caller awaits
    with timeout in ``stop_heartbeat``).
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
    run_id = run_id_from_context(invocation_context)
    turn_idx = turn_idx_from_context(invocation_context)
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
    firestore_sid = normalize_firestore_sid(sid) or sid
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


def _merge_tool_sources(
    per: GearRunState,
    tool_name: str,
    tool_args: dict[str, Any],
    result: Any,
) -> None:
    """Surface successful page-reading tool URLs as run sources.

    Without this hook, fetched URLs would never appear in the per-turn
    source pills or same-run adjudicator source queue. Grounding chunks,
    fetched pages, and `_tool_src_*` provider sources all remain visible in
    the drawer; adjudication decides claim support separately.
    Adjudicator reads are not merged directly because read success is not claim
    support; successful read URLs only gate later `evidence_memo` sources.
    """
    if not isinstance(result, dict):
        return
    if tool_name == "read_adjudicator_sources":
        per.record_adjudicator_read_result(result)
        return
    if tool_name in (
        "read_web_pages",
        "read_public_page",
        "read_public_pages",
    ):
        if result.get("status") != "success":
            return
        for entry in result.get("sources") or []:
            per._merge_source(entry, reader_candidate=True)
        return
    if tool_name == "fetch_web_content":
        if result.get("status") != "success":
            return
        url = result.get("url") or (tool_args.get("url") if tool_args else None)
        entry = build_fetched_source(url, result.get("content"))
        if entry:
            per._merge_source(entry, reader_candidate=True)
        return
    if tool_name == "fetch_web_content_batch":
        for item in result.get("results") or []:
            if not isinstance(item, dict) or item.get("status") != "success":
                continue
            entry = build_fetched_source(item.get("url"), item.get("content"))
            if entry:
                per._merge_source(entry, reader_candidate=True)


# ── Plugin ───────────────────────────────────────────────────────────────────


class FirestoreProgressPlugin(BasePlugin):
    """ADK plugin that mirrors the legacy worker's per-event Firestore
    writes for runs hosted on Vertex AI Agent Engine."""

    def __init__(self, project: str) -> None:
        super().__init__(name="firestore_progress")
        self._project = project
        self._fs: firestore.Client | None = None
        self._states: dict[str, GearRunState] = {}
        self._states_by_run_id: dict[str, GearRunState] = {}

    def _client(self) -> firestore.Client:
        # Lazy-init inside the request context so per-request creds resolve
        # cleanly (matches the probe plugin pattern at
        # `agent/probe/probe_plugin.py:44-50`).
        if self._fs is None:
            self._fs = firestore.Client(project=self._project)
        return self._fs

    def _state_for_context(
        self, context: Any, *, allow_run_id_fallback: bool
    ) -> GearRunState | None:
        invocation_id = getattr(context, "invocation_id", None)
        per = self._states.get(invocation_id) if isinstance(invocation_id, str) else None
        if per is not None:
            return per
        if not allow_run_id_fallback:
            return None

        run_id = run_id_from_context(context)
        if not isinstance(run_id, str) or not run_id:
            return None
        return self._states_by_run_id.get(run_id)

    async def _observe_typed_pill(
        self, per: GearRunState, pill: dict[str, Any]
    ) -> None:
        try:
            await per.observe_typed_pill(pill)
        except Exception:  # noqa: BLE001
            log.exception(
                "typed timeline write failed sid=%s runId=%s; continuing",
                per.sid,
                per.run_id,
            )

    def _stage_for_agent(self, agent_name: str | None) -> str:
        if agent_name == "report_writer":
            return "writing_final_report"
        if agent_name == "evidence_adjudicator":
            return "checking_evidence"
        if agent_name == "research_lead":
            return "planning_research"
        if agent_name == "context_enricher":
            return "building_context"
        if agent_name == "router":
            return "routing"
        if agent_name == "continue_research":
            return "continuing_research"
        if agent_name:
            return "specialist_research"
        return "agent_work"

    async def _write_active_stage(
        self,
        per: GearRunState,
        *,
        agent_name: str | None,
        stage: str | None = None,
        model: str | None = None,
        invocation_id: str | None = None,
    ) -> None:
        per.timeline_builder.record_model_call(agent=agent_name, model=model)
        corr = build_run_correlation(
            per, invocation_id=invocation_id, agent=agent_name
        )
        annotate_current_span(corr)
        update: dict[str, Any] = {
            "activeAgent": agent_name or "unknown",
            "activeStage": stage or self._stage_for_agent(agent_name),
            "activeStageStartedAt": firestore.SERVER_TIMESTAMP,
        }
        if model is not None:
            update["activeModel"] = model
        else:
            update["activeModel"] = firestore.DELETE_FIELD
        if invocation_id is not None:
            update["activeInvocationId"] = invocation_id

        emit_cloud_log(
            "active_stage",
            **corr.as_log_fields(),
            stage=update["activeStage"],
            model=model,
        )

        try:
            await fenced_session_update(self._client(), per, update)
        except OwnershipLost:
            pass
        except Exception:  # noqa: BLE001
            log.exception(
                "active stage write failed sid=%s runId=%s; continuing",
                per.sid,
                per.run_id,
            )

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext):
        if is_nested_invocation(invocation_context):
            # AgentTool spawns a child Runner with its own InMemorySessionService
            # for each tool call. The parent invocation already owns the
            # Firestore session lifecycle (claim, heartbeat, terminal write);
            # nested invocations must be no-ops here to avoid duplicate
            # ownership claims and conflicting heartbeats.
            return None
        fs = self._client()
        state = _build_state(fs, invocation_context)
        if state is None:
            # Malformed handoff — agentStream's :appendEvent didn't put runId
            # into session.state. Halt the run before any LLM compute is
            # spent (returning types.Content triggers ADK's early-exit
            # branch at runners.py:819). The session was just written by
            # agentStream with status='queued'; the watchdog flips it
            # within 5 min via the handoff_start_timeout threshold.
            #
            # We deliberately do NOT write Firestore from this branch:
            # without our own runId we can't fence the write safely
            # (an unfenced flip could clobber a newer turn that took
            # over after agentStream's "previous-turn-in-flight" check
            # passed because watchdog already flipped this turn to error).
            log.warning(
                "halting run: session.state has no runId — malformed gear handoff"
            )
            return _halt_content("gear_handoff_state_missing")

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
        self._states_by_run_id[state.run_id] = state
        # Bind run id for the per-run fetch result cache in web_tools.
        # Paranoid clear handles the unlikely case of a stale entry from
        # a prior crashed run with the same id.
        clear_fetch_cache_for_run(state.run_id)
        set_fetch_run_id(state.run_id)
        state.heartbeat_task = asyncio.create_task(_heartbeat_loop(fs, state))
        asyncio.create_task(write_run_started_event(state))
        # Yield once so the best-effort run-start task can enter its first
        # Firestore await before model work begins, without waiting on the
        # Firestore write itself.
        await asyncio.sleep(0)
        return None

    @override
    async def before_model_callback(self, *, callback_context, llm_request):
        per = self._state_for_context(callback_context, allow_run_id_fallback=True)
        if per is None:
            return None
        await self._write_active_stage(
            per,
            agent_name=callback_context.agent_name,
            model=getattr(llm_request, "model", None),
            invocation_id=callback_context.invocation_id,
        )
        return None

    @override
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        per = self._state_for_context(tool_context, allow_run_id_fallback=True)
        if per is None:
            return None
        per.timeline_builder.record_tool_call(
            agent=getattr(tool_context, "agent_name", None),
            tool=tool.name,
        )
        pill = map_tool_call(
            tool.name,
            tool_args,
            per.mapping_state,
            getattr(tool_context, "function_call_id", None),
        )
        if pill is not None:
            await self._observe_typed_pill(per, pill)
        return None

    @override
    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        if isinstance(result, dict) and result.get("error"):
            return None
        per = self._state_for_context(tool_context, allow_run_id_fallback=True)
        if per is None:
            return None
        per.timeline_builder.record_tool_result(error=False)
        for pill in map_tool_result(
            tool.name,
            result if isinstance(result, dict) else {},
            per.mapping_state,
            getattr(tool_context, "function_call_id", None),
        ):
            await self._observe_typed_pill(per, pill)
        _merge_tool_sources(per, tool.name, tool_args, result)
        return None

    @override
    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        per = self._state_for_context(tool_context, allow_run_id_fallback=True)
        if per is None:
            return None
        per.timeline_builder.record_tool_result(error=True)
        for pill in map_tool_error(
            tool.name,
            tool_args,
            per.mapping_state,
            getattr(tool_context, "function_call_id", None),
        ):
            await self._observe_typed_pill(per, pill)
        return None

    @override
    async def on_event_callback(
        self, *, invocation_context: InvocationContext, event: Event
    ):
        per = self._state_for_context(
            invocation_context,
            allow_run_id_fallback=is_nested_invocation(invocation_context),
        )
        if per is None:
            # Plugin saw an event for an invocation that wasn't claimed —
            # before_run must have short-circuited, or an AgentTool child
            # event arrived after the parent run had already finalized.
            # Ignore.
            return None

        timeline_events = []
        is_partial = getattr(event, "partial", False)
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

        if is_partial:
            # Partial ADK events are useful only for early thought text. Tool
            # rows are emitted by typed tool callbacks, and terminal/source
            # state should come from the final aggregated event.
            timeline_events = [
                ev for ev in timeline_events if ev.get("kind") == "thought"
            ]
            if timeline_events:
                per.partial_thought_pending = True
        elif per.partial_thought_pending:
            # ADK emits a final aggregated event after the streamed partials.
            # Keep non-thought rows from that final event but avoid replaying
            # the same thought paragraph after the user already saw it stream.
            timeline_events = [ev for ev in timeline_events if ev.get("kind") != "thought"]
            per.partial_thought_pending = False

        # Best-effort timeline writes. TimelineWriter has its own internal
        # lock so concurrent writers don't interleave.
        for ev in timeline_events:
            try:
                per.timeline_builder.record_timeline_event(ev)
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
        if is_nested_invocation(invocation_context):
            # Nested invocation (AgentTool child) — parent owns lifecycle.
            return None
        per = self._states.pop(invocation_context.invocation_id, None)
        if per is None:
            return None
        self._states_by_run_id.pop(per.run_id, None)
        clear_fetch_cache_for_run(per.run_id)
        corr = build_run_correlation(per)

        # Order matters:
        #   1. stop_heartbeat — late ticks can't clobber the terminal write
        #   2. finalize — closes writer, awaits title with timeout,
        #      builds payload
        #   3. fenced terminal write with bounded retry on transient
        #      Firestore errors (the answer is in process memory only;
        #      losing it on a retry-exhausted blip is unrecoverable).
        await per.stop_heartbeat()
        annotate_current_span(corr)
        emit_cloud_log(
            "finalize_start",
            **corr.as_log_fields(),
            has_final_reply=bool(per.final_reply),
        )
        try:
            session_update, turn_update, _status = await per.finalize()
        except Exception:  # noqa: BLE001
            log.exception(
                "finalize crashed sid=%s runId=%s",
                per.sid,
                per.run_id,
            )
            # Best-effort terminal error write so the user sees an error
            # quickly instead of waiting for the watchdog to flip the run.
            # Wraps `_retry_critical` to match the same transient-Firestore
            # retry semantics every other terminal write uses.
            try:
                await _retry_critical(
                    lambda: fenced_session_and_turn_update(
                        self._client(),
                        per,
                        {
                            "status": "error",
                            "error": "finalize_failed",
                            "updatedAt": firestore.SERVER_TIMESTAMP,
                            "activeStage": "finalize_failed",
                        },
                        {
                            "status": "error",
                            "error": "finalize_failed",
                            "completedAt": firestore.SERVER_TIMESTAMP,
                        },
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

        if session_update.get("status") == "complete":
            session_update.update(
                {
                    "activeAgent": firestore.DELETE_FIELD,
                    "activeStage": firestore.DELETE_FIELD,
                    "activeStageStartedAt": firestore.DELETE_FIELD,
                    "activeModel": firestore.DELETE_FIELD,
                    "activeInvocationId": firestore.DELETE_FIELD,
                }
            )

        try:
            await _retry_critical(
                lambda: fenced_session_and_turn_update(
                    self._client(), per, session_update, turn_update
                )
            )
            emit_cloud_log(
                "finalize_success",
                **corr.as_log_fields(),
                status=session_update.get("status"),
                reply_len=len(per.final_reply or ""),
            )
        except OwnershipLost:
            log.warning(
                "ownership lost before terminal write sid=%s runId=%s; not resurrecting",
                per.sid,
                per.run_id,
            )
        except Exception as e:  # noqa: BLE001
            # Retry exhausted on a transient Firestore error. Run stays in
            # 'running' until the watchdog catches stale progress and flips
            # to status='error'. The answer is lost in this rare
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
