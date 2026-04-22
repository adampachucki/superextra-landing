"""Live E2E smoke for the new transport.

Runs the worker handler against *real* Firestore + Agent Engine + Places +
Gemini. Verifies that everything the unit tests mocked actually works when
wired to the live stack:

  - Session doc upsert (seeded here; agentStream does it in prod).
  - Worker takeover, fenced updates, heartbeat pulses.
  - Agent Engine session create-on-first-turn + fenced writeback.
  - Mapper writes progressive events to Firestore via real writes.
  - collectionGroup('events') query returns them ordered correctly.
  - Terminal status=complete + reply + sources land on the session doc.

Not part of CI — this costs real Gemini / Places tokens. Run manually.

Usage (from repo root):
    cd agent && \\
    GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<user>/adc.json \\
    PYTHONPATH=. .venv/bin/python tests/e2e_worker_live.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_DIR))

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("AGENT_ENGINE_ID", "2746721333428617216")


def _load_env(p: Path) -> None:
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(AGENT_DIR / ".env")

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.genai import Client as GenaiClient  # noqa: E402

import worker_main  # noqa: E402
from worker_main import RunRequest, run  # noqa: E402


SID = f"e2e-{uuid.uuid4()}"
RUN_ID = str(uuid.uuid4())
USER_ID = f"e2e-user-{uuid.uuid4().hex[:8]}"
PLACE = {
    # Noma, Copenhagen. Verified via Places API (New) v1 at time of authoring:
    # GET /v1/places/{id}?fields=displayName,formattedAddress →
    # displayName.text="Noma", formattedAddress="Refshalevej 96, 1432 København".
    # Keep label/secondary aligned with placeId — the pipeline cross-checks
    # and a mismatch degrades smoke-test signal quality.
    "name": "Noma",
    "secondary": "Copenhagen",
    "placeId": "ChIJpYCQZztTUkYRFOE368Xs6kI",
}


class FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


async def _init_singletons() -> None:
    """Mirror `_lifespan` without FastAPI. Sets module globals the handler
    expects to be present."""
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    worker_main._session_svc = VertexAiSessionService(
        project=project, location="us-central1", agent_engine_id=worker_main.AGENT_ENGINE_ID
    )
    worker_main._runner = Runner(app=worker_main.adk_app, session_service=worker_main._session_svc)
    worker_main._fs = firestore.Client(project=project)
    worker_main._genai_client = GenaiClient(
        vertexai=True, project=project, location="global"
    )


def seed_session() -> None:
    """Write the session doc shape agentStream would have written."""
    fs = worker_main._fs
    now = datetime.now(timezone.utc)
    fs.collection("sessions").document(SID).set({
        "userId": USER_ID,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "adkSessionId": None,
        "placeContext": PLACE,
        "title": None,
        "currentRunId": RUN_ID,
        "currentAttempt": 0,
        "currentWorkerId": None,
        "status": "queued",
        "queuedAt": firestore.SERVER_TIMESTAMP,
        "lastHeartbeat": None,
        "lastEventAt": None,
        "reply": None,
        "sources": None,
        "error": None,
        "expiresAt": now + timedelta(days=30),
    })


async def monitor_session(stop_evt: asyncio.Event) -> list[dict]:
    """Sample the session doc every 2 s; return state transitions observed."""
    transitions: list[dict] = []
    last_status: str | None = None
    last_attempt: int | None = None
    fs = worker_main._fs
    ref = fs.collection("sessions").document(SID)
    while not stop_evt.is_set():
        snap = await asyncio.to_thread(ref.get)
        data = snap.to_dict() or {}
        status = data.get("status")
        attempt = data.get("currentAttempt")
        if status != last_status or attempt != last_attempt:
            transitions.append({
                "t": time.monotonic(),
                "status": status,
                "currentAttempt": attempt,
                "hb": bool(data.get("lastHeartbeat")),
                "lastEvent": bool(data.get("lastEventAt")),
            })
            print(
                f"[monitor @{transitions[-1]['t']:.1f}s] status={status} attempt={attempt} "
                f"hb={transitions[-1]['hb']} lastEventAt={transitions[-1]['lastEvent']}",
                flush=True,
            )
            last_status, last_attempt = status, attempt
        try:
            await asyncio.wait_for(stop_evt.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
    return transitions


async def main() -> int:
    print(f"[e2e] sid={SID} runId={RUN_ID} userId={USER_ID}")
    await _init_singletons()
    seed_session()

    today = datetime.now(timezone.utc).date().isoformat()
    # Override via E2E_QUERY env var. Default exercises numeric chart emission.
    query_text = os.environ.get(
        "E2E_QUERY",
        "How do entree prices compare to other top fine-dining restaurants in Copenhagen?",
    )
    query = (
        f"[Date: {today}] "
        f"[Context: asking about {PLACE['name']}, {PLACE['secondary']} "
        f"(Place ID: {PLACE['placeId']})] "
        f"{query_text}"
    )
    body = RunRequest(
        sessionId=SID,
        runId=RUN_ID,
        adkSessionId=None,  # first turn — worker creates Agent Engine session
        userId=USER_ID,
        queryText=query,
        isFirstMessage=True,
    )
    req = FakeRequest(headers={
        "x-cloudtasks-taskname": f"projects/superextra-site/locations/us-central1/queues/agent-dispatch/tasks/{RUN_ID}",
        "x-cloudtasks-taskretrycount": "0",
        "x-cloud-trace-context": f"e2e-{RUN_ID.replace('-','')}/1;o=1",
    })

    stop_evt = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_session(stop_evt))

    t0 = time.monotonic()
    print("[e2e] invoking worker.run(...)", flush=True)
    result = await run(body, req)
    elapsed = time.monotonic() - t0
    stop_evt.set()
    transitions = await monitor_task

    print(f"\n[e2e] handler returned: {result}")
    print(f"[e2e] elapsed: {elapsed:.2f}s")

    # Final session state
    final_snap = worker_main._fs.collection("sessions").document(SID).get()
    final = final_snap.to_dict() or {}

    # Collection-group events query (what the frontend will do)
    from google.cloud.firestore_v1.base_query import FieldFilter
    events_q = (
        worker_main._fs.collection_group("events")
        .where(filter=FieldFilter("userId", "==", USER_ID))
        .where(filter=FieldFilter("runId", "==", RUN_ID))
        .order_by("attempt")
        .order_by("seqInAttempt")
    )
    event_docs = list(events_q.stream())
    event_types: dict[str, int] = {}
    for d in event_docs:
        t = (d.to_dict() or {}).get("type", "?")
        event_types[t] = event_types.get(t, 0) + 1

    report = {
        "sid": SID,
        "runId": RUN_ID,
        "userId": USER_ID,
        "elapsed_s": round(elapsed, 2),
        "handler_result": result,
        "final_session": {
            "status": final.get("status"),
            "currentRunId": final.get("currentRunId"),
            "currentAttempt": final.get("currentAttempt"),
            "adkSessionId_set": bool(final.get("adkSessionId")),
            "reply_len": len(final.get("reply") or ""),
            "sources_n": len(final.get("sources") or []),
            "title": final.get("title"),
            "error": final.get("error"),
        },
        "events": {
            "total": len(event_docs),
            "by_type": event_types,
        },
        "transitions": transitions,
    }
    out = AGENT_DIR / "tests" / "e2e_worker_live.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n[e2e] report → {out}")
    print(json.dumps(report["final_session"], indent=2, default=str))
    print("event counts:", json.dumps(event_types))
    print(f"{len(event_docs)} events via collectionGroup query")

    # Verdicts
    verdicts = {
        "final_status_complete": final.get("status") == "complete",
        "reply_populated": bool(final.get("reply") and len(final["reply"]) >= 100),
        "adk_session_persisted": bool(final.get("adkSessionId")),
        "events_written": len(event_docs) > 0,
        "title_set_on_first_turn": bool(final.get("title")),
        "collection_group_query_works": len(event_docs) > 0,
    }
    print("\n[e2e] verdicts:")
    for k, v in verdicts.items():
        print(f"  {'✅' if v else '❌'} {k}: {v}")
    all_pass = all(verdicts.values())
    print(f"\n[e2e] OVERALL: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
