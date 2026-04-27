# GEAR migration — Phase 9 decommission plan

**Date drafted:** 2026-04-27
**Earliest execution:** 2026-05-27 (Stage B + 30-day rollback window)
**Owner:** Adam (with agent-side help on the source-side cleanup + migration)

## Pre-flight checklist

Phase 9 only proceeds when ALL of these hold for ≥7 consecutive days. Each item is a single grep / gcloud / Firestore query — no inference.

- [ ] **No new cloudrun sessions.** `transport='cloudrun'` count among `sessions/*` written in the last 7 days = 0. Query: Firestore filter `where('transport', '==', 'cloudrun').where('createdAt', '>=', sevenDaysAgo)`.
- [ ] **No active sticky-cloudrun chats.** Sessions with `transport='cloudrun'` AND `status` in `('queued','running')` = 0. (If there are any, wait for them to drain or watchdog-flip.)
- [ ] **Worker traffic at zero.** `gcloud run services describe superextra-worker` shows zero requests in the last 7 days via Cloud Logging: `resource.type="cloud_run_revision" AND resource.labels.service_name="superextra-worker" AND httpRequest.requestMethod="POST"` returns 0 hits.
- [ ] **No GEAR-side incidents.** `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="agentstream" AND severity>=WARNING'` for the same 7 days shows no `gear_handoff_failed` errors > baseline noise.
- [ ] **Cost trajectory acceptable.** GCP Console → Billing → Reports filtered to project=superextra-site shows weekly spend within ±20 % of pre-migration cloudrun baseline. (Baseline: 2026-04-20 to 2026-04-26 worker week.) If the gear week is materially higher, treat as a Stage 2 conversation, not a Phase 9 blocker — Phase 9 is a code-cleanup phase, not a cost gate.
- [ ] **Firestore backup.** `gcloud firestore export gs://superextra-site-firestore-backups/phase9-pre-migration-$(date +%Y%m%d)` returned success. (One-time creation of the bucket: `gsutil mb -l us-central1 gs://superextra-site-firestore-backups`.) Required because the field-deletion is non-reversible without the export.

If any item fails, do not proceed. Fix or wait, then re-check.

## Execution sequence

Three stages, each gated on the previous succeeding.

### Stage 1 — Source-side deletes (one PR)

Single PR titled `chore(gear): phase 9 — decommission worker codepath`. Branch from main.

**Source files to delete:**

- `agent/worker_main.py` (~921 lines) — the legacy ADK pipeline runner
- `agent/tests/test_worker_main.py` (~1773 lines) — its tests
- `agent/probe/` directory entirely (~1721 lines) — R3 probe scripts that shipped with the migration
- `agent/Dockerfile` — only purpose is to build the worker image; if `cloudbuild.yaml` exists for the worker, also delete
- `spikes/skeletons/worker_main.py` — historic spike, leftover

**Source files to edit:**

- `functions/index.js`
  - Drop `currentAttempt: 0` and `currentWorkerId: null` from the `perTurn` object.
  - Drop the entire `if (transport === 'cloudrun') { ... enqueueRunTask ... }` branch in `agentStream`.
  - Drop the `enqueueRunTask` function and the `CloudTasksClient` import.
  - Drop `chooseInitialTransport`, `GEAR_DEFAULT`, `GEAR_ALLOWLIST` (always-gear after Phase 9).
  - Drop the `transport: 'gear'` assignment in the first-message session set (field becomes implicit).
  - Drop the `agentDelete` Cloud Task auth-token plumbing if it only existed for worker IAM.
- `functions/watchdog.js`
  - Audit for any `currentWorkerId` / `currentAttempt` references; remove. The watchdog's fence is `currentRunId + status` only after Phase 9.
- `functions/index.test.js` + `functions/watchdog.test.js`
  - Drop tests covering the cloudrun branch + the `chooseInitialTransport` unit test.
  - Keep the gear-branch tests, the watchdog tests, and the auth/error tests.
- `functions/utils.js` and `functions/utils.test.js`
  - Drop `enqueueRunTask` and its tests. Drop the Cloud Tasks queue / location constants.
- `firestore.indexes.json` — drop any indexes that exist solely for the worker (audit per index).
- `CLAUDE.md` § "Transport architecture" — collapse to a single-transport description: "Browser POSTs to `agentStream` → handoff to Reasoning Engine via `gearHandoff()`. `FirestoreProgressPlugin` writes progress + terminal state from inside the engine."
- `.github/workflows/deploy.yml`
  - Drop the `deploy-worker` job entirely.
  - Drop `detect-changes` if it only feeds `deploy-worker`.
- `agent/superextra_agent/firestore_progress.py` and `gear_run_state.py` — keep, these ARE the new runtime.

