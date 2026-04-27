"""Verify probe completion via Firestore.

Polls `probe_runs/{sid}/events` for an `after_run` doc and verifies its
timestamp is at least `--min-gap-seconds` after the `caller_killed_at`
marker doc (also in Firestore).

Exit codes:
  0 = pass: after_run exists AND ts > caller_killed_at + min_gap
  1 = fail: no after_run within --timeout seconds
  2 = inconclusive: after_run exists but ts <= caller_killed_at (run
      finished before kill landed; re-run with longer agent)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from google.cloud import firestore

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", required=True)
    ap.add_argument("--timeout", type=int, default=600,
                    help="seconds to wait for after_run after kill")
    ap.add_argument("--min-gap-seconds", type=int, default=60,
                    help="required time gap between caller_killed_at and after_run.ts")
    ap.add_argument("--require-kill-marker", action="store_true",
                    help="require a caller_killed_at marker; without it (no-kill mode) just check after_run exists")
    args = ap.parse_args()

    fs = firestore.Client(project=PROJECT)
    sid_doc = fs.collection("probe_runs").document(args.sid)
    events_col = sid_doc.collection("events")
    markers_col = sid_doc.collection("markers")

    killed_at = None
    if args.require_kill_marker:
        kill_doc = markers_col.document("caller_killed_at").get()
        if not kill_doc.exists:
            print(f"[watch] no caller_killed_at marker for sid={args.sid}", file=sys.stderr)
            return 1
        killed_at = kill_doc.get("ts")
        print(f"[watch] caller_killed_at = {killed_at}")

    deadline = time.monotonic() + args.timeout
    poll_interval = 5

    while time.monotonic() < deadline:
        # Find after_run doc(s).
        after_runs = list(events_col.where("kind", "==", "after_run").stream())
        if after_runs:
            doc = after_runs[0]
            data = doc.to_dict()
            ar_ts = data.get("ts")
            print(f"[watch] after_run found ts={ar_ts}")

            if not args.require_kill_marker:
                print("[watch] PASS (no-kill mode — after_run exists)")
                return 0

            if killed_at is None:
                print("[watch] FAIL (kill marker missing)")
                return 1

            # Compute gap. Both are Firestore Timestamps.
            try:
                gap = (ar_ts - killed_at).total_seconds()
            except Exception as e:
                print(f"[watch] FAIL — could not compute timestamp gap: {e}")
                return 1

            print(f"[watch] gap = {gap:.1f}s (required: > {args.min_gap_seconds}s)")
            if gap > args.min_gap_seconds:
                print("[watch] PASS — runtime continued past the kill")
                return 0
            else:
                print("[watch] INCONCLUSIVE — after_run landed before/too-close-to kill")
                return 2

        elapsed = args.timeout - (deadline - time.monotonic())
        print(f"[watch] no after_run yet (elapsed {elapsed:.0f}s/{args.timeout}s)")
        time.sleep(poll_interval)

    print(f"[watch] FAIL — no after_run within {args.timeout}s of poll start")
    return 1


if __name__ == "__main__":
    sys.exit(main())
