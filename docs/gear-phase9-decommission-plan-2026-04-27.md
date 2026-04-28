# GEAR migration — Phase 9 decommission plan

**Date drafted:** 2026-04-27
**Execution:** 2026-04-28 (compressed — see "Compression rationale" below)
**Owner:** Adam (with agent-side help on the source-side cleanup + migration)

## Compression rationale

The original plan called for a 30-day rollback window before Phase 9, with a 7-day pre-flight checklist on top. That gate was waived on 2026-04-28 with explicit user direction ("there are no users — all testing is on us"). The proof points the calendar would have given us — watchdog firing on a real stuck session, cost trajectory diverging, subjective quality regression — only have value when there's organic traffic to generate them. There isn't.

What we did instead, all on 2026-04-27:

- Rollback drill in both directions (gear→cloudrun→gear), fresh anon UIDs, verified `transport` field flipping correctly each direction.
- Side-by-side quality drill on a substantive prompt (`Le Vintage Brussels` brasserie comparison): gear `6058 chars / 32 sources / structured analysis with chart`, cloudrun `6393 chars / 13 sources / parallel structure`. Quality parity confirmed.
- Watchdog verified end-to-end with an injected stuck Firestore session (`worker_lost` flip in 76s).
- Two production regressions caught + fixed during the same drills (env-var stripping, plugin halting cloudrun) — exactly the kind of issues a real soak would have found.
- Cost baseline script in place (`agent/probe/cost_baseline.py`) with documented project-level visibility limits for the gear side.

Without users, additional calendar time gives us nothing the active drills haven't already given us. Phase 9 executes today.

## Pre-flight sanity checks (single-pass, all run today)

Each item is a single query. If any fails, fix or skip the offending stage; do not proceed past Stage 2 with unresolved failures.

