"""Spike D — Firestore query + composite index + onSnapshot first-callback semantics.

Verifies:
  1. `firestore.indexes.json` declaring COLLECTION_GROUP on `events` covers the
     subcollection query we plan to run from the client.
  2. Running the query without the index returns a clear FAILED_PRECONDITION
     error with a direct index-creation link.
  3. `onSnapshot` (simulated via Firestore's async `on_snapshot`) delivers the
     full current event list on the first callback, ordered correctly by
     `(runId, attempt, seqInAttempt)`.
  4. The query filters cleanly by `runId` (multi-turn event isolation).

We don't verify rules here (client SDK auth simulation is clunky in Python).
Rules verification belongs to Spike F with the Firebase emulator + rules-unit-testing.

Usage:
    export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<user>/adc.json
    .venv/bin/python spikes/firestore_query_spike.py

Cleanup: the spike writes to `sessions/spike-d-<timestamp>` and deletes at the end.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
sys.path.insert(0, str(AGENT_DIR))

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

PROJECT = "superextra-site"


def _write_events(db, sid: str, user_id: str) -> None:
    """Write 30 events: 20 for runId=X across 2 attempts, 10 for runId=Y."""
    coll = db.collection("sessions").document(sid).collection("events")

    # Create parent session doc (required for rules check, not strictly for queries)
    db.collection("sessions").document(sid).set({
        "userId": user_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "queuedAt": firestore.SERVER_TIMESTAMP,
        "status": "running",
        "currentRunId": "X",
        "currentAttempt": 2,
        "expiresAt": firestore.Timestamp.from_datetime(
            __import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(hours=2)
        ) if hasattr(firestore, "Timestamp") else None,
        "_spike": True,
    })

    batch = db.batch()
    now = firestore.SERVER_TIMESTAMP

    # runId=X, attempt=1, seq 1..10
    for i in range(1, 11):
        ref = coll.document()
        batch.set(ref, {
            "userId": user_id,
            "runId": "X", "attempt": 1, "seqInAttempt": i,
            "type": "progress", "data": {"stage": f"a1-step-{i}"},
            "ts": now,
        })
    # runId=X, attempt=2, seq 1..10
    for i in range(1, 11):
        ref = coll.document()
        batch.set(ref, {
            "userId": user_id,
            "runId": "X", "attempt": 2, "seqInAttempt": i,
            "type": "progress", "data": {"stage": f"a2-step-{i}"},
            "ts": now,
        })
    # runId=Y, attempt=1, seq 1..10 (different turn — should be filtered out)
    for i in range(1, 11):
        ref = coll.document()
        batch.set(ref, {
            "userId": user_id,
            "runId": "Y", "attempt": 1, "seqInAttempt": i,
            "type": "progress", "data": {"stage": f"y-step-{i}"},
            "ts": now,
        })

    batch.commit()
    print(f"[spike-d] wrote 30 events under sessions/{sid}/events", flush=True)


def _run_subcollection_query(db, sid: str, run_id: str) -> list:
    coll = db.collection("sessions").document(sid).collection("events")
    q = (
        coll.where(filter=FieldFilter("runId", "==", run_id))
            .order_by("attempt")
            .order_by("seqInAttempt")
    )
    docs = list(q.stream())
    return [d.to_dict() for d in docs]


def _snapshot_first_callback_test(db, sid: str, run_id: str):
    """Simulate onSnapshot: register a listener, wait for the first snapshot,
    verify it delivers the full current state in one shot."""
    import threading
    coll = db.collection("sessions").document(sid).collection("events")
    q = (
        coll.where(filter=FieldFilter("runId", "==", run_id))
            .order_by("attempt")
            .order_by("seqInAttempt")
    )

    first_snapshot: list = []
    done = threading.Event()

    def on_snapshot(col_snapshot, changes, read_time):
        if done.is_set():
            return
        docs = [{**d.to_dict(), "_change": None} for d in col_snapshot]
        # record the changes — should all be "ADDED" for the first callback
        for c in changes:
            docs_i = next((i for i, d in enumerate(docs)
                           if d.get("data", {}).get("stage") == c.document.to_dict().get("data", {}).get("stage")), None)
            if docs_i is not None:
                docs[docs_i]["_change"] = c.type.name
        first_snapshot[:] = docs
        done.set()

    watch = q.on_snapshot(on_snapshot)
    done.wait(timeout=10)
    watch.unsubscribe()
    return first_snapshot


def _cleanup(db, sid: str) -> None:
    # Delete all events in the subcollection, then the parent doc
    events_ref = db.collection("sessions").document(sid).collection("events")
    deleted = 0
    while True:
        batch = db.batch()
        docs = list(events_ref.limit(100).stream())
        if not docs:
            break
        for d in docs:
            batch.delete(d.reference)
            deleted += 1
        batch.commit()
    db.collection("sessions").document(sid).delete()
    print(f"[spike-d] cleanup: deleted {deleted} events + session {sid}", flush=True)


def main() -> None:
    sid = f"spike-d-{int(time.time())}"
    user_id = "spike-user"

    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT)
    db = firestore.Client(project=PROJECT)
    print(f"[spike-d] project={PROJECT} sid={sid}", flush=True)

    try:
        # Step 1: write events
        _write_events(db, sid, user_id)

        # Step 2: query without index — expect FAILED_PRECONDITION first time if
        # index doesn't exist. We might already have the index from earlier spikes,
        # so we tolerate success too.
        print("\n[spike-d] Step 2: run subcollection query (where runId==X, orderBy attempt, seqInAttempt)", flush=True)
        try:
            results = _run_subcollection_query(db, sid, "X")
            print(f"[spike-d]   → query returned {len(results)} docs (index exists)", flush=True)
            query_worked = True
            error_link = None
        except Exception as e:
            msg = str(e)
            print(f"[spike-d]   → query FAILED: {type(e).__name__}", flush=True)
            # Extract the index-creation link from the error
            if "https://console.firebase.google.com" in msg or "https://console.cloud.google.com" in msg:
                for tok in msg.split():
                    if tok.startswith("http"):
                        error_link = tok.rstrip(".")
                        break
            print(f"[spike-d]   → index creation link: {error_link}", flush=True)
            query_worked = False
            results = []

        # Step 3: verify ordering and filter
        if query_worked:
            print("\n[spike-d] Step 3: verify query correctness", flush=True)
            print(f"  - count: {len(results)} (expected 20 — 10 per attempt for runId=X)")
            stages = [(r.get("attempt"), r.get("seqInAttempt"), r.get("data", {}).get("stage")) for r in results]
            ordering_ok = True
            for i in range(1, len(stages)):
                if (stages[i][0], stages[i][1]) <= (stages[i-1][0], stages[i-1][1]):
                    ordering_ok = False
                    break
            print(f"  - ordering by (attempt, seqInAttempt): {'OK' if ordering_ok else 'WRONG'}")
            other_runid = any(r.get("runId") != "X" for r in results)
            print(f"  - no runId=Y leaks: {'OK' if not other_runid else 'LEAKED'}")

            # Step 4: onSnapshot first-callback
            print("\n[spike-d] Step 4: first-callback delivery test", flush=True)
            first_snap = _snapshot_first_callback_test(db, sid, "X")
            print(f"  - first snapshot delivered {len(first_snap)} docs (expected 20)")
            if first_snap:
                changes = [d.get("_change") for d in first_snap]
                # all should be ADDED on first callback
                added_only = all(c in ("ADDED", None) for c in changes)
                print(f"  - all changes are ADDED (or unmapped): {'OK' if added_only else 'NOT-OK'}")

        print("\n[spike-d] === VERDICT ===")
        print(f"  (1) Composite index covers subcollection query   : {'PASS' if query_worked else 'FAIL (need index)'}")
        if query_worked:
            print(f"  (2) Query orders correctly                       : {'PASS' if ordering_ok else 'FAIL'}")
            print(f"  (3) Query filters by runId                       : {'PASS' if not other_runid else 'FAIL'}")
            print(f"  (4) First-snapshot delivers full state           : {'PASS' if len(first_snap) == 20 else 'FAIL'}")

    finally:
        _cleanup(db, sid)


if __name__ == "__main__":
    main()
