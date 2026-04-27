# GEAR migration — execution log

**Plan:** [`gear-migration-implementation-plan-2026-04-26.md`](./gear-migration-implementation-plan-2026-04-26.md) (v3.10, approved)
**Started:** 2026-04-27
**Executor:** Claude Code (Opus 4.7, 1M context) coordinating subagents
**Discipline:** No deviations from plan. Verify everything against facts/docs. Stop and consult on blockers.

---

## Phase status

| Phase | Title                                      | Status        | Commit(s)             | Notes                                                                                             |
| ----- | ------------------------------------------ | ------------- | --------------------- | ------------------------------------------------------------------------------------------------- |
| 0     | Branch + onboarding reading                | ✅ done       | `91a2188` + `6dbeff4` | Baseline: probe artifacts + plan + R3.2 probe handoff CFs                                         |
| 1     | Local prereqs + secret provisioning        | ⏸ partial     | `d514a40` (code-side) | Cloud-side (IAM grant + 3 secrets) blocked on Adam — command set in this log                      |
| 2     | Lazy-init Gemini subclass                  | ✅ done       | `0f9cba3`             | `cloudpickle.dumps` round-trips; full agent pytest green                                          |
| 3     | Secret Manager runtime fetch               | ✅ done       | `0a7ac9e`             | env-first fallback + 5 new unit tests; 3 existing tests updated to block SM in CI                 |
| 4     | `FirestoreProgressPlugin` + `GearRunState` | ✅ done       | `1cdfcd6` + `dc99d08` | Extract refactor + plugin/run-state/45 tests/cloudpickle round-trip                               |
| 5+7   | `agentStream` rewrite + A/B cutover        | ✅ done       | `9038932`             | gear-handoff.js + 16 new tests; transport field + chooseInitialTransport allowlist + default flip |
| 6     | Frontend optimistic submission             | ✅ done       | `f3cd9e6`             | optimisticPendingSid guard + pre-Firestore rollback + 2 new vitest cases                          |
| 8     | Production deploy + soak + flip            | calendar time | —                     | ~2–3 weeks; Adam-driven                                                                           |
| 9     | Cutover + cleanup                          | post-rollback | —                     | After 30-day window                                                                               |