- [ ] **Worker idle.** `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="superextra-worker" AND httpRequest.requestMethod="POST"' --freshness=30m` returns zero hits. Sticky-cloudrun follow-ups manifest as worker POSTs; if the count is zero for the last 30 minutes, no active sticky-cloudrun work is in flight. (Collapsed from two gates that asked the same question different ways — Firestore query for sticky sessions would have needed a composite index; the worker log is observable directly.)
- [ ] **No GEAR-side incidents in last 24h.** `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="agentstream" AND severity>=WARNING' --freshness=24h` shows no `gear_handoff_failed` errors above baseline noise (the cold-start `DEFAULT_RESOURCE` warning is benign and doesn't count).
- [ ] **agentStream env vars healthy.** `gcloud run services describe agentstream --region=us-central1 --format='value(spec.template.spec.containers[0].env)'` shows `GEAR_REASONING_ENGINE_RESOURCE` set. (PR #11 fix verification.)
- [ ] **Firestore backup bucket exists.** `gsutil ls gs://superextra-site-firestore-backups/` returns ok. If the bucket doesn't exist, one-shot create: `gsutil mb -l us-central1 gs://superextra-site-firestore-backups`. Backup is non-negotiable: Stage 3 field deletions are non-reversible without it.

## Execution sequence

Three stages, each gated on the previous succeeding.

### Stage 1 — Source-side deletes (one PR)

Single PR titled `chore(gear): phase 9 — decommission worker codepath`. Branch from main.

**Source files to delete:**

- `agent/worker_main.py` (~921 lines) — the legacy ADK pipeline runner
- `agent/tests/test_worker_main.py` (~1773 lines) — its tests
- `agent/tests/e2e_worker_live.py` — also imports `worker_main`; becomes dead after the worker source is gone
- `agent/probe/` directory entirely (~1721 lines) — R3 probe scripts that shipped with the migration. **Move `agent/probe/cost_baseline.py` → `scripts/cost_baseline.py` BEFORE the directory delete** so the post-Phase-9 cost-monitoring tool survives. Update its docstring to reference its new path.
- `agent/Dockerfile` — only purpose is to build the worker image; if `cloudbuild.yaml` exists for the worker, also delete
- `spikes/skeletons/worker_main.py` — historic spike, leftover

**Source files to edit:**

- `functions/index.js`
  - Drop `currentAttempt: 0` and `currentWorkerId: null` from the `perTurn` object.
  - Drop `adkSessionId: null` from the first-message `t.set` payload (line 342) — Reasoning Engine owns session identity.
  - Drop `existingAdkSessionId` capture (line 312) and the `adkSessionId: existingAdkSessionId` field in the cloudrun task body (line 417). Both go away when the cloudrun branch goes away.
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
- `CLAUDE.md` AND `AGENTS.md` § "Transport architecture" — collapse to a single-transport description: "Browser POSTs to `agentStream` → handoff to Reasoning Engine via `gearHandoff()`. `FirestoreProgressPlugin` writes progress + terminal state from inside the engine."
- `.github/workflows/deploy.yml`
  - Drop the `deploy-worker` job entirely.
  - Update `deploy-hosting.needs` from `[test, deploy-worker]` to `[test]` (verified: `.github/workflows/deploy.yml:102`). Forgetting this line will keep `deploy-hosting` blocked on a non-existent job.
  - Drop `detect-changes` if it only feeds `deploy-worker`.
  - Keep the `GEAR_REASONING_ENGINE_RESOURCE` line in the .env-write step. Belt-and-suspenders with `gear-handoff.js`'s `DEFAULT_RESOURCE` is cheap; future engine recreation only needs the workflow line updated.
- `agent/superextra_agent/firestore_progress.py` and `gear_run_state.py` — keep, these ARE the new runtime. Also keep the `runId`-missing no-op branch + its log warning (case 2 — malformed gear handoff — is still a real failure mode worth surfacing, even with the legacy worker gone).
- `docs/deployment-gotchas.md` — two changes here, not just one. (a) **Strip** the now-stale "Cloud Run worker (`superextra-worker`)" section (lines 11-39) and the "Cloud Tasks + OIDC" section (lines 40-64) — both describe a service that no longer exists. (b) **Add** a short entry capturing the `firebase deploy REPLACES env vars (does not merge)` finding from PR #11. ~5 lines. Future agent sessions otherwise rediscover both the missing-context AND the env-var trap the hard way.
- `docs/gear-stage-a-test-plan-2026-04-27.md` — append a one-paragraph retrospective: "any 'X is contained' smoke must verify the contained X actually works end-to-end (`status='complete'`), not just that routing landed (`status='running'`)." Smoke 5 demonstrated the cost of skipping that — the cloudrun-broken-by-plugin regression sat undetected for hours because the smoke only checked routing.
- `agent/probe/` — `git tag gear-migration-probes-archive HEAD` AND `git push origin gear-migration-probes-archive` BEFORE this PR's `agent/probe/` delete commit. The probe scripts proved R3.x's post-disconnect contract during the migration; tag preserves the audit trail at zero cost.

**Doc files NOT to touch in this PR:** `docs/gear-migration-implementation-plan-2026-04-26.md`, `docs/gear-migration-execution-log-2026-04-27.md`, `docs/gear-stage-a-test-plan-2026-04-27.md` (except the retrospective paragraph), and `docs/gear-post-review-fixes-plan-2026-04-27.md`. They are historical record and should stay as-is.

**Verification gates:**

- `cd functions && npm test` — gear-branch tests pass, cloudrun-branch tests deleted.
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` — drops to whatever's left after worker tests delete (~430 → ~110 if the math is right).
- `npm run test:rules` — unchanged (rules don't reference fields).
- `npm run check` — 0 errors.

**Merge order (CRITICAL):** Stage 1 PR must merge AND deploy successfully BEFORE Stage 2's `gcloud run services delete` runs. The deployed agentStream still routes sticky `transport='cloudrun'` follow-ups via `enqueueRunTask` until the Stage 1 source ships; deleting the worker first would 404 those Cloud Tasks. The pre-flight gate ("zero new cloudrun sessions in last 7 days") gives strong protection but isn't atomic — the strict ordering closes the gap.

### Stage 2 — Cloud-side deletes (Adam runs gcloud)

After Stage 1 PR has merged AND the Cloud Functions deploy completes successfully (verify `gcloud run services describe agentstream --region=us-central1` shows the new revision serving 100% traffic), AND the gear-only source has been live for ≥30 min with the worker observably idle: re-run the pre-flight "Worker idle" check (`gcloud logging read ...freshness=30m` returns 0 worker POSTs). agentStream itself does not log successful `enqueueRunTask` calls (only failures at `functions/index.js:425`), so the worker-side log is the load-bearing observable, not an agentStream-side one.

```bash
# 1. Snapshot Firestore (required for the rollback story)
gcloud firestore export gs://superextra-site-firestore-backups/phase9-pre-migration-$(date +%Y%m%d) \
  --project=superextra-site

# 2. Delete the worker Cloud Run service
gcloud run services delete superextra-worker \
  --region=us-central1 \
  --project=superextra-site \
  --quiet

# 3. Delete the Cloud Tasks queue (verified live name: agent-dispatch, NOT agent-runs)
gcloud tasks queues delete agent-dispatch \
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

After Stage 2 step 2, the only path that could attempt to route to the deleted worker is a sticky-cloudrun follow-up — but the Stage 1 source no longer has the `transport === 'cloudrun'` branch, so even a sticky follow-up routes via `gearHandoff` to the Reasoning Engine. The pre-flight gate ("no active sticky-cloudrun sessions") + the source-side branch removal gives belt-and-suspenders containment.

### Stage 3 — Firestore field migration

Run `scripts/phase9_field_migration.py` AFTER Stage 2 completes (worker gone, no chance of new legacy-field writes).

```bash
# Dry-run first — confirm count + sample looks right
GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=superextra-site \
  .venv/bin/python scripts/phase9_field_migration.py

# Apply
GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=superextra-site \
  .venv/bin/python scripts/phase9_field_migration.py --apply
```

The script strips `adkSessionId`, `currentAttempt`, `currentWorkerId`, and `transport` from every `sessions/*` doc. Idempotent — re-run if interrupted. Latest dry-run (2026-04-28) reports 33 sessions need cleanup. Note: `transport` is a deviation from plan §9 (which only listed `adkSessionId`/`currentAttempt`/`currentWorkerId`); included here because the field becomes vestigial once the cloudrun branch is gone, and leaving it would just confuse future readers.

### Stage 4 — Post-flight smoke

After Stage 3 completes:

1. Submit one Chrome MCP query against the live agentStream from a fresh anon UID. Use a substantive prompt (e.g. the Le Vintage Brussels brasserie comparison) so the run exercises the full pipeline, not just routing.
2. Verify `sessions/{sid}` reaches `status='complete'`, no `error`, reply length and source count in the same ballpark as previous gear runs.
3. Spot-check the session doc: confirm `adkSessionId`, `currentAttempt`, `currentWorkerId`, `transport` are absent (Stage 3 cleaned them; Stage 1 source no longer writes them).
4. `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="agentstream" AND severity>=WARNING' --freshness=10m` — confirm no new warnings.

If any check fails, freeze cleanup and investigate. The Firestore export from Stage 2 step 1 is the safety net.

## Rollback (if something goes sideways)

- **Stage 1 mid-execution:** revert the Stage 1 PR. No cloud-side state changed yet.
- **Stage 2 mid-execution:** Stage 1 is already deployed (gear-only source), so a re-deployed worker would have no caller. Restore via `git checkout gear-migration-probes-archive -- agent/worker_main.py agent/Dockerfile` (the tag is placed at HEAD BEFORE the Stage 1 delete commits, so the tagged tree CONTAINS the worker source — no `~1` parent traversal needed) then `gcloud run deploy superextra-worker --source=agent` (~10 min build). Then revert the relevant `functions/index.js` deletes to restore the cloudrun branch + redeploy. About 30 min total to a working cloudrun fallback.
- **Stage 3 mid-execution:** the script is dry-run-by-default and idempotent; re-running picks up where it left off.
- **Post-Stage 3:** field deletions are non-reversible without the Firestore export from Stage 2 step 1. Restore via `gcloud firestore import gs://superextra-site-firestore-backups/phase9-pre-migration-...`.

## Estimated effort

- Stage 1 (source PR + bundled doc cleanups): 2-3 hours including test updates.
- Stage 2 (gcloud + service-account cleanup): 30 min wall clock.
- Stage 3 (Firestore migration): 5 min wall clock (dry-run + apply on 33 sessions today).
- Stage 4 (post-flight smoke): 10 min wall clock.

**Total:** ~half a day end-to-end on 2026-04-28.

## What stays

After Phase 9 the codebase carries:

- `agent/superextra_agent/` — the agent app (instructions, plugins, tools)
- `agent/superextra_agent/firestore_progress.py` + `gear_run_state.py` — the runtime
- `functions/index.js` (slimmer), `functions/gear-handoff.js`, `functions/watchdog.js`
- `agent/tests/` (without `test_worker_main.py`) — plugin + agent tests
- `agent/probe/` is GONE from main but preserved at the `gear-migration-probes-archive` git tag
- `scripts/phase9_field_migration.py` stays in tree as a re-runnable safety net (idempotent, dry-run by default)

Nothing about gear/cloudrun coexistence remains. The mental model becomes: **browser → agentStream → Reasoning Engine → Firestore progress/terminal state**. Sticky transport, the allowlist, `chooseInitialTransport`, and the four legacy session fields all evaporate.

## Done means

Quoting the reviewer's framing — "Done means: no cloudrun branch, no transport field dependency, no Cloud Tasks queue, no worker deployment job, no stale docs. The architecture should read simply: browser → agentStream → GEAR → Firestore progress/terminal state."

Verification at end-of-Phase-9:

- `grep -rn 'cloudrun\|enqueueRunTask\|chooseInitialTransport\|GEAR_DEFAULT\|GEAR_ALLOWLIST' functions/ agent/superextra_agent/` returns no matches in source. (Comments are fine; active code references would be a bug. Scope expanded from `functions/` because gear-side code in `agent/superextra_agent/` would otherwise pass the check falsely.)
- `grep -rn 'transport\|adkSessionId\|currentAttempt\|currentWorkerId' functions/ agent/superextra_agent/` returns no matches in source.
- `gcloud run services list --project=superextra-site` does not list `superextra-worker`.
- `gcloud tasks queues list --location=us-central1 --project=superextra-site` does not list `agent-dispatch`.
- `gcloud iam service-accounts list --project=superextra-site` does not list `superextra-worker@...`.
- `cat .github/workflows/deploy.yml` has no `deploy-worker` job.
- `grep -rn 'Cloud Tasks\|Cloud Run worker\|cloudrun' CLAUDE.md AGENTS.md` returns no match (except possibly in historic-context callouts).
- Firestore: a fresh-anon submission produces a `sessions/{sid}` doc whose only fence-related field is `currentRunId`.
