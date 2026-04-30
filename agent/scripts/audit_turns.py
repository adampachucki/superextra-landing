#!/usr/bin/env python3
"""Audit recent turns for empty/short/errored final reports.

Queries Firestore for turns created in the last N hours and flags:

  - errored: turn has an `error` field set
  - not_complete: turn status is anything but `complete` (excluding turns
    started in the last 30 min, which are likely still in flight)
  - short: status=complete but reply <1000 chars (post-collapse fallback
    is gone — empty/short replies are a real failure mode worth surfacing)

Exits 0 if everything is healthy, 1 if anything was flagged. Designed
to be invoked from a daily GitHub Actions cron and a workflow summary
annotation when issues surface.

Local usage:
    GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/.../adc.json \\
        agent/.venv/bin/python agent/scripts/audit_turns.py
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys


PROJECT = "superextra-site"
# Two thresholds: research turns (0001) use the full report length floor;
# follow-up turns (0002+) use a much smaller floor, since the follow-up
# prompt explicitly tells the agent to "be concise — match the answer's
# length to what the question asks." A 200-char follow-up is legitimate;
# a 50-char follow-up is the empty-or-near-empty failure mode.
SHORT_THRESHOLD_RESEARCH = 1000
SHORT_THRESHOLD_FOLLOWUP = 200
IN_FLIGHT_GRACE_MIN = 30


def _is_research_turn(turn_id: str) -> bool:
    """`0001` is the research turn; anything else is a follow-up."""
    return turn_id == "0001"


def _short_threshold_for(turn_id: str) -> int:
    return (
        SHORT_THRESHOLD_RESEARCH
        if _is_research_turn(turn_id)
        else SHORT_THRESHOLD_FOLLOWUP
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Window to audit, in hours back from now. Default 24.",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT),
    )
    args = parser.parse_args()

    from google.api_core.exceptions import FailedPrecondition
    from google.cloud import firestore
    from google.cloud.firestore_v1 import FieldFilter

    fs = firestore.Client(project=args.project)
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=args.hours)
    inflight_grace = now - datetime.timedelta(minutes=IN_FLIGHT_GRACE_MIN)

    errored: list[tuple[str, str, str, int]] = []
    not_complete: list[tuple[str, str, str | None, int]] = []
    short: list[tuple[str, str, int]] = []
    ok = 0
    in_flight_skipped = 0

    query = fs.collection_group("turns").where(
        filter=FieldFilter("createdAt", ">=", cutoff)
    )
    try:
        for t in query.stream():
            d = t.to_dict()
            started = d.get("startedAt") or d.get("createdAt")
            if started and started > inflight_grace and d.get("status") != "complete":
                in_flight_skipped += 1
                continue
            sid = t.reference.parent.parent.id
            tid = t.id
            reply = d.get("reply") or ""
            status = d.get("status")
            error = d.get("error")
            threshold = _short_threshold_for(tid)
            if error:
                errored.append((sid, tid, str(error), len(reply)))
            elif status != "complete":
                not_complete.append((sid, tid, status, len(reply)))
            elif len(reply) < threshold:
                short.append((sid, tid, len(reply)))
            else:
                ok += 1
    except FailedPrecondition as exc:
        if "index" in str(exc).lower():
            print("audit unavailable: Firestore index for turns.createdAt is not ready")
            print("  deployed index: collectionGroup=turns field=createdAt ASC")
            return 2
        raise

    flagged = errored or not_complete or short
    print(
        f"audit window: last {args.hours}h "
        f"(cutoff {cutoff.isoformat(timespec='minutes')})"
    )
    print(f"  ok:           {ok}")
    print(f"  errored:      {len(errored)}")
    print(f"  not_complete: {len(not_complete)}")
    print(
        f"  short (research <{SHORT_THRESHOLD_RESEARCH}, "
        f"follow-up <{SHORT_THRESHOLD_FOLLOWUP}): {len(short)}"
    )
    print(f"  in_flight_skipped (<{IN_FLIGHT_GRACE_MIN}m old, still running): {in_flight_skipped}")

    if errored:
        print("\nERRORED:")
        for sid, tid, err, n in errored[:10]:
            print(f"  {sid[:12]}/{tid} error={err!r} reply_len={n}")
    if not_complete:
        print("\nNOT COMPLETE:")
        for sid, tid, status, n in not_complete[:10]:
            print(f"  {sid[:12]}/{tid} status={status!r} reply_len={n}")
    if short:
        print("\nSHORT (status=complete but reply below threshold):")
        for sid, tid, n in short[:10]:
            print(
                f"  {sid[:12]}/{tid} reply_len={n} "
                f"(threshold={_short_threshold_for(tid)})"
            )

    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