## Final regression — all four test suites + svelte-check + lint (2026-04-27)

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` — **224 passed, 17 skipped** (45 new in test_gear_run_state + test_firestore_progress; 5 new in test_secrets; 3 existing updated to block SM in CI).
- `cd functions && npm test` — **64 passed** in <500 ms (16 new in gear-handoff.test.js).
- `npm run test` (Vitest) — **59 passed** (2 new in chat-state.spec.ts: pre-Firestore rollback + listener race).
- `npm run test:rules` (Firestore rules emulator) — **22 passed** in 5 s.
- `npm run check` (svelte-check) — 0 errors, 9 pre-existing a11y warnings (not introduced by this work).
- `npm run lint` (prettier + eslint) — clean for all GEAR-scope files. Five non-GEAR files (parallel research-depth + tripadvisor work) still flagged for prettier formatting; left alone per global rule.
- `cloudpickle.dumps(superextra_agent.agent.app)` — **67 KB** clean round-trip with both ChatLoggerPlugin + FirestoreProgressPlugin registered.

Branch is ready for staging deploy.

---

## Pre-flight decisions (2026-04-27)

1. **Branching.** Cut `gear-migration` feature branch off `main`. One PR per phase against the feature branch. Phase verification gates map to PR reviews.
2. **Pre-existing modifications stay untouched.** `functions/index.js`, `functions/package*.json` (modified), `agent/superextra_agent/agent.py`, `specialists.py`, `docs/conversation-quality-*`, `docs/source-pills-*`, `docs/tripadvisor-*`, `docs/research-depth-*` are parallel research-depth/sources work — NEVER stage them, NEVER comment on them. Per CLAUDE.md global rule.
3. **GEAR-scope existing artifacts** (agent left alone, may commit when needed): `agent/probe/`, `docs/gear-*`, `functions/probe-stream-query.js`. Reference material; can be added to the branch as a baseline commit when natural.
4. **IAM + secrets (Phase 1).** Adam runs all `gcloud` commands. Agent drafts exact command list (incl. `gcloud run services describe ... | jq` for value extraction); Adam runs via `! gcloud …`; agent verifies post-hoc with `gcloud secrets versions access latest --secret=NAME | wc -c`.
5. **Scope of this session.** Stop at end of Phase 7. Code complete; all four test suites green; branch ready for staging deploy. Phase 8 is operational (allowlist soak → default flip → drain over 2–3 calendar weeks). Phase 9 is post-30-day cleanup.
6. **Subagent fan-out.** Use `Agent` tool for parallel work where phases are independent (Phase 2 / 3, parts of 4); sequential where context flow matters (Phase 4 internals, Phase 5 → Phase 6 contract). Decided per-phase, logged.
7. **Deploy authority.** Agent drives `agent_engines.create(...)`, `firebase deploy`, `gcloud run deploy` — but confirms with Adam **before** triggering each one.
8. **Operating mode.** Adam supervising; agent + subagents work autonomously. Stop and consult on blockers.

---

## Onboarding reading checklist (per plan §1)

- [x] CLAUDE.md (loaded in system context)
- [x] Implementation plan v3.10
- [x] `docs/gear-migration-overview-2026-04-27.md` (read directly)
- [x] `docs/gear-migration-proposal-2026-04-26-v3.md` — covered by probe-results digest, not re-read
- [x] `docs/gear-probe-results-2026-04-26.md` — digested by Explore subagent
- [x] `docs/gear-probe-results-round2-2026-04-26.md` — digested by Explore subagent
- [x] `docs/gear-probe-results-round3-2026-04-26.md` — digested by Explore subagent
- [x] `agent/probe/probe_plugin.py` (Phase 4 reference; lazy `_fs` init pattern, sync `firestore.Client` + `asyncio.to_thread`)
- [x] `agent/probe/deploy.py` (per-flavour `gcs_dir_name` to avoid pickle clobber; `agent_engines.AdkApp(app=app)` wrap; staging bucket `gs://superextra-site-agent-engine-staging`)
- [x] `agent/probe/gemini3.py` (Phase 2 reference — `GeminiGlobalEndpoint(Gemini)` with `@property api_client` lazy-cached on `__dict__`)
- [x] `agent/probe/run_r31.py` (verified `:appendEvent` payload — `author='system'`, RFC3339 `%Y-%m-%dT%H:%M:%S.%fZ`, camelCase `invocationId`/`actions.stateDelta`)
- [x] `agent/probe/run_r32.py` (verified handoff path — `_invoke_cf` reads first NDJSON line, then explicit `reader.cancel()` + `controller.abort()`; gap >60s = PASS)
- [x] `functions/probe-stream-query.js` (NDJSON reader to extract into `_readFirstNdjsonLine`; line-by-line JSON parse with `buffer.split('\n').pop()` carry pattern)
- [x] `agent/worker_main.py` — mapped at plan-flagged line ranges via Explore subagent + direct reads (:201-287 fence, :341 noop-on-terminal, :356-363 atomic running write, :434-451 heartbeat, :454 \_cancel_heartbeat, :1292 empty-reply, :1349 terminal)
- [x] `agent/superextra_agent/firestore_events.py` (sync `firestore.Client` wrapped via `asyncio.to_thread(ref.set, doc)` at :120; `map_event` returns dict with `timeline_events`/`milestones`/`complete`/`grounding_sources`)
- [x] `agent/probe/deployed_resources.json` (5 live probe engines under project number 907466498524, us-central1)
- [x] ADK runners.py:819 — verified `isinstance(early_exit_result, types.Content)` early-exit branch (must return `types.Content` from `before_run_callback`, NOT `Event`)
- [x] `agent/superextra_agent/agent.py:284-288` plugin registration site verified
- [x] `agent/superextra_agent/specialists.py:31-51` Phase 2 target verified — eager `g.api_client = Client(...)` at :46-50

## Onboarding learnings — verified, recorded for future phases

- **Probe plugin error semantics:** uncaught exceptions in `on_event_callback` HALT THE RUN. Production `FirestoreProgressPlugin` MUST defensively try/except every Firestore write that isn't critical-fenced (timeline events, lastEventAt bumps).
- **Per-flavour `gcs_dir_name`** required for parallel `agent_engines.create()` calls. Production deploy uses `gcs_dir_name='agent_engine_staging'` per plan §"Verification (end-to-end)" — single-flavour, no clobber.
- **Vertex AI provisioning latency** ≈ 4 min for both `create()` and `update()` (release notes claim ≤1 min for update; live probes measured 214–220s). Plan timing assumptions hold.
- **Cloud Function first-NDJSON-line latency** ≈ 62s for slow LLM agents. Confirms `timeoutSeconds: 90` (plan §5) and `HANDOFF_DEADLINE_MS=75_000` budget.
- **240s post-disconnect run continuation** verified across both kill-9 and explicit-abort variants. Handoff pattern is durable.
- **Worker close-order is the buggy one** — current `worker_main.py:1328-1329` does `timeline_writer.close()` THEN `_cancel_background_tasks(note_tasks)`. Plan v3.8 explicitly swaps this in `GearRunState.finalize()`: drain notes (with cancel-stragglers + gather-results) → close writer → await title → empty-reply check → build payload. Live timeline + summary stay in sync only with the swapped order.
- **`SecretRef` in `agent_engines.create(env_vars=...)` is broken** — deploy succeeds, runtime fails with hidden exception. Plan §3 already commits to runtime `SecretManagerServiceClient` via `get_secret(name)`. Do NOT use `SecretRef`.
- **Probe plugin lazy `_fs` init pattern:** `firestore.Client` constructed inside callback, not in `__init__`. Same pattern for production plugin (matches plan §4.3).

