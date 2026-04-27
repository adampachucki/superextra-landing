"""R3.1 — verify per-turn `sessionState` mutability.

Plan: docs/gear-probe-plan-round3-2026-04-26.md §R3.1.

Sequence:
1. Create fresh session via REST `:createSession?sessionId=se-r31-{ts}` with
   sessionState={runId: 'r-1', turnIdx: 0, attempt: 1}.
2. Write turn1_started_at marker. Run async_stream_query (turn 1). Capture
   invocation_id from first event. Verify plugin docs from this invocation
   carry r-1.
3. Try four state-mutation mechanisms in order, stopping at first success:
   (a) PATCH sessions?updateMask=sessionState
   (b) :appendEvent with stateDelta
   (c) SDK async_update_session
   (d) :createEvent or other discovered endpoints
4. Re-read session via :getSession to confirm state actually mutated.
5. Write turn2_started_at marker. Run async_stream_query (turn 2). Capture
   invocation_id. Filter Firestore docs by turn 2's invocation_id +
   ts >= turn2_started_at. Verify they carry r-2.

Exit codes:
  0 = PASS — turn-2 docs show updated runId='r-2' and turnIdx=1
  1 = FAIL — turn-2 docs still show original values, or no mutation worked
  2 = INCONCLUSIVE — mutation succeeded at HTTP but :getSession unchanged
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

import google.auth
import google.auth.transport.requests
import requests
import vertexai
from google.cloud import firestore
from vertexai import agent_engines

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
KITCHEN_RESOURCE = "projects/907466498524/locations/us-central1/reasoningEngines/3851695334971408384"


def _token() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _create_session(sid: str, user_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Create session via REST with custom sessionId."""
    r = requests.post(
        f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{KITCHEN_RESOURCE}/sessions?sessionId={sid}",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json={"userId": user_id, "sessionState": state},
        timeout=30,
    )
    print(f"[create_session] status={r.status_code} body={r.text[:300]}")
    r.raise_for_status()
    return r.json()


