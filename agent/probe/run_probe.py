"""Probe harness — invokes a deployed probe app via async_stream_query
and writes a local marker file per event so kill-after-first-event can
synchronize.

Run:  cd agent && PYTHONPATH=.. .venv/bin/python -m agent.probe.run_probe \\
        --flavour lifecycle --sid se-run001 --message "go"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import vertexai
from vertexai import agent_engines

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MARKERS_DIR = Path("/tmp/probe_markers")

STATE_FILE = Path(__file__).parent / "deployed_resources.json"


def _resource_name(flavour: str) -> str:
    state = json.loads(STATE_FILE.read_text())
    if flavour not in state:
        raise SystemExit(f"flavour {flavour!r} not deployed; run deploy.py first")
    return state[flavour]


async def run(flavour: str, sid: str, message: str, run_id: str, attempt: int, turn_idx: int) -> int:
    vertexai.init(project=PROJECT, location=LOCATION)
    resource_name = _resource_name(flavour)
    print(f"[harness] resource={resource_name}")
    print(f"[harness] sid={sid} runId={run_id} attempt={attempt} turnIdx={turn_idx}")

    remote = agent_engines.get(resource_name)
    print(f"[harness] remote methods: {[m for m in dir(remote) if 'session' in m or 'query' in m or 'operation' in m]}")

    # Create session — VertexAiSessionService rejects user-provided
    # session IDs (verified empirically 2026-04-26 contra April release
    # notes), so always let Agent Runtime generate the ID. Capture it
    # and use it as the sid for Firestore lookups too.
    # Keep the harness-arg sid as the marker-file prefix. The Agent
    # Runtime session id (real_sid) is only used for API calls — the
    # external kill script and watcher use the harness-arg sid.
    harness_sid = sid
    print(f"[harness] creating session (auto-generated id, marker prefix: {harness_sid})")
    sess = await remote.async_create_session(
        user_id="probe_user",
        state={"runId": run_id, "attempt": attempt, "turnIdx": turn_idx},
    )
    real_sid = sess["id"] if isinstance(sess, dict) else sess.id
    print(f"[harness] session created: real_sid={real_sid}")
    MARKERS_DIR.mkdir(parents=True, exist_ok=True)
    (MARKERS_DIR / f"{harness_sid}.real_sid").write_text(real_sid)

    started_marker = MARKERS_DIR / f"{harness_sid}.started"
    started_marker.write_text(str(time.time()))

    print(f"[harness] starting async_stream_query (real_sid={real_sid})")
    event_count = 0
    async for event in remote.async_stream_query(
        user_id="probe_user",
        session_id=real_sid,
        message=message,
    ):
        event_count += 1
        marker = MARKERS_DIR / f"{harness_sid}.event.{event_count}"
        marker.write_text(json.dumps({
            "ts": time.time(),
            "event_count": event_count,
            "event_repr": str(event)[:300],
        }))
        print(f"[harness] event #{event_count} received")

    completed_marker = MARKERS_DIR / f"{harness_sid}.completed"
    completed_marker.write_text(str(time.time()))
    print(f"[harness] stream completed cleanly, total_events={event_count}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flavour", choices=["lifecycle", "event_shape"], required=True)
    ap.add_argument("--sid", required=True, help="session id (must start with letter, [a-z0-9-])")
    ap.add_argument("--message", default="go", help="message text")
    ap.add_argument("--run-id", default="r1")
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--turn-idx", type=int, default=0)
    args = ap.parse_args()
    return asyncio.run(run(
        args.flavour, args.sid, args.message,
        args.run_id, args.attempt, args.turn_idx,
    ))


if __name__ == "__main__":
    sys.exit(main())
