# GEAR migration — execution log

**Plan:** [`gear-migration-implementation-plan-2026-04-26.md`](./gear-migration-implementation-plan-2026-04-26.md) (v3.10, approved)
**Started:** 2026-04-27
**Executor:** Claude Code (Opus 4.7, 1M context) coordinating subagents
**Discipline:** No deviations from plan. Verify everything against facts/docs. Stop and consult on blockers.

---

## Phase status

| Phase | Title                                      | Status        | Started | Finished | Notes                                                      |
| ----- | ------------------------------------------ | ------------- | ------- | -------- | ---------------------------------------------------------- |
| 1     | Local prereqs + secret provisioning        | not started   | —       | —        | Requires user action on `gcloud` IAM grant + secret values |
| 2     | Lazy-init Gemini subclass                  | not started   | —       | —        |                                                            |
| 3     | Secret Manager runtime fetch               | not started   | —       | —        |                                                            |
| 4     | `FirestoreProgressPlugin` + `GearRunState` | not started   | —       | —        |                                                            |
| 5     | `agentStream` rewrite + `gearHandoff`      | not started   | —       | —        |                                                            |
| 6     | Frontend optimistic submission             | not started   | —       | —        |                                                            |
| 7     | A/B cutover infrastructure                 | not started   | —       | —        |                                                            |
| 8     | Production deploy + soak + flip            | calendar time | —       | —        | ~2–3 weeks; user-driven                                    |
| 9     | Cutover + cleanup                          | post-rollback | —       | —        | After 30-day window                                        |

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

(none yet)

---

## Decisions / changes / learnings

(none yet)

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

## Verification artifacts

(none yet — log green test runs, screenshots, deploy IDs here as phases finish)
