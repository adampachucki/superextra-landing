"""Spike A — verify ADK Runner(app=app) works in-process with Agent Engine session service.

Questions this answers:
  1. Does `Runner(app=app, session_service=VertexAiSessionService(...))` instantiate
     without error?
  2. Does `run_async(user_id, session_id, new_message=content)` yield events?
  3. Do `App.plugins` fire when we pass `app=app`? (verified by checking that
     `ChatLoggerPlugin` writes to `agent/logs/<date>_spike-*.jsonl`)
  4. Is session state persisted in Agent Engine? (verified by fetching the session
     after the run and inspecting `state` / `events`)

Usage:
    cd agent && PYTHONPATH=. .venv/bin/python ../spikes/adk_runner_spike.py

Outputs printed to stdout + final JSON summary at the end.
Early-exits after ~10 events or ~30 seconds to keep the spike cheap.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure we import from the agent package correctly
AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
sys.path.insert(0, str(AGENT_DIR))

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.genai import types

# Import agent code after path is set
from superextra_agent.agent import app  # noqa: E402

PROJECT = "superextra-site"
LOCATION = "us-central1"
AGENT_ENGINE_ID = "2746721333428617216"

USER_ID = "spike-user"
SESSION_ID_PREFIX = "spike-adk-runner-"

MAX_EVENTS = 10
TIMEOUT_S = 60


def _describe_event(evt, idx: int) -> dict:
    """Extract a compact, loggable summary of an ADK Event."""
    out: dict = {
        "idx": idx,
        "event_type": type(evt).__name__,
        "author": getattr(evt, "author", None),
        "partial": getattr(evt, "partial", None),
        "id": getattr(evt, "id", None),
        "is_final": None,
    }
    try:
        out["is_final"] = evt.is_final_response()
    except Exception:
        pass

    content = getattr(evt, "content", None)
    if content and getattr(content, "parts", None):
        parts_info = []
        for part in content.parts:
            pi: dict = {}
            if getattr(part, "text", None):
                pi["text_len"] = len(part.text)
                pi["text_preview"] = part.text[:120]
            if getattr(part, "function_call", None):
                pi["function_call"] = part.function_call.name
            if getattr(part, "function_response", None):
                pi["function_response"] = part.function_response.name
            if getattr(part, "inline_data", None) and getattr(part.inline_data, "mime_type", None):
                pi["inline_data_mime"] = part.inline_data.mime_type
            if pi:
                parts_info.append(pi)
        if parts_info:
            out["content_parts"] = parts_info

    actions = getattr(evt, "actions", None)
    if actions:
        state_delta = getattr(actions, "state_delta", None)
        if state_delta:
            out["state_delta_keys"] = list(state_delta.keys())

    gm = getattr(evt, "grounding_metadata", None)
    if gm:
        if getattr(gm, "web_search_queries", None):
            out["grounding_queries"] = list(gm.web_search_queries)
        if getattr(gm, "grounding_chunks", None):
            out["grounding_chunks_n"] = len(gm.grounding_chunks)

    return out


async def main() -> None:
    session_id = "<assigned-by-agent-engine>"
    print(f"[spike] agent_engine_id={AGENT_ENGINE_ID}", flush=True)
    print(f"[spike] app.name={app.name}, plugins={[p.__class__.__name__ for p in (app.plugins or [])]}", flush=True)

    # 1. Construct VertexAiSessionService
    svc = VertexAiSessionService(
        project=PROJECT,
        location=LOCATION,
        agent_engine_id=AGENT_ENGINE_ID,
    )
    print("[spike] VertexAiSessionService constructed ✓", flush=True)

    # 2. Create a fresh session in Agent Engine (Agent Engine assigns the session ID;
    #    user-provided IDs are rejected by VertexAiSessionService — finding #1 from spike).
    session = await svc.create_session(
        app_name=app.name,
        user_id=USER_ID,
    )
    session_id = session.id
    print(f"[spike] session created: id={session_id}, state_keys={list(session.state.keys())}", flush=True)

    # 3. Construct Runner(app=app, ...)
    runner = Runner(app=app, session_service=svc)
    print("[spike] Runner constructed ✓", flush=True)

    # 4. Fire a trivial message. Don't let it run the full 10-min pipeline —
    #    capture the first N events or timeout after TIMEOUT_S.
    message = types.Content(
        role="user",
        parts=[types.Part(text="hi")],
    )

    events_captured: list[dict] = []
    t0 = time.monotonic()
    error: str | None = None

    try:
        async def _consume():
            idx = 0
            async for evt in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=message,
            ):
                idx += 1
                summary = _describe_event(evt, idx)
                summary["t_since_start_s"] = round(time.monotonic() - t0, 2)
                events_captured.append(summary)
                print(
                    f"[spike] event #{idx} @{summary['t_since_start_s']}s "
                    f"author={summary.get('author')} partial={summary.get('partial')} "
                    f"final={summary.get('is_final')} parts={len(summary.get('content_parts') or [])} "
                    f"state_delta={summary.get('state_delta_keys')}",
                    flush=True,
                )
                if idx >= MAX_EVENTS:
                    print(f"[spike] reached MAX_EVENTS={MAX_EVENTS}, breaking", flush=True)
                    break

        await asyncio.wait_for(_consume(), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[spike] timeout after {TIMEOUT_S}s — breaking", flush=True)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"[spike] EXCEPTION during run_async: {error}", flush=True)
        import traceback
        traceback.print_exc()

    elapsed = round(time.monotonic() - t0, 2)

    # 5. Re-fetch the session to check state persistence
    persisted_state_keys: list[str] = []
    persisted_events_n = 0
    try:
        persisted = await svc.get_session(
            app_name=app.name,
            user_id=USER_ID,
            session_id=session_id,
        )
        if persisted:
            persisted_state_keys = list(persisted.state.keys())
            persisted_events_n = len(persisted.events or [])
            print(
                f"[spike] persisted session: state_keys={persisted_state_keys}, "
                f"events_n={persisted_events_n}",
                flush=True,
            )
    except Exception as e:
        print(f"[spike] re-fetch session failed: {type(e).__name__}: {e}", flush=True)

    # 6. Check that ChatLoggerPlugin produced a log file
    from datetime import datetime, timezone
    from superextra_agent.chat_logger import LOGS_DIR
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{date_str}_{session_id}.jsonl"
    plugin_fired = log_file.exists()
    plugin_lines = 0
    plugin_event_types: list[str] = []
    if plugin_fired:
        try:
            with log_file.open() as f:
                lines = f.readlines()
            plugin_lines = len(lines)
            for line in lines[:20]:
                try:
                    plugin_event_types.append(json.loads(line).get("event", "?"))
                except Exception:
                    pass
        except Exception:
            pass

    summary = {
        "session_id": session_id,
        "app_name": app.name,
        "plugins_configured": [p.__class__.__name__ for p in (app.plugins or [])],
        "events_captured_n": len(events_captured),
        "event_authors": sorted({e.get("author") for e in events_captured if e.get("author")}),
        "elapsed_s": elapsed,
        "error": error,
        "persisted_state_keys": persisted_state_keys,
        "persisted_events_n": persisted_events_n,
        "plugin_log_file": str(log_file),
        "plugin_log_fired": plugin_fired,
        "plugin_log_lines": plugin_lines,
        "plugin_event_types_first20": plugin_event_types,
    }
    print("\n[spike] === SUMMARY ===")
    print(json.dumps(summary, indent=2))

    # Verdict on each assumption
    print("\n[spike] === VERDICTS ===")
    print(f"  (1) Runner(app=app) constructs                    : {'PASS' if True else 'FAIL'}")
    print(f"  (2) run_async yields events                       : {'PASS' if events_captured else 'FAIL'}")
    print(f"  (3) Plugins fire via Runner(app=app)              : {'PASS' if plugin_fired else 'FAIL'}")
    print(f"  (4) Session state persisted in Agent Engine       : {'PASS' if persisted_state_keys or persisted_events_n else 'FAIL'}")

    # Dump full event log for downstream Spike B (event taxonomy mapping)
    dump_path = Path(__file__).parent / "adk_runner_spike_events.json"
    with dump_path.open("w") as f:
        json.dump({"summary": summary, "events": events_captured}, f, indent=2, default=str)
    print(f"\n[spike] full event log → {dump_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
