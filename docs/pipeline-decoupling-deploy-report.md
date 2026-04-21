# Pipeline-Decoupling Deploy Report

**Date**: 2026-04-21
**PR**: [#5 — Pipeline decoupling refactor](https://github.com/adampachucki/superextra-landing/pull/5)
**Final status**: Production-validated end-to-end, including a real-user browser flow and a multi-turn follow-up.

---

## 1. Summary

Shipped the pipeline-decoupling refactor (Cloud Tasks → private Cloud Run worker → Firestore progress stream) to production. Rollout took **5 workflow runs + 3 live-fix commits after merge** because the workflow ran into a sequence of infrastructure permissions and configuration issues that hadn't been exercised before (the deploy pipeline itself was new).

After the initial deploy succeeded, two additional defects were caught by adversarial post-deploy review — one of them a production blocker for multi-turn conversations — and fixed with live verification.

**All findings are now resolved or explicitly accepted. The system is live and verified.**

---

## 2. Deploy timeline

### Attempt 1 — Run `24710949201` (merge of PR #5, 6 commits)

**Failure**: `test` job failed on `npm run test:rules`.

**Root cause**: GitHub's `ubuntu-latest` runner ships Java 17. The auto-installed `firebase-tools@15.15.0` requires JDK 21+ to run the Firestore emulator.

**Fix**: `5ded8c0` — added `actions/setup-java@v4` with `temurin 21` before the emulator step.

### Attempt 2 — Run `24711047518`

**Failure**: `deploy-worker` built and deployed the Cloud Run service successfully, but the `/healthz` smoke test returned HTTP 404.

**Investigation**: Worker logs showed uvicorn booting cleanly. IAM showed only the worker SA itself had `roles/run.invoker`. The smoke test minted an identity token as the GitHub Actions SA (`firebase-adminsdk-fbsvc@superextra-site.iam.gserviceaccount.com`), which had no `run.invoker` permission. Private Cloud Run services return 404 (not 403) to unauthorized callers to avoid existence disclosure.

**Fix**:

1. Manual IAM grant (via gcloud): `firebase-adminsdk-fbsvc@` → `roles/run.invoker` on `superextra-worker`.
2. Workflow change `f0a6b52` — resolves the active auth SA at runtime via `gcloud auth list`, then grants `run.invoker` to both the worker SA and the deploy SA. Idempotent, so future deploys reapply safely.

### Attempt 3 — Run `24711805393`

**Failure**: Smoke step still returned `status=` (empty) despite valid IAM.

**Root cause**: The readiness check used `gcloud ... --format='value(status.conditions[?type=="Ready"].status)'`. `gcloud`'s `value()` projection does not support the JMESPath filter syntax (`[?...]`) and silently returned empty. This is poorly documented.

**Fix**: Commit `55517d5` — replaced filter syntax with positional indexing (`conditions[0].type` + `conditions[0].status`) and assert both values explicitly. Cloud Run reliably orders `Ready` first.

Alongside this, commit `2301f6b` dropped the HTTP `/healthz` probe entirely in favour of a Cloud Run control-plane `Ready=True` check — the HTTP probe was brittle (private-service 404s obscure real failures) and the Cloud Run readiness gate already validates container startup.

### Attempt 4 — Run `24712143095`

**Failure**: `deploy-worker` succeeded. `deploy-hosting` failed cascading 403s:

1. `firebaserules.googleapis.com:test` — 403 permission denied.
2. (After fix) `cloudscheduler.googleapis.com` — "Permissions denied enabling" (the SA couldn't enable APIs).
3. (After fix) Firestore indexes REST — 403 permission denied.
4. (After fix) `cloudscheduler.jobs.update` — 403 permission denied.

**Root cause**: The Firebase admin SA has roles for hosting, functions, auth, artifact registry, Cloud Build, secret manager, and storage — but none for rules, indexes, or scheduler. None of these permissions had been needed by the pre-refactor deploy pipeline.

**Fixes** (manual IAM via gcloud, all on `superextra-site` project level, member `firebase-adminsdk-fbsvc@...`):

| Role                         | Why                                                                                     |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| `roles/firebaserules.admin`  | Deploying `firestore.rules` requires `firebaserules.rulesets.test` + `releases.create`. |
| `roles/datastore.indexAdmin` | Deploying composite indexes via Firestore Admin API.                                    |
| `roles/cloudscheduler.admin` | Creating/updating the watchdog's scheduled trigger.                                     |

Also enabled `cloudscheduler.googleapis.com` manually via `gcloud services enable`.

No workflow edit — these grants are one-time and persist.

### Attempt 5 — Run `24713422338`

**Failure**: Workflow succeeded. But Cloud Scheduler had **no jobs**. Firebase had logged "watchdog(us-central1) Skipped (No changes detected)" — because attempt 4 partially deployed the function (Cloud Run side) but hit 403 on the scheduler-creation step. On rerun, firebase saw the function source hadn't changed and skipped the whole unit, leaving the scheduler job absent.

**Fix**: Commit `986bf6c` — added one sentence to `watchdog.js`'s header comment to force firebase-tools to re-walk the function and create the missing scheduler job.

### Attempt 6 — Final green run

Full workflow passed. Live state verified:

- `superextra-worker` Cloud Run service: `Ready=True` at `https://superextra-worker-22b3fxahka-uc.a.run.app`
- `agentStream` Cloud Function: `serviceConfig.timeoutSeconds=30` (was 500 pre-refactor)
- `agentCheck` Cloud Function: deployed
- `watchdog` Cloud Function + `firebase-schedule-watchdog-us-central1` Cloud Scheduler job: `ENABLED`, `every 2 minutes`
- 4 Firestore composite indexes: `READY`
- 2 TTL policies: `ACTIVE` (at this point — see §4 for the later regression)
- Firebase Hosting: both sites uploaded

### Immediate live E2E validation

Ran `agent/tests/e2e_worker_live.py` against the deployed worker:

- Query: Umami Berlin, "What service issues come up in reviews?"
- Elapsed: 290 s
- `status=complete`, `reply=119,624 chars`, `sources=5 items`, `title="Service issues reviews"`
- All 6 verdicts ✅ (`final_status_complete`, `reply_populated`, `adk_session_persisted`, `events_written`, `title_set_on_first_turn`, `collection_group_query_works`)

---

## 3. IAM grants applied manually during rollout

One-time, persistent, authoritative:

| Principal                                                         | Role                                    | Scope                       |
| ----------------------------------------------------------------- | --------------------------------------- | --------------------------- |
| `firebase-adminsdk-fbsvc@superextra-site.iam.gserviceaccount.com` | `roles/run.invoker`                     | service `superextra-worker` |
| `firebase-adminsdk-fbsvc@superextra-site.iam.gserviceaccount.com` | `roles/firebaserules.admin`             | project `superextra-site`   |
| `firebase-adminsdk-fbsvc@superextra-site.iam.gserviceaccount.com` | `roles/datastore.indexAdmin`            | project `superextra-site`   |
| `firebase-adminsdk-fbsvc@superextra-site.iam.gserviceaccount.com` | `roles/cloudscheduler.admin`            | project `superextra-site`   |
| (API)                                                             | `cloudscheduler.googleapis.com` enabled | project `superextra-site`   |

For a fresh project deploy of this stack, these should be scripted into a bootstrap Terraform/shell rather than discovered at workflow time.

---

## 4. Adversarial post-deploy review — round 1

After the immediate E2E passed, spawned an adversarial agent to stress-test 30+ categories (auth gates, ownership checks, Firestore rules, watchdog flips, rate limits, cross-user 403, concurrent-turn 409, log correlation, etc.).

### Result: 20 PASS, 3 real findings

**Finding 1 — TTL policies wiped by firebase deploy** (the one real regression)

Root cause: `firestore.indexes.json` had `fieldOverrides: []` (empty). `firebase deploy --only firestore:indexes` syncs field configs **and removes any not declared**. The TTL policies I had set manually with `gcloud firestore fields ttls update` prior to the first firestore deploy were silently wiped when the workflow ran the combined Firebase deploy.

**Fix**: Commit `3d7d6f5` — declared both TTL fields in `fieldOverrides`:

```json
{
	"fieldOverrides": [
		{ "collectionGroup": "sessions", "fieldPath": "expiresAt", "ttl": true, "indexes": [] },
		{ "collectionGroup": "events", "fieldPath": "expiresAt", "ttl": true, "indexes": [] }
	]
}
```

Verified live after redeploy: both TTLs transitioned to `CREATING` then `ACTIVE`. Deploy is idempotent now; future workflow runs won't wipe them.

**Finding 2 — Vertex AI Session Event Append 429 under burst**: Expected under adversarial load (25-req blast). Design-partner scale is well under the per-minute quota. Accepted; watch production metrics and request quota raise if it ever matters.

**Finding 3 — IP rate-limit shadows UID rate-limit**: Intentional per plan. IP (20/10 min) is the outer ceiling; UID (20/hour) is the inner ceiling. Documented trade-off for shared-IP users. No action.

---

## 5. Live user-flow verification via Chrome DevTools MCP

Opened a real browser against `https://agent.superextra.ai/chat`.

### Observed end-to-end chain

1. `/__/firebase/init.json` → 200
2. `identitytoolkit.googleapis.com/v1/accounts:signUp` → 200 (anonymous sign-in, valid ID token)
3. Google Places autocomplete for "Umami Berlin" → 200 (5 real suggestions)
4. Selected "Umami, Knaackstraße, Berlin"
5. Typed: "What service issues keep coming up in recent reviews?"
6. **`agentstream POST` → 202 in ~1 s** (JSON transport, no SSE)
7. Firestore `Listen/channel` opened; 6 long-poll responses streamed progress
8. URL updated to `?sid=56f28db0-...`
9. UI rendered live activity: Gathering data → Loading place details → Fetching Google reviews → Fetching TripAdvisor reviews → Assigning specialists → Guest Intelligence, Review Analysis, Gap Research
10. After ~4 min, full synthesiser report rendered: 129 kB markdown, embedded base64 chart, 8 clickable grounding sources, 4 structured sections
11. Follow-up input unlocked

### Server-side state (verified via Firestore REST)

| Field            | Value                                              |
| ---------------- | -------------------------------------------------- |
| `userId`         | `ueKapMVz3hhADQtJkXRT52Mp3fA3` (Firebase anon UID) |
| `adkSessionId`   | `6757824276511850496` (Agent Engine session)       |
| `status`         | `complete`                                         |
| `currentRunId`   | `67691ab2-0def-4fd3-958f-0f3f5db9e299`             |
| `currentAttempt` | 1 (no retries)                                     |
| `reply`          | 129,206 chars                                      |
| `sources`        | 8 items                                            |
| `title`          | "Service reviews issues"                           |
| `error`          | null                                               |
| `expiresAt`      | +30 days                                           |

Zero console errors, zero warnings.

---

## 6. Adversarial post-deploy review — round 2

Second adversarial pass specifically probed cases the first agent didn't cover: multi-turn on the same `sid`, `agentCheck` fallback, concurrent-turn 409 races, watchdog actually flipping a stuck doc, adversarial input sanitation, Firestore rules from an anon user's ID token, Agent Engine session hygiene, log correlation.

### Result: 1 BLOCKER, 3 Significant, 3 Minor — plus 8 confirmations of working behaviour

#### BLOCKER B-1 — Multi-turn `follow_up` always fails

**Symptom** (reproduced live): On a completed session, sending any follow-up query that routed through the router's `follow_up` sub-agent flipped `status=error` with `error='empty_or_malformed_reply'`.

**Root cause**: `agent/superextra_agent/agent.py:278` registers `follow_up` as an `LlmAgent` with `output_key="final_report"` — the same terminal key the synthesiser uses. `agent/superextra_agent/firestore_events.py:map_event()` dispatched `router`, `context_enricher`, `research_orchestrator`, each specialist, and `synthesizer` — but had **no branch for `follow_up`**. Terminal events with `author='follow_up'` fell to `return None`. Since Tier 1.3 of the fixes plan switched the worker from reading `state_delta.final_report` directly to reading the mapper's emission (`emitted["type"] == "complete"`), the worker never saw the terminal, `final_reply` stayed `None`, and the reply-sanity gate flipped the session to error.

**Why it wasn't caught earlier**:

- Single-turn tests (all my unit tests + the live E2E) never exercised `follow_up`.
- `test_follow_up_routing.py` exists but is CI-excluded and tests router routing behaviour, not the mapper's handling of the `follow_up` agent's output.
- The initial browser smoke only tested turn 1.

**Fix** — Commit `a4f763e`:

1. `firestore_events.py`: added `if author in ("synthesizer", "follow_up"): return _map_synthesizer(event)` to the dispatcher. Same state_delta shape, same handler. Kept the prior `if author == "synthesizer"` branch removed to avoid duplicate dispatch.
2. `test_firestore_events.py`: two new cases — `test_follow_up_final_report_emits_complete` (happy path) and `test_follow_up_no_final_report_is_skipped` (guard). These will fail loud if the dispatcher is edited without handling `follow_up`.
3. `worker_main.py` — bonus S-3 fix in the same commit. The reply-sanity warning was `log.warning("reply sanity check failed sid=%s", sid)` — a bare-format log line that ended up in Cloud Logging with no `runId`/`workerId`/`attempt` correlation fields. Precisely the log needed to diagnose this incident. Changed to `log.warning(..., extra={**log_ctx, "event": "reply_sanity_failed"})`.

#### Significant / Minor — status

| #   | Finding                                                                 | Disposition                                                                                                        |
| --- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| S-1 | `validatePlaceContext` truncates but doesn't strip control chars / HTML | Deferred. No DOM sink renders raw placeContext; LLM input surface only. Track for hygiene pass.                    |
| S-2 | Worker `maxScale=10` vs queue `maxConcurrentDispatches=1000`            | Accepted per plan. Queue retry (`maxAttempts=3`) absorbs bursts at design-partner scale. Watch production metrics. |
| S-3 | Sanity-check log missing structured context                             | **Fixed** (bundled with B-1).                                                                                      |
| S-4 | Agent Engine 364-day TTL, no reconciliation with Firestore              | Accepted per plan. Low disk cost at current volume.                                                                |
| M-1 | Deleting a session doesn't cascade-delete its events subcollection      | Self-healing via 30-day `expiresAt` TTL.                                                                           |
| M-2 | Default Hosting `Cache-Control: max-age=3600`                           | Intentional Firebase default; acceptable for mostly-static shell.                                                  |
| M-3 | SSL cert CN is Firebase shared SAN                                      | Firebase behaviour. `verify_hostname` OK for `landing.superextra.ai`. Not a real finding.                          |

### Live verification of the B-1 fix

After commit `a4f763e` deployed, returned to the same session (`56f28db0-...`) in the browser (now showing the turn-1 report from earlier) and typed:

> "Which of these four service issues is the most urgent to fix first?"

Result:

- Turn-2 POST → 202, new `runId=37c708c4-...`, same `adkSessionId=6757824276511850496` (reused, as designed)
- Pipeline completed quickly (follow-up uses Gemini Flash, not the full research pipeline)
- **Agent reply** (631 chars): _"Based on the research report, the most urgent service issue to fix first is the lapse in food safety standards. The report explicitly states: 'The most critical service issue threatening the restaurant's local reputation is an empirically verified lapse in hygiene standards.' ..."_ — correctly grounded in turn-1 content
- `status=complete`, `error=null`
- `currentAttempt=1` (reset per turn, not accumulated)
- `title` preserved from turn-1 (not regenerated)
- `sources=[]` (correct — follow-up does no new research)

**Multi-turn is now production-validated.**

---

## 7. Commit log, post-merge

| Commit    | Summary                                                                                               |
| --------- | ----------------------------------------------------------------------------------------------------- |
| `a687004` | Merge commit for PR #5 (6 rolled-up commits)                                                          |
| `5ded8c0` | CI — install JDK 21 for `test:rules`                                                                  |
| `f0a6b52` | CI — grant `run.invoker` to active deploy SA for smoke                                                |
| `2301f6b` | CI — replace `/healthz` smoke with `Ready`-condition check                                            |
| `55517d5` | CI — positional indexing for Cloud Run Ready condition                                                |
| `986bf6c` | CI — force watchdog redeploy (scheduler job was missing)                                              |
| `3d7d6f5` | FIX — declare TTL policies in `fieldOverrides` (regression repair)                                    |
| `a4f763e` | FIX — map `follow_up` agent events to terminal emission; add structured log context on sanity warning |

---

## 8. What's still open

**Deferred (non-blocking, documented)**:

- S-1 placeContext HTML/control-char sanitization.
- S-2 worker scale tuning (only matters at scale beyond design-partner).
- S-4 Agent Engine session cleanup cadence.
- `test_follow_up_routing.py` — 4–7 flaky live-LLM routing-quality failures, CI-excluded, pre-existing.

**Manual cleanup tasks for operator**:

1. Delete the retired `superextra-agent` Cloud Run service after a day of clean traffic:
   ```
   gcloud run services delete superextra-agent --region=us-central1 --project=superextra-site
   ```
2. Delete the local `legacy-sessions-backup.json` from the dev machine once confident no rollback is needed.
3. Monitor `aiplatform.googleapis.com/SessionEventAppendRequestsPerMinutePerRegion` quota for the first week. If it shows sustained near-max usage, request a raise.

**Infrastructure-as-code debt**: The 4 IAM grants applied manually during rollout (§3) should be scripted — either in Terraform, a bootstrap shell, or a dedicated "project setup" GitHub Action — so a second project deploy doesn't repeat the discovery process.

---

## 9. Final verification snapshot

| Check                                     | Status                                          |
| ----------------------------------------- | ----------------------------------------------- |
| All 6 PR commits landed                   | ✅                                              |
| Post-merge fixes landed                   | ✅ (7 additional commits)                       |
| Workflow green on final run               | ✅                                              |
| Worker Cloud Run service Ready            | ✅                                              |
| `agentStream` timeout = 30 s              | ✅ (was 500)                                    |
| Watchdog Cloud Scheduler ENABLED          | ✅                                              |
| Firestore indexes READY (4/4)             | ✅                                              |
| Firestore TTLs ACTIVE (2/2)               | ✅                                              |
| Firebase Anonymous Auth enabled           | ✅                                              |
| Single-turn live flow works               | ✅ (browser verified, 4 min, full report)       |
| Multi-turn follow-up works                | ✅ (browser verified, B-1 fix confirmed)        |
| Adversarial review pass #1                | 20 PASS, 1 fixed                                |
| Adversarial review pass #2                | 1 BLOCKER fixed + live-verified, minor deferred |
| Vitest / functions / rules / agent pytest | ✅ (77 / 47 / 10 / 140+7 pre-existing)          |
| Lint + Prettier                           | ✅ clean                                        |
| Console errors on landing page            | 0                                               |

**Deploy is production-validated.**
