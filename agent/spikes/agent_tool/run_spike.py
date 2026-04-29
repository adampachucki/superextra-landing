"""Run Variant A and Variant B against the same query and capture
comparable artifacts.

Captures into `results/<variant>.json`:
- elapsed wall-clock time
- per-event timestamps (start, function_call, function_response, output)
- which agent emitted each event
- function calls (tool name + args excerpt)
- function responses (tool name + length excerpt)
- final state keys + their lengths
- whether output_key writes succeeded

Run:
  cd agent
  .venv/bin/python spikes/agent_tool/run_spike.py [--variant a|b|both]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path

# Set env BEFORE importing build.py (which imports superextra_agent)
SPIKE_DIR = Path(__file__).resolve().parent
AGENT_DIR = SPIKE_DIR.parents[1]
sys.path.insert(0, str(AGENT_DIR))

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(AGENT_DIR / ".env")

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from spikes.agent_tool.build import build_variant_a, build_variant_b  # type: ignore
from spikes.agent_tool.places_context import PLACES_CONTEXT, QUERY  # type: ignore

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


def _summarize_event(evt) -> dict:
    """Extract the comparable bits from an ADK event."""
    out = {
        "ts": time.monotonic(),
        "author": getattr(evt, "author", None),
        "invocation_id": getattr(evt, "invocation_id", None),
        "branch": getattr(evt, "branch", None),
        "id": getattr(evt, "id", None),
    }
    content = getattr(evt, "content", None)
    if content and getattr(content, "parts", None):
        text_parts = []
        thought_parts = []
        function_calls = []
        function_responses = []
        out["parts_count"] = len(content.parts)
        for p in content.parts:
            if getattr(p, "text", None):
                if getattr(p, "thought", False):
                    thought_parts.append(p.text)
                else:
                    text_parts.append(p.text)
            fc = getattr(p, "function_call", None)
            if fc:
                args_repr = (
                    json.dumps({k: (v[:120] + "…" if isinstance(v, str) and len(v) > 120 else v) for k, v in (fc.args or {}).items()})
                    if fc.args else "{}"
                )
                function_calls.append({"name": fc.name, "args_excerpt": args_repr})
            fr = getattr(p, "function_response", None)
            if fr:
                resp_str = json.dumps(fr.response) if fr.response is not None else ""
                excerpt = resp_str[:200] + ("…" if len(resp_str) > 200 else "")
                function_responses.append({"name": fr.name, "response_len": len(resp_str), "response_excerpt": excerpt})
        if text_parts:
            joined = "\n".join(text_parts)
            out["text_len"] = len(joined)
            out["text_excerpt"] = joined[:300] + ("…" if len(joined) > 300 else "")
        if thought_parts:
            joined = "\n".join(thought_parts)
            out["thought_len"] = len(joined)
            out["thought_excerpt"] = joined[:200] + ("…" if len(joined) > 200 else "")
        if function_calls:
            out["function_calls"] = function_calls
        if function_responses:
            out["function_responses"] = function_responses
    elif content is None:
        out["content_state"] = "none"
    else:
        out["content_state"] = "no_parts"
    actions = getattr(evt, "actions", None)
    if actions and getattr(actions, "state_delta", None):
        out["state_delta_keys"] = list(actions.state_delta.keys())
    err_code = getattr(evt, "error_code", None)
    err_msg = getattr(evt, "error_message", None)
    if err_code or err_msg:
        out["error_code"] = err_code
        out["error_message"] = err_msg
    # Capture turn_complete flag if present (helps identify final events)
    out["turn_complete"] = getattr(evt, "turn_complete", None)
    return out


async def _run_one(label: str, root_agent, *, place_id: str = "ChIJ48HwEQCn_UYRmVqYQULc9pM") -> dict:
    svc = InMemorySessionService()
    app_name = f"spike_{label}"
    user_id = f"spike-{label}"
    session = await svc.create_session(
        app_name=app_name,
        user_id=user_id,
        state={
            "places_context": PLACES_CONTEXT,
            "_target_place_id": place_id,
        },
    )
    today = datetime.date.today().isoformat()
    full_query = f"[Date: {today}] [Context: asking about Monsun, Świętojańska, Gdynia, Poland (Place ID: {place_id})] {QUERY}"
    msg = types.Content(role="user", parts=[types.Part(text=full_query)])

    runner = Runner(app_name=app_name, agent=root_agent, session_service=svc)

    events_summary = []
    t0 = time.monotonic()
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    error = None
    timed_out = False

    async def _consume():
        async for evt in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=msg
        ):
            summary = _summarize_event(evt)
            summary["elapsed_s"] = round(summary["ts"] - t0, 2)
            events_summary.append(summary)
            # Live progress in stderr so the user can watch
            ts = summary["elapsed_s"]
            author = summary.get("author") or "?"
            bits = []
            if "function_calls" in summary:
                bits.append(f"call {[fc['name'] for fc in summary['function_calls']]}")
            if "function_responses" in summary:
                bits.append(f"resp {[fr['name'] for fr in summary['function_responses']]}")
            if summary.get("text_len"):
                bits.append(f"text({summary['text_len']})")
            if summary.get("thought_len"):
                bits.append(f"thought({summary['thought_len']})")
            if summary.get("state_delta_keys"):
                bits.append(f"state_delta={summary['state_delta_keys']}")
            if summary.get("error_code") or summary.get("error_message"):
                bits.append(f"ERROR {summary.get('error_code')}/{summary.get('error_message')}")
            if not bits and summary.get("content_state"):
                bits.append(f"content={summary['content_state']}")
            print(f"[{label} +{ts:5.1f}s] {author} {' | '.join(bits)}", file=sys.stderr, flush=True)

    try:
        # 12-min budget is plenty for a 2-specialist run
        await asyncio.wait_for(_consume(), timeout=12 * 60)
    except asyncio.TimeoutError:
        timed_out = True
        error = "timeout"
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"

    elapsed = time.monotonic() - t0

    # Read final state
    final_session = await svc.get_session(
        app_name=app_name, user_id=user_id, session_id=session.id
    )
    final_state = dict(final_session.state) if final_session else {}
    state_summary = {}
    for k, v in final_state.items():
        if isinstance(v, str):
            state_summary[k] = {"type": "str", "len": len(v), "excerpt": v[:300]}
        elif isinstance(v, dict):
            state_summary[k] = {"type": "dict", "keys": list(v.keys())}
        else:
            state_summary[k] = {"type": type(v).__name__}

    return {
        "label": label,
        "started_at": started_at,
        "elapsed_s": round(elapsed, 2),
        "timed_out": timed_out,
        "error": error,
        "events": events_summary,
        "final_state_summary": state_summary,
    }


def _save(record: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str))


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["a", "b", "both"], default="both")
    parser.add_argument("--suffix", default="", help="suffix for output filename, e.g. trial2")
    args = parser.parse_args()

    out_dir = SPIKE_DIR / "results"

    suffix = f"_{args.suffix}" if args.suffix else ""

    if args.variant in ("a", "both"):
        print("=" * 60, file=sys.stderr)
        print("VARIANT A — current setup replica (set_specialist_briefs + ParallelAgent)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        rec = await _run_one("variant_a" + suffix, build_variant_a())
        _save(rec, out_dir / f"variant_a{suffix}.json")
        print(f"\n→ saved variant_a{suffix}.json  elapsed={rec['elapsed_s']:.1f}s  error={rec['error']}\n", file=sys.stderr)

    if args.variant in ("b", "both"):
        print("=" * 60, file=sys.stderr)
        print("VARIANT B — AgentTool-wrapped specialists", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        rec = await _run_one("variant_b" + suffix, build_variant_b())
        _save(rec, out_dir / f"variant_b{suffix}.json")
        print(f"\n→ saved variant_b{suffix}.json  elapsed={rec['elapsed_s']:.1f}s  error={rec['error']}\n", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
