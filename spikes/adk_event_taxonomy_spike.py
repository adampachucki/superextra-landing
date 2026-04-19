"""Spike B — capture the full ADK event taxonomy from a real pipeline run.

Runs a realistic restaurant research query through `runner.run_async()` for up to
3 minutes, capturing every distinct event shape we emit. Output feeds Phase 2's
event-mapper design: we need to know exactly which event types the mapper must
handle to reach parity with today's `parseADKStream` (functions/utils.js:200-678).

Stops early after MAX_EVENTS events or after TIMEOUT_S seconds. Prints a
taxonomy summary at the end.

Usage:
    export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<user>/adc.json
    cd agent && PYTHONPATH=. .venv/bin/python ../spikes/adk_event_taxonomy_spike.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
sys.path.insert(0, str(AGENT_DIR))

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

# A real restaurant places_context is needed so the research pipeline actually
# runs — without it the router will short-circuit with clarification.
# Using Umami Berlin (same place_id from the stuck-session example in the plan).
PLACE_ID = "ChIJpYCQZztTUkYRFOE368Xs6kI"
PLACE_NAME = "Umami"
PLACE_SECONDARY = "Berlin"
QUERY_TEXT = "What service issues keep coming up in reviews?"

from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.genai import types

from superextra_agent.agent import app  # noqa: E402

PROJECT = "superextra-site"
LOCATION = "us-central1"
AGENT_ENGINE_ID = "2746721333428617216"
USER_ID = "spike-user"

MAX_EVENTS = 50
TIMEOUT_S = 180


def _describe_event(evt, idx: int, t0: float) -> dict:
    out: dict = {
        "idx": idx,
        "t_s": round(time.monotonic() - t0, 2),
        "event_class": type(evt).__name__,
        "author": getattr(evt, "author", None),
        "partial": getattr(evt, "partial", None),
        "id": getattr(evt, "id", None),
        "branch": getattr(evt, "branch", None),
        "is_final": None,
    }
    try:
        out["is_final"] = evt.is_final_response()
    except Exception:
        pass

    content = getattr(evt, "content", None)
    if content and getattr(content, "parts", None):
        parts = []
        for p in content.parts:
            pi: dict = {}
            if getattr(p, "text", None):
                pi["text_len"] = len(p.text)
                pi["text_preview"] = p.text[:180]
            if getattr(p, "function_call", None):
                pi["function_call_name"] = p.function_call.name
                args = p.function_call.args
                if args:
                    pi["function_call_args_keys"] = list(args.keys())[:8]
            if getattr(p, "function_response", None):
                pi["function_response_name"] = p.function_response.name
                r = p.function_response.response
                if r is not None:
                    if isinstance(r, dict):
                        pi["function_response_keys"] = list(r.keys())[:8]
                    else:
                        pi["function_response_repr"] = str(r)[:180]
            if getattr(p, "inline_data", None) and getattr(p.inline_data, "mime_type", None):
                pi["inline_data_mime"] = p.inline_data.mime_type
            if getattr(p, "thought", None):
                pi["thought"] = True
            if pi:
                parts.append(pi)
        if parts:
            out["parts"] = parts

    actions = getattr(evt, "actions", None)
    if actions:
        sd = getattr(actions, "state_delta", None)
        if sd:
            out["state_delta_keys"] = list(sd.keys())
        esc = getattr(actions, "escalate", None)
        if esc:
            out["escalate"] = True
        tr = getattr(actions, "transfer_to_agent", None)
        if tr:
            out["transfer_to_agent"] = tr

    gm = getattr(evt, "grounding_metadata", None)
    if gm:
        if getattr(gm, "web_search_queries", None):
            out["grounding_queries"] = list(gm.web_search_queries)
        if getattr(gm, "grounding_chunks", None):
            out["grounding_chunks_n"] = len(gm.grounding_chunks)
            # sample a chunk to see shape
            ch = gm.grounding_chunks[0]
            if getattr(ch, "web", None):
                out["grounding_chunk_sample"] = {
                    "has_uri": bool(getattr(ch.web, "uri", None)),
                    "has_title": bool(getattr(ch.web, "title", None)),
                    "has_domain": bool(getattr(ch.web, "domain", None)),
                }

    um = getattr(evt, "usage_metadata", None)
    if um:
        out["tokens"] = {
            "prompt": getattr(um, "prompt_token_count", None),
            "candidates": getattr(um, "candidates_token_count", None),
        }

    if getattr(evt, "error_code", None):
        out["error_code"] = evt.error_code
        out["error_message"] = getattr(evt, "error_message", None)

    return out


async def main() -> None:
    svc = VertexAiSessionService(
        project=PROJECT, location=LOCATION, agent_engine_id=AGENT_ENGINE_ID
    )
    session = await svc.create_session(app_name=app.name, user_id=USER_ID)
    print(f"[spike] session_id={session.id}", flush=True)

    runner = Runner(app=app, session_service=svc)

    # Match what functions/index.js:297-300 builds for the real chat flow
    full_query = (
        f"[Date: 2026-04-19] "
        f"[Context: asking about {PLACE_NAME}, {PLACE_SECONDARY} (Place ID: {PLACE_ID})] "
        f"{QUERY_TEXT}"
    )
    print(f"[spike] query: {full_query}", flush=True)

    message = types.Content(role="user", parts=[types.Part(text=full_query)])

    events: list[dict] = []
    t0 = time.monotonic()
    error: str | None = None

    try:
        async def _consume():
            idx = 0
            async for evt in runner.run_async(
                user_id=USER_ID, session_id=session.id, new_message=message
            ):
                idx += 1
                info = _describe_event(evt, idx, t0)
                events.append(info)
                parts_n = len(info.get("parts") or [])
                fc = next(
                    (p.get("function_call_name") for p in info.get("parts") or [] if p.get("function_call_name")),
                    None,
                )
                fr = next(
                    (p.get("function_response_name") for p in info.get("parts") or [] if p.get("function_response_name")),
                    None,
                )
                print(
                    f"[spike] #{idx:02d} @{info['t_s']:>6.2f}s  author={info.get('author'):<28s} "
                    f"partial={str(info.get('partial')):<5s}  final={str(info.get('is_final')):<5s}  "
                    f"parts={parts_n}  fc={fc or '-'}  fr={fr or '-'}  sd={info.get('state_delta_keys') or '-'}",
                    flush=True,
                )
                if idx >= MAX_EVENTS:
                    print(f"[spike] MAX_EVENTS={MAX_EVENTS} reached", flush=True)
                    break

        await asyncio.wait_for(_consume(), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[spike] timeout after {TIMEOUT_S}s", flush=True)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"[spike] EXCEPTION: {error}", flush=True)
        import traceback
        traceback.print_exc()

    elapsed = round(time.monotonic() - t0, 2)

    # Taxonomy summary
    author_counts = Counter(e.get("author") for e in events)
    state_delta_keys = set()
    for e in events:
        for k in e.get("state_delta_keys") or []:
            state_delta_keys.add(k)

    function_calls = Counter()
    function_responses = Counter()
    partial_text_events = 0
    final_events = 0
    grounding_events = 0

    for e in events:
        if e.get("is_final"):
            final_events += 1
        if e.get("partial"):
            partial_text_events += 1
        if e.get("grounding_queries") or e.get("grounding_chunks_n"):
            grounding_events += 1
        for p in e.get("parts") or []:
            if p.get("function_call_name"):
                function_calls[p["function_call_name"]] += 1
            if p.get("function_response_name"):
                function_responses[p["function_response_name"]] += 1

    print("\n[spike] === TAXONOMY SUMMARY ===")
    print(f"elapsed_s={elapsed}  events_captured={len(events)}  error={error}")
    print(f"authors: {dict(author_counts)}")
    print(f"state_delta_keys_seen: {sorted(state_delta_keys)}")
    print(f"function_calls: {dict(function_calls)}")
    print(f"function_responses: {dict(function_responses)}")
    print(f"partial_text_events: {partial_text_events}")
    print(f"final_events: {final_events}")
    print(f"grounding_events: {grounding_events}")

    dump = Path(__file__).parent / "adk_event_taxonomy_dump.json"
    with dump.open("w") as f:
        json.dump({
            "session_id": session.id,
            "elapsed_s": elapsed,
            "error": error,
            "authors": dict(author_counts),
            "state_delta_keys": sorted(state_delta_keys),
            "function_calls": dict(function_calls),
            "function_responses": dict(function_responses),
            "partial_text_events": partial_text_events,
            "final_events": final_events,
            "grounding_events": grounding_events,
            "events": events,
        }, f, indent=2, default=str)
    print(f"[spike] full dump → {dump}")


if __name__ == "__main__":
    asyncio.run(main())