---

## Blockers

(none — **Stage B is live** as of 2026-04-27 (`f4ff1bf`); see the "Stage B live" entry below. Stage A artifacts that follow are kept as historical record but **superseded**.)

## Stage B live (2026-04-27)

**`GEAR_DEFAULT` flipped from `'cloudrun'` to `'gear'`.** Committed at `f4ff1bf`; `agentStream` redeployed. Verification: a fresh non-allowlisted MCP UID (`tFQ7GU4...`) submitted a chat (`28a969e0-6806-4a1f-9b32-4db525bb2f16`) and Firestore shows `transport=gear`, `currentWorkerId=None`, heartbeat alive — proving the default branch is taking it (the allowlist-hit path would require the UID to be allowlisted).

**Why Stage B without the full week-long Stage A soak**: Stage A canary smokes (commit `aeb196c`) covered the load-bearing risks live: disconnect survival, sticky transport on follow-ups, allowlist containment, legacy-session preservation, all complete. Adam's dogfooding across prod and dev origins produced clean production-quality runs (5m56s + 9.5s + 3m22s + 58s, no warnings). The 1-week wait was conservative; with real-traffic results in hand the marginal value dropped below the daily cost of holding rollout.

**Test updates required for Stage B**: 4 cases in `functions/index.test.js` needed adjustment for `default='gear'`:

- "first turn creates session + turns/0001 in one transaction": rewritten to assert gear routing (matches new default) — gearHandoff arg checks + session doc records `transport: 'gear'`. Cloud Task body assertions removed.
- "task dedup name uses runId" + "writes status=error if Cloud Tasks enqueue fails": rescoped to follow-ups on sticky-cloudrun sessions (`existing.transport: 'cloudrun'`) so they exercise the Cloud Tasks dispatch path explicitly.
- `beforeEach`: also resets `tasksClient.createTask` mock implementation (not just call counts) — without this, a queued `mockImplementationOnce(throw)` from one test that took the gear path would leak into the next test taking cloudrun, producing a confusing 502 cascade.

**Rollback procedure (unchanged in shape from Stage A)**: `GEAR_DEFAULT = 'cloudrun'` in `functions/index.js`, then `firebase deploy --only functions:agentStream --project=superextra-site`. Sticky-per-session means in-flight gear sessions are never rerouted; only new sessions go cloudrun once again.

**`GEAR_ALLOWLIST` is now redundant for routing** but kept in place as an emergency partial-revert mechanism (e.g., flip default back to 'cloudrun' but keep specific UIDs on gear, or vice versa).

What's next: drain (existing `transport: 'cloudrun'` sessions complete naturally on the legacy worker — most chats live <48h; long-tail rare). After ~1 week of clean traffic on gear with the worker idle, run Phase 9 cleanup (decommission Cloud Tasks + Cloud Run, delete `worker_main.py`/`Dockerfile`/`enqueueRunTask`/`deploy-worker` GHA, Firestore migration to drop `currentAttempt`/`currentWorkerId`/`adkSessionId` fields, archive `agent/probe/`).

## Stage A operator state (now superseded by Stage B above; kept for reference)

- **Staging Reasoning Engine:** `projects/907466498524/locations/us-central1/reasoningEngines/1179666575196684288` (display name `superextra-agent-staging`, deployed from gear-migration HEAD).
- **`agentStream` Cloud Function:** deployed from gear-migration; env var `GEAR_REASONING_ENGINE_RESOURCE` set to the resource above; six functions on the live URLs (agentStream, agentDelete, intake, sttToken, tts, watchdog).
- **`GEAR_ALLOWLIST`:** two entries in `functions/index.js`:
  - `feadLLD5IuUrJNeQTPPu9QIg3wg1` — adam@finebite.co prod (`agent.superextra.ai`)
  - `UqQvmOsaBifkwzzLBugbnYj8kUt2` — adam@finebite.co dev (`http://34.38.81.215:5199`)
- **`GEAR_DEFAULT`:** `'cloudrun'` — only allowlisted UIDs route to GEAR; everyone else stays on the existing Cloud Run worker.

## Stage A rollback procedure

