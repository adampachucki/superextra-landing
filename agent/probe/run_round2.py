"""Round-2 test runner — invokes deployed probes and captures findings.

Usage:
  python -m probe.run_round2 <test>

Tests:
  outbound       — R2.1 outbound HTTPS (kitchen probe)
  secrets        — R2.2 SecretRef + plain env vars (kitchen probe)
  multiturn      — R2.3 multi-turn session.state semantics (kitchen probe)
  logs           — R2.6 logs visibility (kitchen probe)
  gemini3        — R2.4 Gemini 3.1 routing (gemini3 probe)
  prodshape      — R2.5 ParallelAgent + output_key chains (prod_shape probe)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import vertexai
from vertexai import agent_engines
from google.cloud import firestore

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
STATE_FILE = Path(__file__).parent / "deployed_resources.json"

vertexai.init(project=PROJECT, location=LOCATION)
fs = firestore.Client(project=PROJECT)


def _resource(flavour: str) -> str:
    state = json.loads(STATE_FILE.read_text())
    if flavour not in state:
        raise SystemExit(f"flavour {flavour!r} not deployed; run deploy.py --flavour {flavour}")
    return state[flavour]


def _last_event_text(events: list) -> str:
    for d in events:
        data = d.to_dict()
        if data.get("kind") == "after_run":
            continue
        author = data.get("event_author")
        if author:
            # Look for tool response in event_id to find the text
            return f"author={author} ev_id={data.get('event_id')}"
    return "(no event text)"


# ---------------------------------------------------------------------------
# R2.1 — outbound HTTPS
# ---------------------------------------------------------------------------

async def test_outbound() -> None:
    print("=== R2.1 — outbound HTTPS ===")
    remote = agent_engines.get(_resource("kitchen"))
    urls = [
        ("https://places.googleapis.com/", "google"),
        ("https://api.apify.com/v2/", "third-party"),
        ("https://example.com/", "generic"),
    ]
    for url, label in urls:
        sess = await remote.async_create_session(user_id=f"r21-{label}")
        sid = sess["id"]
        n = 0
        last_event_text = None
        async for ev in remote.async_stream_query(
            user_id=f"r21-{label}", session_id=sid, message=f"fetch:{url}"
        ):
            n += 1
            parts = ev.get("content", {}).get("parts") or []
            for p in parts:
                if "function_response" in p:
                    last_event_text = p["function_response"].get("response", {})
                elif "text" in p:
                    last_event_text = p.get("text")
        print(f"  {label} ({url}): events={n} response={str(last_event_text)[:200]}")


# ---------------------------------------------------------------------------
# R2.2 — env vars + SecretRef
# ---------------------------------------------------------------------------

async def test_secrets() -> None:
    print("=== R2.2 — env vars + SecretRef ===")
    remote = agent_engines.get(_resource("kitchen"))
    for var_name in ["PLAIN_VAR", "SECRET_VAR", "GOOGLE_CLOUD_PROJECT", "MISSING_VAR"]:
        sess = await remote.async_create_session(user_id=f"r22-{var_name}")
        sid = sess["id"]
        got_value = "(no response)"
        async for ev in remote.async_stream_query(
            user_id=f"r22-{var_name}", session_id=sid, message=f"env:{var_name}"
        ):
            for p in (ev.get("content", {}).get("parts") or []):
                if "function_response" in p:
                    got_value = p["function_response"].get("response", {})
        print(f"  {var_name}: {got_value}")


# ---------------------------------------------------------------------------
# R2.3 — multi-turn session.state semantics
# ---------------------------------------------------------------------------

async def test_multiturn() -> None:
    print("=== R2.3 — multi-turn session.state ===")
    remote = agent_engines.get(_resource("kitchen"))
    sid_base = f"se-multiturn-{int(time.time())}"

    # Use REST createSession for custom ID
    import requests, google.auth, google.auth.transport.requests
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    resource_name = _resource("kitchen")
    r = requests.post(
        f"https://us-central1-aiplatform.googleapis.com/v1beta1/{resource_name}/sessions?sessionId={sid_base}",
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        json={"userId": "r23", "sessionState": {"runId": "r-mt", "attempt": 1, "turnIdx": 0, "preexisting_key": "set_at_create"}},
        timeout=30,
    )
    print(f"  REST createSession: {r.status_code}")
    if r.status_code >= 300:
        print(f"  body: {r.text[:300]}")
        return
    print(f"  using sid={sid_base}")

    # Turn 1
    print("  turn 1: invoke with 'turn1' prompt")
    n = 0
    async for ev in remote.async_stream_query(
        user_id="r23", session_id=sid_base, message="turn1"
    ):
        n += 1
    print(f"  turn 1: {n} events")

    # Read session state after turn 1
    r = requests.get(
        f"https://us-central1-aiplatform.googleapis.com/v1beta1/{resource_name}/sessions/{sid_base}",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=30,
    )
    sess = r.json()
    print(f"  state after turn 1: {sess.get('sessionState')}")

    # Turn 2
    print("  turn 2: invoke with 'turn2' prompt")
    n = 0
    async for ev in remote.async_stream_query(
        user_id="r23", session_id=sid_base, message="turn2"
    ):
        n += 1
    print(f"  turn 2: {n} events")

    r = requests.get(
        f"https://us-central1-aiplatform.googleapis.com/v1beta1/{resource_name}/sessions/{sid_base}",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=30,
    )
    sess = r.json()
    print(f"  state after turn 2: {sess.get('sessionState')}")

    docs = list(fs.collection("probe_runs").document(sid_base).collection("events").stream())
    print(f"  Firestore docs total across both turns: {len(docs)}")
    by_kind = {}
    for d in docs:
        k = d.to_dict().get("kind")
        by_kind[k] = by_kind.get(k, 0) + 1
    print(f"  by kind: {by_kind}")
    # Check what runId values appear — if turn 2 events show runId='r-mt', state propagated
    run_ids = set(d.to_dict().get("runId") for d in docs)
    print(f"  unique runId values seen: {run_ids}")


# ---------------------------------------------------------------------------
# R2.6 — logs visibility
# ---------------------------------------------------------------------------

async def test_logs() -> None:
    print("=== R2.6 — logs visibility ===")
    remote = agent_engines.get(_resource("kitchen"))
    resource_name = _resource("kitchen")
    re_id = resource_name.split("/")[-1]
    print(f"  reasoning_engine_id={re_id}")

    sess = await remote.async_create_session(user_id="r26")
    sid = sess["id"]
    print("  invoking to produce log markers...")
    async for ev in remote.async_stream_query(
        user_id="r26", session_id=sid, message="fetch:https://example.com/"
    ):
        pass
    print("  invocation done; waiting 90s for log propagation...")
    time.sleep(90)

    # Try multiple gcloud queries
    queries = [
        f'resource.labels.reasoning_engine_id="{re_id}"',
        f'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="{re_id}"',
        f'resource.type="aiplatform.googleapis.com/ReasoningEngine"',
    ]
    for q in queries:
        print(f"  query: {q}")
        result = subprocess.run(
            ["gcloud", "logging", "read", q, "--project=superextra-site", "--freshness=5m", "--limit=5", "--format=value(timestamp,severity,textPayload,jsonPayload.message)"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "GOOGLE_APPLICATION_CREDENTIALS": "/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json"},
        )
        out = result.stdout.strip()
        if out:
            print(f"  RESULTS:\n{out[:1500]}")
            return
        print(f"  (empty)")
    print("  RESULT: no log markers found via any query")


# ---------------------------------------------------------------------------
# R2.4 — Gemini 3.1 routing
# ---------------------------------------------------------------------------

async def test_gemini3() -> None:
    print("=== R2.4 — Gemini 3.1 routing ===")
    remote = agent_engines.get(_resource("gemini3"))
    sess = await remote.async_create_session(user_id="r24")
    sid = sess["id"]
    print(f"  invoking gemini-3.1-flash via per-agent api_client(location='global') override...")
    n = 0
    last_text = None
    error = None
    try:
        async for ev in remote.async_stream_query(
            user_id="r24", session_id=sid, message="hi"
        ):
            n += 1
            for p in (ev.get("content", {}).get("parts") or []):
                if "text" in p:
                    last_text = p["text"]
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:500]}"
    if error:
        print(f"  ERROR: {error}")
        print("  → Gemini 3.1 override does NOT survive deploy. Migration blocker if no workaround.")
    elif last_text:
        print(f"  events={n}; last text={last_text!r}")
        print("  → Gemini 3.1 override survives deploy. Migration path clear.")
    else:
        print(f"  events={n}; no text response. Inconclusive.")


# ---------------------------------------------------------------------------
# R2.5 — production agent shape
# ---------------------------------------------------------------------------

async def test_prodshape() -> None:
    print("=== R2.5 — production agent shape (ParallelAgent + output_key) ===")
    remote = agent_engines.get(_resource("prod_shape"))
    sess = await remote.async_create_session(user_id="r25")
    sid = sess["id"]
    print("  invoking SequentialAgent[ParallelAgent[a,b], synth]...")
    n = 0
    authors = []
    async for ev in remote.async_stream_query(
        user_id="r25", session_id=sid, message="run"
    ):
        n += 1
        a = ev.get("author")
        if a:
            authors.append(a)
        sd = ev.get("actions", {}).get("state_delta") or {}
        if sd:
            print(f"  event {n} author={a} state_delta={sd}")
    print(f"  events={n} authors={authors}")
    # Read final state
    import requests, google.auth, google.auth.transport.requests
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    resource_name = _resource("prod_shape")
    r = requests.get(
        f"https://us-central1-aiplatform.googleapis.com/v1beta1/{resource_name}/sessions/{sid}",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=30,
    )
    print(f"  final session.state: {r.json().get('sessionState')}")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TESTS = {
    "outbound": test_outbound,
    "secrets": test_secrets,
    "multiturn": test_multiturn,
    "logs": test_logs,
    "gemini3": test_gemini3,
    "prodshape": test_prodshape,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in TESTS:
        print("usage: python -m probe.run_round2 <test>")
        print("tests:", ", ".join(TESTS.keys()))
        sys.exit(2)
    asyncio.run(TESTS[sys.argv[1]]())


if __name__ == "__main__":
    main()
