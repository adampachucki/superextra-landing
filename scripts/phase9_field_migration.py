"""Phase 9 Firestore field migration — drop legacy fence fields.

Run AFTER the legacy Cloud Run worker is decommissioned. Strips the
following fields from every `sessions/*` doc:

  - currentAttempt — Cloud-Tasks-takeover counter, never read by gear
  - currentWorkerId — worker identity for the legacy fence, never used by gear
  - transport — sticky-per-session selector; collapses to gear-only after
    Phase 9, so the field becomes vestigial

The script is idempotent: deleting a missing field is a no-op. Safe to
re-run if interrupted.

Defaults to DRY-RUN — pass --apply to actually write. Always run a dry
pass first to confirm the count + sample.

Pre-flight checklist (verify before --apply):

  - [ ] Cloud Run service `superextra-worker` deleted (or maxScale=0
        for >=24h with no traffic)
  - [ ] No new sessions written with `transport='cloudrun'` in the last
        7 days (sticky cloudrun sessions all drained)
  - [ ] `functions/index.js` source already updated to drop the fields
        from `perTurn` AND deployed (otherwise the next agentStream
        write puts them back)
  - [ ] Firestore backup exists: `gcloud firestore export
        gs://superextra-site-firestore-backups/phase9-pre-migration`

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=superextra-site \\
      .venv/bin/python scripts/phase9_field_migration.py [--apply]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from google.cloud import firestore


PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LEGACY_FIELDS = ("currentAttempt", "currentWorkerId", "transport")
BATCH_LIMIT = 400  # Firestore batched writes cap at 500; leave headroom.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the field deletions. Defaults to DRY-RUN.",
    )
    args = ap.parse_args()

    db = firestore.Client(project=PROJECT)
    sessions = db.collection("sessions")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] phase 9 field migration on project={PROJECT}")
    print(f"[{mode}] removing fields: {LEGACY_FIELDS}\n")

    # Stream all session docs. We can't filter on "has any of these
    # fields" cheaply in Firestore, so we read everything and skip docs
    # that already lack all three fields.
    examined = 0
    needs_update = 0
    written = 0
    samples_collected = 0
    batch = db.batch()
    in_batch = 0

    started = time.time()
    for snap in sessions.stream():
        examined += 1
        data = snap.to_dict() or {}
        present = [f for f in LEGACY_FIELDS if f in data]
        if not present:
            continue

        needs_update += 1
        if samples_collected < 5:
            print(
                f"  sample sid={snap.id} fields_to_drop={present} "
                f"transport={data.get('transport')!r} "
                f"status={data.get('status')!r}"
            )
            samples_collected += 1

        if not args.apply:
            continue

        update = {f: firestore.DELETE_FIELD for f in present}
        batch.update(snap.reference, update)
        in_batch += 1
        if in_batch >= BATCH_LIMIT:
            batch.commit()
            written += in_batch
            print(f"[apply] committed batch — written so far: {written:,}")
            batch = db.batch()
            in_batch = 0

    if args.apply and in_batch:
        batch.commit()
        written += in_batch

    elapsed = time.time() - started
    print(
        f"\n[{mode}] examined={examined:,} "
        f"needs_update={needs_update:,} "
        f"written={written:,} "
        f"elapsed={elapsed:.1f}s"
    )

    if not args.apply:
        print(f"\n[DRY-RUN] re-run with --apply to commit.")
        return 0
    return 0 if written == needs_update else 1


if __name__ == "__main__":
    sys.exit(main())
