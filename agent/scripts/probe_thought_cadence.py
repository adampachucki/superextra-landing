#!/usr/bin/env python3
"""One-shot probe — runs a real query against the deployed Reasoning Engine
to inspect Gemini thought-summary cadence on Research Lead.

Replicates the agentStream Cloud Function setup just enough to make the
plugin's before_run claim succeed:
  1. Write `sessions/{sid}` with currentRunId + status='queued' + turn doc
  2. Create ADK session in Vertex with stateDelta {runId, turnIdx}
  3. POST :streamQuery with class_method=async_stream_query
  4. Drain the SSE response so the run completes

After the run finishes, tail Cloud Logging for `PROBE_THOUGHT` lines —
each one is a thought-summary chunk Gemini emitted on this run.

Usage:
    .venv/bin/python scripts/probe_thought_cadence.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import google.auth
import google.auth.transport.requests
import httpx
from google.cloud import firestore

PROJECT = "superextra-site"
LOCATION = "us-central1"
RESOURCE = (
    "projects/907466498524/locations/us-central1/"
    "reasoningEngines/1179666575196684288"
)
VERTEX_BASE = f"https://{LOCATION}-aiplatform.googleapis.com"

# Probe identifiers — easy to spot/clean up later.
SID = f"probe-thought-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
RUN_ID = uuid.uuid4().hex
USER_ID = "probe-thought-cadence"
ADK_SID = f"se-{SID}"
TURN_IDX = 1

# A real-looking question with a plausible Warsaw venue. The placeId field
# is deliberately omitted so the model has to think + search.
QUERY = (
    f"[Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}] "
    "Give me a market-fit read on Nolita restaurant in Warsaw — its position "
    "vs. the closest fine-dining peers, sentiment trends, and any 2025 press "
    "worth flagging."
)


def _token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _seed_firestore(fs: firestore.Client) -> None:
    """Create the session + turn docs the plugin's before_run expects."""
    sess_ref = fs.collection("sessions").document(SID)
    turn_ref = sess_ref.collection("turns").document(f"{TURN_IDX:04d}")
    now = firestore.SERVER_TIMESTAMP
    sess_ref.set(
        {
            "userId": USER_ID,
            "participants": [USER_ID],
            "createdAt": now,
            "placeContext": None,
            "title": None,
            "currentRunId": RUN_ID,
            "status": "queued",
            "queuedAt": now,
            "lastHeartbeat": None,
            "lastEventAt": None,
            "error": None,
            "lastTurnIndex": TURN_IDX,
            "updatedAt": now,
        }
    )
    turn_ref.set(
        {
            "turnIndex": TURN_IDX,
            "runId": RUN_ID,
            "userMessage": QUERY,
            "status": "pending",
            "reply": None,
            "sources": None,
            "turnSummary": None,
            "createdAt": now,
            "completedAt": None,
            "error": None,
        }
    )
    print(f"  [firestore] seeded sessions/{SID} + turn 0001 (runId={RUN_ID})")


def _setup_adk_session(client: httpx.Client, headers: dict) -> None:
    """Create the ADK session and append the stateDelta event."""
    r = client.post(
        f"{VERTEX_BASE}/v1beta1/{RESOURCE}/sessions?sessionId={ADK_SID}",
        headers=headers,
        json={"userId": USER_ID, "sessionState": {"runId": RUN_ID, "turnIdx": TURN_IDX}},
    )
    if r.status_code not in (200, 409):
        raise RuntimeError(f"createSession failed: {r.status_code} {r.text[:300]}")
    print(f"  [adk] session ready ({r.status_code})")

    r = client.post(
        f"{VERTEX_BASE}/v1beta1/{RESOURCE}/sessions/{ADK_SID}:appendEvent",
        headers=headers,
        json={
            "author": "system",
            "invocationId": f"probe-{RUN_ID}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": {"stateDelta": {"runId": RUN_ID, "turnIdx": TURN_IDX}},
        },
    )
    if not r.is_success:
        raise RuntimeError(f"appendEvent failed: {r.status_code} {r.text[:300]}")
    print(f"  [adk] stateDelta appended ({r.status_code})")


def _stream_query(client: httpx.Client, headers: dict) -> int:
    """Stream the query and drain SSE so the run completes."""
    print("  [stream] POST :streamQuery — waiting for run to complete…")
    n_lines = 0
    started = time.time()
    with client.stream(
        "POST",
        f"{VERTEX_BASE}/v1/{RESOURCE}:streamQuery?alt=sse",
        headers=headers,
        json={
            "class_method": "async_stream_query",
            "input": {"user_id": USER_ID, "session_id": ADK_SID, "message": QUERY},
        },
        timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=60.0),
    ) as r:
        if not r.is_success:
            raise RuntimeError(f"streamQuery not ok: {r.status_code} {r.read().decode()[:500]}")
        for line in r.iter_lines():
            if not line:
                continue
            n_lines += 1
            # Periodically print progress so we can see the run is alive
            if n_lines % 10 == 0:
                elapsed = time.time() - started
                print(f"  [stream] {n_lines} lines, {elapsed:.0f}s elapsed")
    elapsed = time.time() - started
    print(f"  [stream] complete — {n_lines} SSE lines in {elapsed:.0f}s")
    return n_lines


def main() -> int:
    print(f"Probe — sid={SID} runId={RUN_ID}")
    print()

    fs = firestore.Client(project=PROJECT)
    _seed_firestore(fs)

    token = _token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client() as client:
        _setup_adk_session(client, headers)
        _stream_query(client, headers)

    print()
    print("Run finished. Tail thoughts with:")
    print(
        f"  gcloud logging read 'resource.type=\"aiplatform.googleapis.com/ReasoningEngine\" "
        f"AND textPayload:\"PROBE_THOUGHT\" AND textPayload:\"runId={RUN_ID}\"' "
        f"--project={PROJECT} --limit=500 --format='value(textPayload)' --freshness=15m"
    )
    print()
    print(f"To clean up: delete sessions/{SID} from Firestore (probe traffic only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