**Verification gates:**

- `cd functions && npm test` — gear-branch tests pass, cloudrun-branch tests deleted.
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` — drops to whatever's left after worker tests delete (~430 → ~110 if the math is right).
- `npm run test:rules` — unchanged (rules don't reference fields).
- `npm run check` — 0 errors.

Merge this PR ONLY after Stage 2 below has been planned (do not delete worker source while a deployed worker still exists).

### Stage 2 — Cloud-side deletes (Adam runs gcloud)

After Stage 1 PR is approved but BEFORE merging:

```bash
# 1. Snapshot Firestore (required for the rollback story)
gcloud firestore export gs://superextra-site-firestore-backups/phase9-pre-migration-$(date +%Y%m%d) \
  --project=superextra-site

# 2. Delete the worker Cloud Run service
gcloud run services delete superextra-worker \
  --region=us-central1 \
  --project=superextra-site \
  --quiet

# 3. (If exclusive to worker) delete the Cloud Tasks queue
gcloud tasks queues delete agent-runs \
  --location=us-central1 \
  --project=superextra-site \
  --quiet

# 4. Drop worker IAM bindings
# (Verify these — names depend on what was set up; check your IaC notes.)
gcloud projects remove-iam-policy-binding superextra-site \
  --member="serviceAccount:superextra-worker@superextra-site.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# 5. Delete the worker service account
gcloud iam service-accounts delete \
  superextra-worker@superextra-site.iam.gserviceaccount.com \
  --project=superextra-site \
  --quiet
```

Once step 2 succeeds and zero errors fire from agentStream for ≥30 min, merge the Stage 1 PR.

### Stage 3 — Firestore field migration

Run `scripts/phase9_field_migration.py` AFTER the Stage 1 PR is deployed (so no new docs get the legacy fields written back).

```bash
# Dry-run first — confirm count + sample looks right
GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=superextra-site \
  .venv/bin/python scripts/phase9_field_migration.py

# Apply
GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=superextra-site \
  .venv/bin/python scripts/phase9_field_migration.py --apply
```

The script strips `currentAttempt`, `currentWorkerId`, and `transport` from every `sessions/*` doc. Idempotent — re-run if interrupted. Today's dry-run reports 29 sessions need cleanup (all complete state, no in-flight risk).

### Stage 4 — agent/probe/ archival (optional)

The probe scripts under `agent/probe/` proved the platform's post-disconnect contract during the migration (R3.x rounds). They have audit value but no operational role. Two options:

- **Archive on a tag.** Before deleting in Stage 1, `git tag gear-migration-probes-archive HEAD` and push the tag. Restoration via `git checkout gear-migration-probes-archive -- agent/probe/`.
- **Just delete.** The probe results docs (`docs/gear-probe-results-*.md`) capture the findings; the scripts are reproducible from those + the implementation plan.

Recommend the tag — costs nothing and preserves the audit trail.

## Rollback (if something goes sideways)

- **Stage 1 / Stage 2 mid-execution:** revert the Stage 1 PR, redeploy the worker via `gcloud run deploy superextra-worker --source=agent` if it was already deleted (~10 min from a fresh container build). Sticky-cloudrun was already drained by the pre-flight gate, so any in-flight work is on gear and unaffected.
- **Stage 3 mid-execution:** the script is dry-run-by-default and idempotent; re-running picks up where it left off.
- **Post-Stage 3:** field deletions are non-reversible without the Firestore export from the pre-flight checklist. Restore via `gcloud firestore import gs://superextra-site-firestore-backups/phase9-pre-migration-...`.

## Estimated effort

- Stage 1 (source PR): 2-3 hours including test updates.
- Stage 2 (gcloud + service-account cleanup): 30 min wall clock.
- Stage 3 (Firestore migration): 5 min wall clock (dry-run + apply on 29 sessions today).
- Stage 4 (archival): 5 min if tag; <1 min if just delete.

**Total:** ~half a day, plus the 30-day rollback wait before any of it starts.

## What stays

After Phase 9 the codebase carries:

- `agent/superextra_agent/` — the agent app (instructions, plugins, tools)
- `agent/superextra_agent/firestore_progress.py` + `gear_run_state.py` — Stage B runtime
- `functions/index.js` (slimmer), `functions/gear-handoff.js`, `functions/watchdog.js`
- `agent/tests/` (without `test_worker_main.py`) — plugin + agent tests
- `agent/probe/` may or may not be present per Stage 4 choice

Nothing about gear/cloudrun coexistence remains. The mental model becomes: browser → agentStream → Reasoning Engine. Sticky transport, the allowlist, and `chooseInitialTransport` all evaporate.
