"""R3.2 — verify Cloud Function handoff with streamQuery.

Plan: docs/gear-probe-plan-round3-2026-04-26.md §R3.2.

GATE variant: probeHandoffAbort
  - Reads first NDJSON line, then explicit reader.cancel() + AbortController.abort(),
    then res.status(202).send().
  - PASS if Agent Runtime continues and after_run lands >60s after cf_returned_at.

DIAGNOSTIC variant: probeHandoffLeaveOpen
  - Reads first NDJSON line, returns 202 with fetch still pending.
  - Result is informative-only (Firebase docs warn: undefined behaviour).

Sequence per variant:
1. Create session via REST :createSession?sessionId=se-r32-{variant}-{ts}
   on the lifecycle probe.
2. POST to deployed CF URL with {sessionId}.
3. Capture CF response timestamp.
4. Watch Firestore probe_runs/{sid}/events/ for full 8-doc shape.
5. Compute gap between cf_returned_at marker and after_run doc timestamp.

Exit codes (gate variant only — leave-open is informative):
  0 = PASS — after_run.ts > cf_returned_at + 60s, full 8 docs landed
  1 = FAIL — after_run never landed within 10 min, OR <5 event docs
  2 = INCONCLUSIVE — gap <60s, re-run with longer agent
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import google.auth
import google.auth.transport.requests
import requests
from google.cloud import firestore

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
LIFECYCLE_RESOURCE = "projects/907466498524/locations/us-central1/reasoningEngines/329317476414259200"

# Function URLs follow Firebase v2 default pattern. Confirmed format:
# https://<region>-<project>.cloudfunctions.net/<function-name> OR
# https://<region>-<project>.run.app for Gen2 deployed via firebase-functions
# We'll discover the URL from gcloud after deploy if needed.


def _token() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _create_session(sid: str, user_id: str) -> None:
    r = requests.post(
        f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{LIFECYCLE_RESOURCE}/sessions?sessionId={sid}",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json={"userId": user_id, "sessionState": {"runId": "r-r32", "turnIdx": 0, "attempt": 1}},
        timeout=30,
    )
    print(f"[create_session] status={r.status_code} body={r.text[:200]}")
    r.raise_for_status()


def _gcloud_function_url(name: str) -> str:
    """Discover the deployed Gen 2 function URL via gcloud."""
    import subprocess
    out = subprocess.run(
        [
            "gcloud", "functions", "describe", name,
            "--region=us-central1",
            "--project=superextra-site",
            "--gen2",
            "--format=value(serviceConfig.uri)",
        ],
        capture_output=True, text=True, check=False,
        env={**os.environ, "GOOGLE_APPLICATION_CREDENTIALS": "/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json"},
    )
    if out.returncode != 0:
        raise RuntimeError(f"gcloud describe failed: {out.stderr}")
    url = out.stdout.strip()
    if not url:
        raise RuntimeError(f"no URL for function {name}")
    return url


def _invoke_cf(url: str, sid: str) -> tuple[float, dict]:
    """POST to the CF, time it, return (wall_time_returned, response_json)."""
    t0 = time.time()
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"sessionId": sid},
        timeout=120,  # CF can wait up to 90s for first NDJSON line
    )
    elapsed = time.time() - t0
    print(f"[cf-invoke] status={r.status_code} elapsed={elapsed:.2f}s body={r.text[:300]}")
    r.raise_for_status()
    return time.time(), r.json()


def _watch_for_after_run(fs: firestore.Client, sid: str, timeout_s: int = 600) -> tuple[dict | None, dict, dict]:
    """Poll Firestore until after_run lands or timeout. Return
    (after_run_doc, all_kinds_count, cf_returned_at_marker)."""
    deadline = time.monotonic() + timeout_s
    poll = 10
    cf_marker = None
    while time.monotonic() < deadline:
        events = list(fs.collection("probe_runs").document(sid).collection("events").stream())
        kinds = {}
        after_run_doc = None
        for d in events:
            data = d.to_dict() or {}
            k = data.get("kind")
            kinds[k] = kinds.get(k, 0) + 1
            if k == "after_run":
                after_run_doc = data
        if cf_marker is None:
            mref = fs.collection("probe_runs").document(sid).collection("markers").document("cf_returned_at").get()
            if mref.exists:
                cf_marker = mref.to_dict()
                print(f"[watch] cf_returned_at marker: {cf_marker}")
        elapsed = timeout_s - (deadline - time.monotonic())
        print(f"[watch] elapsed={elapsed:.0f}s kinds={kinds}")
        if after_run_doc:
            return after_run_doc, kinds, cf_marker or {}
        time.sleep(poll)
    return None, kinds, cf_marker or {}


def run(variant: str) -> int:
    fs = firestore.Client(project=PROJECT)

    fn_name = "probeHandoffAbort" if variant == "abort" else "probeHandoffLeaveOpen"
    print(f"\n=== R3.2 variant={variant} fn={fn_name} ===")

    # Session ID must match [a-z][a-z0-9-]*[a-z0-9] — underscores rejected
    sid_variant = variant.replace("_", "-")
    sid = f"se-r32-{sid_variant}-{int(time.time())}"
    print(f"sid={sid}")

    _create_session(sid, f"r32-{variant}")
    url = _gcloud_function_url(fn_name)
    print(f"function URL: {url}")

    cf_returned_at_wall, cf_response = _invoke_cf(url, sid)
    print(f"cf_returned_at_wall={cf_returned_at_wall} ({time.strftime('%H:%M:%S', time.localtime(cf_returned_at_wall))})")

    print(f"\n--- Watching Firestore for after_run (timeout 10 min) ---")
    after_run, kinds, cf_marker = _watch_for_after_run(fs, sid, timeout_s=600)

    if after_run is None:
        print(f"\n[FAIL/{variant}] no after_run within 10 min. Final kinds={kinds}")
        return 1

    if not cf_marker.get("ts"):
        print(f"[ERROR] cf_returned_at marker missing")
        return 1

    cf_ts = cf_marker["ts"]
    ar_ts = after_run["ts"]
    gap = (ar_ts - cf_ts).total_seconds()
    print(f"\n[result/{variant}] cf_returned_at={cf_ts}")
    print(f"[result/{variant}] after_run.ts ={ar_ts}")
    print(f"[result/{variant}] gap          ={gap:.1f}s")
    print(f"[result/{variant}] kinds        ={kinds}")

    event_count = kinds.get("event", 0)
    if event_count < 5:
        print(f"\n[FAIL/{variant}] only {event_count} event docs (expected 5 for 5-min DeterministicSlowAgent)")
        return 1

    if variant == "abort":
        if gap > 60:
            print(f"\n[PASS/{variant}] gap {gap:.1f}s > 60s — Agent Runtime continued past explicit CF disconnect")
            return 0
        else:
            print(f"\n[INCONCLUSIVE/{variant}] gap {gap:.1f}s <= 60s — re-run with longer agent")
            return 2
    else:
        # Leave-open is diagnostic only — record the result, not a gate
        verdict = "after_run-landed" if gap > 0 else "after_run-but-too-fast"
        print(f"\n[DIAGNOSTIC/{variant}] {verdict}; gap={gap:.1f}s")
        # Treat any after_run delivery as informational pass
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["abort", "leave_open"], required=True)
    args = ap.parse_args()
    sys.exit(run(args.variant))


if __name__ == "__main__":
    main()
