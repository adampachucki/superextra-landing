#!/usr/bin/env python3
"""Post-deploy smoke: run one real prompt through the deployed Reasoning
Engine and verify the Firestore terminal state the frontend consumes.

Mirrors the production handoff (agentStream → gearHandoff):
  1. seed `sessions/{sid}` + `turns/0001` (status queued/pending, currentRunId)
  2. createSession + appendEvent with the same state keys gearHandoff sends
     (runId, turnIdx, firestoreSid, quotaUid, promptLanguage — keep in sync
     with functions/gear-handoff.js)
  3. POST :streamQuery and read the FIRST stream line as proof of acceptance,
     then disconnect — runs survive client disconnect by design, so Firestore
     (not the stream) is the authoritative signal
  4. poll the turn doc to a terminal status; verify reply/sources/summary and
     timeline events
  5. delete the probe docs — sessions/turns have no TTL (only events do), so
     cleanup is the default; pass --keep to retain them for inspection

Exit code 0 = PASS, 1 = FAIL.

Usage:
    .venv/bin/python scripts/smoke_run.py [--keep] [--timeout 900]
"""
from __future__ import annotations

import argparse
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
USER_ID = "smoke-run-probe"
TURN_IDX = 1
POLL_INTERVAL_S = 10.0

QUERY = (
    f"[Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}] "
    "What has opened or closed recently around Świętojańska street in "
    "Gdynia, Poland, and what does it mean for a casual restaurant there?"
)


def _token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def seed_firestore(fs: firestore.Client, sid: str, run_id: str) -> None:
    sess_ref = fs.collection("sessions").document(sid)
    now = firestore.SERVER_TIMESTAMP
    sess_ref.set(
        {
            "userId": USER_ID,
            "participants": [USER_ID],
            "createdAt": now,
            "placeContext": None,
            "title": None,
            "currentRunId": run_id,
            "status": "queued",
            "queuedAt": now,
            "lastHeartbeat": None,
            "lastEventAt": None,
            "error": None,
            "lastTurnIndex": TURN_IDX,
            "updatedAt": now,
        }
    )
    sess_ref.collection("turns").document(f"{TURN_IDX:04d}").set(
        {
            "turnIndex": TURN_IDX,
            "runId": run_id,
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
    print(f"  [firestore] seeded sessions/{sid} turn 0001 runId={run_id}")


def start_run(client: httpx.Client, headers: dict, sid: str, run_id: str) -> None:
    adk_sid = f"se-{sid}"
    state = {
        "runId": run_id,
        "turnIdx": TURN_IDX,
        "firestoreSid": sid,
        "promptLanguage": "en",
    }
    r = client.post(
        f"{VERTEX_BASE}/v1beta1/{RESOURCE}/sessions?sessionId={adk_sid}",
        headers=headers,
        json={"userId": USER_ID, "sessionState": state},
    )
    if r.status_code not in (200, 409):
        raise RuntimeError(f"createSession failed: {r.status_code} {r.text[:300]}")

    r = client.post(
        f"{VERTEX_BASE}/v1beta1/{RESOURCE}/sessions/{adk_sid}:appendEvent",
        headers=headers,
        json={
            "author": "system",
            "invocationId": f"smoke-{run_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": {"stateDelta": {**state, "quotaUid": USER_ID}},
        },
    )
    if not r.is_success:
        raise RuntimeError(f"appendEvent failed: {r.status_code} {r.text[:300]}")

    # First stream line proves the engine accepted the run; after that the
    # run continues server-side without us (same contract gearHandoff uses).
    with client.stream(
        "POST",
        f"{VERTEX_BASE}/v1/{RESOURCE}:streamQuery?alt=sse",
        headers=headers,
        json={
            "class_method": "async_stream_query",
            "input": {"user_id": USER_ID, "session_id": adk_sid, "message": QUERY},
        },
        timeout=httpx.Timeout(connect=30.0, read=120.0, write=60.0, pool=60.0),
    ) as r:
        if not r.is_success:
            raise RuntimeError(
                f"streamQuery not ok: {r.status_code} {r.read().decode()[:500]}"
            )
        for line in r.iter_lines():
            if line:
                print("  [stream] run accepted (first line received); disconnecting")
                break


def wait_for_terminal(fs: firestore.Client, sid: str, timeout_s: float) -> dict:
    turn_ref = (
        fs.collection("sessions").document(sid).collection("turns").document("0001")
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        turn = turn_ref.get().to_dict() or {}
        status = turn.get("status")
        if status in ("complete", "error"):
            return turn
        print(f"  [poll] turn status={status} — waiting…")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"turn did not reach a terminal status in {timeout_s:.0f}s")


def evaluate(turn: dict, event_count: int) -> tuple[bool, list[str]]:
    """Pure pass/fail predicate over the terminal turn doc + event count."""
    problems = []
    if turn.get("status") != "complete":
        problems.append(f"turn.status={turn.get('status')} error={turn.get('error')}")
    reply = turn.get("reply") or ""
    if len(reply) < 500:
        problems.append(f"reply too short ({len(reply)} chars)")
    if not turn.get("turnSummary"):
        problems.append("turnSummary missing")
    if not (turn.get("sources") or []):
        problems.append("no sources")
    if event_count == 0:
        problems.append("no timeline events")
    return (not problems, problems)


def cleanup(fs: firestore.Client, client: httpx.Client, headers: dict, sid: str) -> None:
    sess_ref = fs.collection("sessions").document(sid)
    for sub in ("events", "turns"):
        for doc in sess_ref.collection(sub).stream():
            doc.reference.delete()
    sess_ref.delete()
    r = client.delete(
        f"{VERTEX_BASE}/v1beta1/{RESOURCE}/sessions/se-{sid}", headers=headers
    )
    adk_note = "" if r.is_success else f" (ADK session delete: {r.status_code})"
    print(f"  [cleanup] deleted sessions/{sid} + subcollections{adk_note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep probe docs")
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    sid = f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    run_id = uuid.uuid4().hex
    print(f"Smoke run — sid={sid} runId={run_id}")

    fs = firestore.Client(project=PROJECT)
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    seed_firestore(fs, sid, run_id)
    with httpx.Client() as client:
        start_run(client, headers, sid, run_id)
        started = time.time()
        try:
            turn = wait_for_terminal(fs, sid, args.timeout)
        except TimeoutError as err:
            print(f"SMOKE FAIL — {err} (docs kept at sessions/{sid})")
            return 1
        events = list(
            fs.collection("sessions").document(sid).collection("events").stream()
        )
        ok, problems = evaluate(turn, len(events))

        print()
        print(f"  turn.status   : {turn.get('status')} ({time.time() - started:.0f}s)")
        print(f"  reply length  : {len(turn.get('reply') or '')}")
        print(f"  sources       : {len(turn.get('sources') or [])}")
        print(f"  events        : {len(events)}")
        for p in problems:
            print(f"  PROBLEM       : {p}")

        if args.keep or not ok:
            print(f"  (probe docs kept at sessions/{sid})")
        else:
            cleanup(fs, client, headers, sid)

    print()
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