def _get_session_state(sid: str) -> dict[str, Any]:
    r = requests.get(
        f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{KITCHEN_RESOURCE}/sessions/{sid}",
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("sessionState") or {}


def _write_marker(fs: firestore.Client, sid: str, name: str) -> None:
    ref = fs.collection("probe_runs").document(sid).collection("markers").document(name)
    ref.set({"ts": firestore.SERVER_TIMESTAMP, "wall_time": time.time()})


def _try_patch_sessionstate(sid: str, new_state: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Mechanism (a): REST PATCH with updateMask=sessionState."""
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{KITCHEN_RESOURCE}/sessions/{sid}?updateMask=sessionState"
    body = {"sessionState": new_state}
    r = requests.patch(
        url,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    out = {"status": r.status_code, "body": r.text[:500], "request": json.dumps(body)}
    return (r.status_code < 300), out


def _try_append_event(sid: str, new_state: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Mechanism (b): REST :appendEvent with actions.stateDelta (camelCase).

    Platform explicitly directed us here via mechanism (a)'s error:
    'Can't update the session state... you can only update it by appending
    an event.' Payload uses protobuf Timestamp format (RFC3339 string),
    NOT Unix float."""
    from datetime import datetime, timezone
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{KITCHEN_RESOURCE}/sessions/{sid}:appendEvent"
    body = {
        "author": "system",
        "invocationId": f"r31-mutate-{int(time.time())}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "actions": {
            "stateDelta": new_state,
        },
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    out = {"status": r.status_code, "body": r.text[:500], "request": json.dumps(body)}
    return (r.status_code < 300), out


def _try_sdk_update(remote, new_state: dict[str, Any], sid: str) -> tuple[bool, dict[str, Any]]:
    """Mechanism (c): SDK async_update_session if exposed."""
    methods = [m for m in dir(remote) if "update" in m.lower() and "session" in m.lower()]
    if not methods:
        return False, {"reason": "no SDK update_session-like method exists", "dir": [m for m in dir(remote) if not m.startswith("_")][:30]}
    return False, {"reason": f"SDK methods exist but signature unknown: {methods}", "manual_followup": True}


async def run() -> int:
    fs = firestore.Client(project=PROJECT)
    vertexai.init(project=PROJECT, location=LOCATION)
    remote = agent_engines.get(KITCHEN_RESOURCE)

    sid = f"se-r31-{int(time.time())}"
    print(f"\n=== R3.1 sid={sid} ===")

    # Step 1: create with state runId=r-1
    print("\n--- Step 1: create session with sessionState={runId: r-1, turnIdx: 0, attempt: 1} ---")
    _create_session(sid, "r31", {"runId": "r-1", "turnIdx": 0, "attempt": 1})

    # Step 2: turn 1 invoke
    print("\n--- Step 2: turn 1 invoke ---")
    _write_marker(fs, sid, "turn1_started_at")
    turn1_invocation_id: str | None = None
    n1 = 0
    async for ev in remote.async_stream_query(
        user_id="r31", session_id=sid, message="fetch:https://example.com/"
    ):
        n1 += 1
        if turn1_invocation_id is None:
            turn1_invocation_id = ev.get("invocation_id")
            print(f"[turn1] invocation_id={turn1_invocation_id}")
    print(f"[turn1] {n1} events")

    # Wait briefly for plugin docs to land
    await asyncio.sleep(3)

    # Verify turn 1 docs carry r-1
    turn1_docs = list(fs.collection("probe_runs").document(sid).collection("events").stream())
    turn1_filtered = [d for d in turn1_docs if (d.to_dict() or {}).get("invocation_id") == turn1_invocation_id]
    print(f"[turn1] {len(turn1_filtered)} plugin docs for invocation_id={turn1_invocation_id}")
    if turn1_filtered:
        sample = turn1_filtered[0].to_dict()
        print(f"[turn1] sample: kind={sample.get('kind')} runId={sample.get('runId')} turnIdx={sample.get('turnIdx')}")
        if sample.get("runId") != "r-1":
            print("[ERROR] turn 1 sanity check failed — runId not 'r-1'")
            return 1

    # Step 3: try mutation mechanisms
    print("\n--- Step 3: mutate sessionState to {runId: r-2, turnIdx: 1, attempt: 1} ---")
    new_state = {"runId": "r-2", "turnIdx": 1, "attempt": 1}
    mutation_results: list[tuple[str, dict]] = []

    mechanisms = [
        ("a:PATCH-updateMask-sessionState", lambda: _try_patch_sessionstate(sid, new_state)),
        ("b:appendEvent-stateDelta", lambda: _try_append_event(sid, new_state)),
        ("c:SDK-update_session", lambda: _try_sdk_update(remote, new_state, sid)),
    ]
    succeeded_mechanism = None
    for name, fn in mechanisms:
        print(f"\n[{name}] trying...")
        ok, info = fn()
        mutation_results.append((name, info))
        print(f"[{name}] success={ok} info={json.dumps(info)[:400]}")
        if ok:
            succeeded_mechanism = name
            break

    if not succeeded_mechanism:
        print("\n[FAIL] No mutation mechanism succeeded at HTTP layer")
        for name, info in mutation_results:
            print(f"  {name}: {json.dumps(info)[:300]}")
        return 1

    # Step 4: verify state actually mutated
    print(f"\n--- Step 4: re-read session state via :getSession ---")
    await asyncio.sleep(2)  # give the platform a moment
    actual = _get_session_state(sid)
    print(f"[getSession] sessionState={actual}")
    if actual.get("runId") != "r-2" or actual.get("turnIdx") != 1:
        print(f"[INCONCLUSIVE] mechanism {succeeded_mechanism} returned 2xx but state didn't change")
        return 2

    # Step 5: turn 2 invoke
    print("\n--- Step 5: turn 2 invoke ---")
    _write_marker(fs, sid, "turn2_started_at")
    turn2_started_wall = time.time()
    turn2_invocation_id: str | None = None
    n2 = 0
    async for ev in remote.async_stream_query(
        user_id="r31", session_id=sid, message="fetch:https://example.com/"
    ):
        n2 += 1
        if turn2_invocation_id is None:
            turn2_invocation_id = ev.get("invocation_id")
            print(f"[turn2] invocation_id={turn2_invocation_id}")
    print(f"[turn2] {n2} events")

    await asyncio.sleep(3)

    # Filter by turn 2's invocation_id
    all_docs = list(fs.collection("probe_runs").document(sid).collection("events").stream())
    turn2_docs = [d for d in all_docs if (d.to_dict() or {}).get("invocation_id") == turn2_invocation_id]
    print(f"\n[turn2] {len(turn2_docs)} plugin docs for invocation_id={turn2_invocation_id}")

    # Verify they carry the new metadata
    fail_count = 0
    for d in turn2_docs:
        data = d.to_dict()
        ok = data.get("runId") == "r-2" and data.get("turnIdx") == 1
        flag = "✓" if ok else "✗"
        print(f"  {flag} kind={data.get('kind')} runId={data.get('runId')} turnIdx={data.get('turnIdx')} attempt={data.get('attempt')}")
        if not ok:
            fail_count += 1

    if not turn2_docs:
        print("\n[FAIL] no turn 2 plugin docs found with invocation_id match")
        return 1

    if fail_count == 0:
        print(f"\n[PASS] all {len(turn2_docs)} turn-2 docs carry runId=r-2, turnIdx=1")
        print(f"[PASS] mechanism that worked: {succeeded_mechanism}")
        return 0
    else:
        print(f"\n[FAIL] {fail_count}/{len(turn2_docs)} turn-2 docs DON'T carry the mutated state")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