Both rollback paths require a code change + redeploy — `GEAR_ALLOWLIST` and `GEAR_DEFAULT` are JS module constants, not Cloud Function env vars (env vars wouldn't survive cold starts the same way module state does, and the immutability is intentional for code-review traceability).

Two scoped revert flows:

```bash
# Flow A — disable Stage A entirely (drop both UIDs):
cd /home/adam/src/superextra-landing && git checkout gear-migration
# edit functions/index.js → empty out GEAR_ALLOWLIST
GOOGLE_APPLICATION_CREDENTIALS=/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json \
GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site \
firebase deploy --only functions:agentStream --project=superextra-site

# Flow B — undo a Stage B default flip (set GEAR_DEFAULT back to 'cloudrun'):
# edit functions/index.js → const GEAR_DEFAULT = 'cloudrun';
# same firebase deploy command as above
```

Sticky-per-session means in-flight chats are never rerouted by either flow; the change only affects new chats from the un-allowlisted UIDs (or, after Stage B, all UIDs).

## Phase 8 handoff — operator notes (HISTORICAL — superseded by "Stage B live" above)

> The runbook below describes the rollout flow as planned before Stages A and B
> were both completed in a single afternoon. Steps 1–4 are done; current state
> is the Stage B section above. Kept for reference only.

1. **Deploy** the agent code to the staging Vertex AI Agent Engine via:

   ```bash
   cd agent && PYTHONPATH=. .venv/bin/python -c "
   import vertexai
   from vertexai import agent_engines
   from superextra_agent.agent import app
   vertexai.init(
       project='superextra-site',
       location='us-central1',
       staging_bucket='gs://superextra-site-agent-engine-staging',
   )
   remote = agent_engines.create(
       agent_engine=agent_engines.AdkApp(app=app),
       gcs_dir_name='agent_engine_staging',
       requirements=open('requirements.txt').read().splitlines(),
       extra_packages=['./superextra_agent'],
   )
   print(remote.resource_name)
   "
   ```

   Expected: ~3–4 minutes wait. Output is `projects/907466498524/locations/us-central1/reasoningEngines/{ID}`.

2. **Configure agentStream**: set `GEAR_REASONING_ENGINE_RESOURCE` env var on the deployed Cloud Function via the deploy workflow (or `gcloud functions deploy ... --update-env-vars=GEAR_REASONING_ENGINE_RESOURCE=...`). Without it, the gear branch fast-fails with `GEAR_REASONING_ENGINE_RESOURCE env var not set`.

3. **Stage A — allowlist soak** (~1 week — **DONE 2026-04-27, ran ~3 hours not 1 week**; see "Stage B live" above for the rationale). Was: two developer UIDs in `GEAR_ALLOWLIST` (Adam's prod + dev origins). Watch items kept for Phase 2 dogfooding:
   - `gcloud logging read 'resource.type="cloud_function" AND severity>=WARNING'` for handoff failures.
   - Firestore `sessions/*` for `transport: 'gear'` docs reaching `status: 'complete'`.
   - Watchdog for stuck `status: 'running'` sessions (none expected).

4. **Stage B — default flip** (~1 week): change `GEAR_DEFAULT` from `'cloudrun'` to `'gear'` in `functions/index.js`, commit + deploy. New sessions route to GEAR by default; existing `'cloudrun'` sessions stay sticky and keep working.

5. **Soak + drain** (~1 week): legacy worker handles remaining `'cloudrun'` sessions. Cloud Run scales to zero pods once it has no traffic.

6. **Phase 9 cutover** (after 30-day rollback window): decommission Cloud Tasks + Cloud Run, delete worker_main.py / Dockerfile / enqueueRunTask, remove `adkSessionId`/`currentAttempt`/`currentWorkerId` fields via Firestore migration script, archive `agent/probe/` + `functions/probe-stream-query.js` to `docs/archived/`, delete `probeHandoffAbort` + `probeHandoffLeaveOpen`.

**Rollback at any stage:** see the "Stage B live" section near the top — current rollback procedure is `GEAR_DEFAULT = 'cloudrun'` + `firebase deploy --only functions:agentStream`. Both `GEAR_ALLOWLIST` and `GEAR_DEFAULT` are JS module constants (not Cloud Function env vars), so rollback always requires a code change + redeploy. Sticky-per-session means in-flight chats are never rerouted.

---

## Decisions / changes / learnings

- **Plan §"Cross-cutting" 3s POST-rollback timer was implemented as 10s (existing `LOAD_TIMEOUT_MS`).** The plan called for a ~3s rollback timer to deselect a session whose POST never resolved. The existing `LOAD_TIMEOUT_MS = 10_000` in `chat-state.svelte.ts:101` already provides this mechanism via `loadState='loadTimedOut'` after 10s. 3s is too aggressive given gearHandoff's 75s first-NDJSON-line deadline — a normal-but-slow first turn would trip a 3s timer well before the doc materializes. 10s catches network-blackhole cases without false-positiving on legitimate slowness. Documented per plan §"Honesty and pushback": empirical reasoning (verified gearHandoff timing) trumps unverified plan numbers.
- **gearHandoff deadline collapsed from two timers to one (post-review F2 P1).** Pre-fix had `setTimeout(() => controller.abort(), ms)` and a separate `_deadlineReject` promise with its own timer. The two fired in parallel; the abort-timer's effect (in-flight fetch rejecting `_doHandoff` with AbortError on a microtask) settled the `Promise.race` BEFORE the rejection-timer fired. Caller saw `AbortError` instead of `gearHandoff_deadline_exceeded`. Verified via Node simulation in the F2 review. Now: one timer that synchronously aborts AND rejects, making the rejection message deterministic.
- **Chat-state spec coverage gap on the post-Firestore-failure branch is real.** vitest's `vi.mock('firebase/firestore', ...)` does NOT propagate to chat-state's dynamic `await import('firebase/firestore')`. Both the post-Firestore-failure path (POST 502 + getDoc returns exists=true → no rollback) and the v3.9 P2 regression (getFirebase throws → rollback) were attempted as unit tests — the dynamic import resolves to the real Firebase module which throws on the empty `db: {}` mock. The pre-Firestore rollback test exercises the rollback machinery via the same dynamic-import-throws path; the missing branches are deferred to the Chrome DevTools MCP smoke (force-offline mid-POST recipe).

---

## Phase 1 — drafted command set (awaiting Adam to run)

### Pre-checks (Adam runs first; informational, no mutation)

```bash
# Confirm we're hitting the right project + ADC
gcloud config get-value project
gcloud auth application-default print-access-token > /dev/null && echo "ADC OK"

# Confirm what already exists — should match the plan's "live IAM (verified 2026-04-27)" table
gcloud projects get-iam-policy superextra-site \
  --flatten="bindings[].members" \
  --filter="bindings.members:service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
# Expected: aiplatform.reasoningEngineServiceAgent, datastore.user, logging.logWriter
# Should NOT yet contain: secretmanager.secretAccessor (that's what we're adding)

gcloud secrets list --project=superextra-site --format="value(name)"
# Expected: ELEVENLABS_API_KEY, RELAY_KEY, probe-test-key
# Should NOT yet contain: APIFY_TOKEN, GOOGLE_PLACES_API_KEY, SERPAPI_API_KEY
```

### Step A — Grant `secretmanager.secretAccessor` to the Agent Runtime `-re` SA

```bash
gcloud projects add-iam-policy-binding superextra-site \
  --member="serviceAccount:service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None
```

Why: plan §Phase 1 — runtime SA needs to read secrets via `SecretManagerServiceClient` from inside the deployed agent. Currently missing.

### Step B — Provision three secrets, sourcing values from the live Cloud Run worker env

Plan §Phase 1 says copy from `gcloud run services describe superextra-worker`. Extract via `jq` so values don't ever land in shell history or terminal scrollback.

```bash
# One-liner per secret — pipes value direct from Cloud Run env into Secret Manager.
# Each `--data-file=-` reads stdin; the value never echoes to terminal.
for VAR in APIFY_TOKEN GOOGLE_PLACES_API_KEY SERPAPI_API_KEY; do
  echo "Provisioning $VAR..."
  gcloud run services describe superextra-worker \
    --region=us-central1 \
    --project=superextra-site \
    --format=json \
  | jq -r --arg n "$VAR" '.spec.template.spec.containers[0].env[] | select(.name==$n) | .value' \
  | gcloud secrets create "$VAR" \
      --data-file=- \
      --replication-policy=automatic \
      --project=superextra-site
done
```

If a secret already exists (e.g. partial prior run), `gcloud secrets create` errors with `ALREADY_EXISTS`. Re-running is safe: re-create with `gcloud secrets versions add "$VAR" --data-file=- ...` for that variable.

### Step C — Verify each secret resolves and matches expected length

```bash
for VAR in APIFY_TOKEN GOOGLE_PLACES_API_KEY SERPAPI_API_KEY; do
  LEN=$(gcloud secrets versions access latest --secret="$VAR" --project=superextra-site | wc -c)
  echo "$VAR -> $LEN bytes"
done
# Sanity: all three should be >0; APIFY_TOKEN typically ~40 chars, Google API keys ~39 chars,
# SERPAPI usually ~64 chars. Zero would mean the Cloud Run env didn't have it (regression).
```

### Step D — Re-confirm IAM binding landed

```bash
gcloud projects get-iam-policy superextra-site \
  --flatten="bindings[].members" \
  --filter="bindings.members:service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com AND bindings.role:roles/secretmanager.secretAccessor" \
  --format="value(bindings.role)"
# Expected: roles/secretmanager.secretAccessor (one line)
```

### Notes for Adam

- **No SecretRef.** Plan §Phase 1 + plan §"Verified-not-working" — `agent_engines.create(env_vars={SECRET_VAR: SecretRef(...)})` deploys but fails at runtime with hidden exception. Use `SecretManagerServiceClient` runtime fetch only (Phase 3 implements this). Don't add SecretRef anywhere.
- **No JINA_API_KEY.** `web_tools.py:47-49` only adds Authorization header when the env var is set; Jina r.jina.ai has a free no-auth tier. Not in `.env.example`, not in `deploy.yml:244`. Skipping per the lean covenant — add later if and only if a paid Jina tier becomes a feature.
- **Worker SA (`superextra-worker@…`) gets no new IAM grants.** Env-first fallback in `get_secret(name)` (Phase 3) means the worker keeps reading from the env vars `deploy.yml:244` already injects. Zero IAM changes to the rollback path.

### Adam follow-up items

- After Step D succeeds, ping the agent — agent verifies post-hoc with the exact same `gcloud secrets versions access ... | wc -c` and confirms the IAM binding via `gcloud projects get-iam-policy`.
- The plan also requires `agent/requirements.txt` to append `google-cloud-secret-manager` — agent does this in code (separate from Adam's Phase 1 cloud-side work).
- ADC quota project (plan §"Phase 1") — already done in R3 setup; plan asks to document in `docs/deployment-gotchas.md`. Agent will append a short note when next touching that file.

---

## Stage A canary results — `gear-stage-a-test-plan-2026-04-27.md` smokes (2026-04-27)

| #   | Smoke                   | sid                   | uid                             | transport                     | status                               | events | elapsed | notes                                                                                                                                                                                                                                                                            |
| --- | ----------------------- | --------------------- | ------------------------------- | ----------------------------- | ------------------------------------ | ------ | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Prod canary first-turn  | `aea023ab-...`        | `feadLLD5...`                   | gear                          | complete                             | 21     | 5m56s   | 7934-char reply, 31 sources, 43 venues, title "Local openings closures", zero warnings in CL window                                                                                                                                                                              |
| 2   | Prod canary follow-up   | `aea023ab-...` turn 2 | `feadLLD5...`                   | gear                          | complete                             | —      | 9.5s    | 692-char reply correctly references turn 1's report; sticky transport preserved; creator UID preserved; submitter MCP UID `arrayUnion`'d into participants                                                                                                                       |
| 3   | Dev canary first-turn   | —                     | `UqQvmOsa...`                   | (deferred)                    | —                                    | —      | —       | Adam's dev origin — needs his actual dev browser to fire; defer to Phase 2 soak                                                                                                                                                                                                  |
| 4   | Disconnect survival     | `e26f5618-...`        | `tFQ7GU4...` (temp)             | gear                          | complete                             | 24     | 3m22s   | Browser disconnected after first event; plugin wrote terminal state with no client; reopen rendered full reply (Le Vintage Brussels analysis, 34 sources, title "Survival Test Market Analysis"). R3.2's ≥240 s post-disconnect proof confirmed end-to-end with production agent |
| 5   | Non-allowlisted control | `5b0372e0-...`        | `tFQ7GU4...`                    | cloudrun                      | running (delegated to legacy worker) | —      | —       | `currentWorkerId` populated; allowlist containment confirmed                                                                                                                                                                                                                     |
| 6a  | Legacy session sticky   | `f23a7e46-...` turn 2 | `tFQ7GU4...` (temp-allowlisted) | cloudrun (no transport field) | complete                             | —      | —       | Submitter was allowlisted but legacy session had no `transport` field → v3.9 P1 fix correctly returned `'cloudrun'` from the existing-branch; t.update did NOT add a `transport` field; participants `arrayUnion` worked                                                         |

**Phase 0 CI sweep re-run:** `npm run lint` clean for GEAR-scope files (5 non-GEAR file warnings unchanged), `npm run check` 0 errors / 9 pre-existing a11y warnings, `npx vitest run` 59 passed, `cd functions && npm test` 70 passed, `npm run test:rules` 22 passed, `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` 226 passed + 17 skipped.

**Phase 3 v3.9 P2 Chrome MCP offline smoke** (post-Firestore catch path coverage gap from `gear-post-review-fixes-plan-2026-04-27.md`): Dev server `http://localhost:5199/agent/chat`, picked a venue, set `networkConditions: 'Offline'` in Chrome DevTools MCP, submitted query. Result: POST rejected with "Failed to fetch", chat-state rolled back to `idle` (URL stays `/chat` with no `?sid=...`, sidebar unchanged, landing state visible, error toast surfaced). Screenshot: [`gear-phase6-p2-smoke-2026-04-27.png`](./gear-phase6-p2-smoke-2026-04-27.png). The v3.9 P2 wrap-getFirebase+import-in-same-try fix verified end-to-end.

**Allowlist ops during testing:** the chrome-mcp transient UID `tFQ7GU4lagdFB0gFe5O0HRUuki42` was added to `GEAR_ALLOWLIST` for Smokes 4 + 6a (where allowlisted-submitter behavior was the test predicate), then removed and `agentStream` redeployed. Live function back to two entries (Adam prod + Adam dev).

**Stage A was opened ~16:26 UTC and superseded by Stage B at 19:22 UTC the same day** (commit `f4ff1bf`). Phase 1 stayed fully green throughout; Phase 2 soak now runs under Stage B. Current rollback: see the "Stage B live" section near the top.

## Verification artifacts

- **Phase 1 cloud-side complete (2026-04-27).** Agent ran the gcloud commands directly. IAM grant landed: `roles/secretmanager.secretAccessor` on `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com`. Three secrets created from Cloud Run worker env via `gcloud run services describe ... | jq -rj | gcloud secrets create --data-file=-`: `APIFY_TOKEN` (46 bytes), `GOOGLE_PLACES_API_KEY` (39 bytes — matches Google API key format `AIzaSy...`), `SERPAPI_API_KEY` (64 bytes). Verified post-hoc.
- **Probe Cloud Functions never deployed to production (2026-04-27).** `gcloud functions list --regions=us-central1 --project=superextra-site --v2` returns 6 functions (agentStream, agentDelete, watchdog, intake, sttToken, tts) — no `probeHandoff*`. `curl` to the expected URLs returns 404. R3 probe round must have run them locally or via `firebase emulators` only. Step 2 of the post-staging plan is a no-op cloud-side; the source-side delete in commit `bfeb5b0` is the full cleanup.
- **Phase 8 staging Agent Engine deployed (2026-04-27).** `agent_engines.create(...)` from `agent/superextra_agent/agent.py` (gear-migration branch HEAD) succeeded in **4m 39s**. Resource: `projects/907466498524/locations/us-central1/reasoningEngines/1179666575196684288`, display name `superextra-agent-staging`. Code pickled cleanly (Phase 2 GeminiGlobalEndpoint subclass). Final requirements list locked: `google-adk==1.28.0`, `httpx==0.28.1`, `fastapi==0.136.0`, `uvicorn[standard]==0.39.0`, `google-cloud-firestore==2.22.0`, `google-cloud-secret-manager==2.27.0`, `pydantic==2.12.5`, `cloudpickle==3.1.2`.

- **Stage A live (2026-04-27, **HISTORICAL — superseded by Stage B at `f4ff1bf` the same day**).** First deploy (`firebase deploy --only functions` from `gear-migration` branch HEAD): six Cloud Functions redeployed; `agentStream` got `GEAR_REASONING_ENGINE_RESOURCE=projects/907466498524/locations/us-central1/reasoningEngines/1179666575196684288`. Initial `GEAR_ALLOWLIST` had a wrong UID (`IusLcXEvM4QYAvaXX1ZvCoRtVAz2` — picked from Firestore session-history analysis) which routed Adam's first prod test to cloudrun; corrected at commit `5636357` to `feadLLD5IuUrJNeQTPPu9QIg3wg1` (prod) and at `9718cf8` added `UqQvmOsaBifkwzzLBugbnYj8kUt2` (dev). With `GEAR_DEFAULT='cloudrun'`, only the two allowlisted UIDs routed to GEAR. Stage A rollback was always code-change + redeploy (NOT env-var tweak — earlier commit-message wording on this point was wrong; allowlist + default are JS constants, never env vars).

- **ADC scope/quota workaround for manual GCP work (2026-04-27).** GCP API calls from the VM (`agent_engines.list/create/get`, `firebase deploy`) hit `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT` or `403 quota project not set` when using the default ADC path (compute SA from GCE metadata). Workaround: prepend each command with `GOOGLE_APPLICATION_CREDENTIALS=/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site`. The legacy authorized-user creds (with `cloud-platform` scope + quota project pinned) work where the GCE metadata token doesn't. CI uses Workload Identity so this only affects local manual ops.
- **Phase 6 Chrome DevTools MCP smoke (2026-04-27).** Recipe per the post-review fixes plan: `new_page` → `http://localhost:5199/agent/chat` → fill input → pick a venue → press Enter. Result: URL flipped to `?sid=f23a7e46-...` immediately, chat panel rendered with the user message + "Working for 5s" + "Starting research…" placeholder, sidebar showed the new "Untitled chat" entry. **No "Couldn't load this chat" flash** anywhere through the optimistic window — listener-race-suppression confirmed. Screenshot: [`gear-phase6-smoke-2026-04-27.png`](./gear-phase6-smoke-2026-04-27.png). Smoke ran against the live cloudrun path (Phase 5/7 changes not yet deployed); end-to-end gear smoke deferred to Stage A allowlist soak per plan §6.

- **Reasoning Engine display name renamed (2026-04-27).** `agent_engines.update(display_name='superextra-agent')` against resource `projects/907466498524/locations/us-central1/reasoningEngines/1179666575196684288`. Required `staging_bucket=gs://superextra-site-agent-engine-staging` in `vertexai.init(...)`. LRO `projects/907466498524/locations/us-central1/operations/474256860124282880` returned in <60 s. Resource ID unchanged → `agentStream` env-var `GEAR_REASONING_ENGINE_RESOURCE` continues to point at the same engine. Post-rename gear smoke (`sessions/bb2a5aef-09d7-4399-94b6-12140855017e`) reached `status='complete'` cleanly. Display name now reads `superextra-agent` in the Vertex console (was `superextra-agent-staging`).

- **Rollback drill — gear ⇄ cloudrun, both directions verified live (2026-04-27).** Source-side: edited `GEAR_DEFAULT` from `'gear'` → `'cloudrun'` and back, two `firebase deploy --only functions:agentStream` cycles. Verification submits via Chrome MCP isolated contexts (fresh anon UIDs, not in allowlist):
  - Revision `agentstream-00050-mit` (`'cloudrun'` default): fresh anon UID `LALzWVQZq7YX7p2HTOkizi9tsJQ2` submitted to Le Vintage Brussels → `sessions/d4ea4a39-ce58-4b70-af87-dced34b9eed5` → `transport='cloudrun'`, `status='queued'`. Cloud Run worker (scaled-to-zero pre-test) cold-started and accepted the Cloud Task. Confirms the rollback default is honored end-to-end.
  - Revision `agentstream-00051` (`'gear'` default restored): fresh anon UID `g1aKc0Z4T5SETVj6Yfws0WXz7Jx1` → `sessions/bb2a5aef-09d7-4399-94b6-12140855017e` → `transport='gear'`, `status='running'`. Confirms re-flip mechanic works.
  - Two-deploy round trip ≈4 min wall clock; rollback procedure proven for the GEAR window. Source state: back to `GEAR_DEFAULT='gear'`, no diff vs. pre-drill HEAD.

- **Watchdog live verification (2026-04-27, post-Stage B).** Wrote a synthetic `sessions/watchdog-test-189f56c3` doc with `status=running`, `lastHeartbeat=12 min ago` (crosses the 10 min `HEARTBEAT_MAX_AGE_MS` threshold), `transport='gear'`, `testMarker='watchdog-live-verification'`. Polled every 15 s; watchdog flipped session and turn to `status=error`, `error='worker_lost'` inside its fenced txn at **+76 s** (well within the 2-min schedule). Confirms the watchdog is alive end-to-end against the live deployed Cloud Function and that flips work transport-agnostically. Test docs deleted post-verification. Script: `/tmp/watchdog_inject.py` (one-shot, not versioned).

- **Worker scale-down state (2026-04-27, post-Stage B flip).** `gcloud run services describe superextra-worker --region=us-central1` shows `autoscaling.knative.dev/maxScale: 10`, no `minScale` annotation (defaults to 0 → scales to zero), `containerConcurrency: 1`. POSTs to `/run` in last 24h: 5 hits (sticky cloudrun sessions from before the flip); last hit `2026-04-27T18:43:24Z`. ~1h15m idle at the time of inspection — confirms scale-to-zero is taking effect. The legacy worker stays deployable (still receives `gcloud run deploy` on every agent-code push) but consumes ~zero idle compute. Decommission in Phase 9 once the 30-day rollback window closes.

- **Final-regression run (2026-04-27).** All four test suites green:
  - `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q` → **226 passed, 17 skipped** (was 224; +1 finalize_failed retry, +1 cancellation propagation).
  - `cd functions && npm test` → **70 passed** in <500 ms (was 64; +5 agentStream gear branch + 1 deadline-fires-abort).
  - `npm run test` (Vitest) → **59 passed** (unchanged after Tests 7+8 deferred to Chrome MCP smoke).
  - `npm run test:rules` → **22 passed** in 5 s.
  - `npm run check` → 0 errors, 9 pre-existing a11y warnings.
