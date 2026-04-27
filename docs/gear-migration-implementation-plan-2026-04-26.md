# GEAR migration — implementation plan (v3.10, approved for implementation)

**Original date:** 2026-04-26 · **Last revised:** 2026-04-27 (v3.10 — onboarding section added for executing agent)
**Status:** Implementation plan, ready to execute (incorporates v3.1 reviewer corrections)
**Migration proposal:** [`gear-migration-proposal-2026-04-26-v3.md`](./gear-migration-proposal-2026-04-26-v3.md)
**Leadership/PM overview (non-technical):** [`gear-migration-overview-2026-04-27.md`](./gear-migration-overview-2026-04-27.md)
**Probe artifacts:** [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md), [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md), [`gear-probe-results-round3-2026-04-26.md`](./gear-probe-results-round3-2026-04-26.md)
**Probe execution log (timestamped):** [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md)

---

## Executing this plan — onboarding for a fresh agent

You are picking up an approved, empirically-validated migration plan. The verification work is done; the implementation is not. Read this section before opening any phase.

### 1. Read in this order before writing any code

1. **`CLAUDE.md` (repo root)** — branding, stack, Svelte 5 rules, deploy flow, dev-server discipline (systemd, port 5199), test commands, "don'ts". The hard constraints in there override anything you remember from training.
2. **`docs/gear-migration-overview-2026-04-27.md`** — non-technical mental model of the migration. Two minutes. Tells you the _why_ in plain English so subsequent technical decisions make sense.
3. **`docs/gear-migration-proposal-2026-04-26-v3.md`** — the approved technical proposal this plan implements. Read for architectural shape; the implementation plan refines it.
4. **All three probe-result docs** — these are the empirical contract. They contain the _verified_ request/response shapes for `:createSession`, `:appendEvent`, `:streamQuery`, the verified IAM grants, the verified handoff timing (240s post-disconnect), and the verified gotchas. **If something here disagrees with your training data or the official Vertex docs, the probe results win** — they were tested live against the real platform.
5. **This plan, end to end** — phases are mostly independent but the cross-cutting design decisions section explains why the code looks the way it does.

### 2. Verified-working code to study (do not rewrite from scratch)

The probing work produced reusable scaffolding. Read these before writing the equivalent production code:

- **`agent/probe/probe_plugin.py`** — the prototype `FirestoreProgressPlugin`. ADK callback signatures are _empirically verified_ against `google-adk==1.28.0` (see file docstring). Phase 4's `FirestoreProgressPlugin` is essentially this plugin, fenced and hardened.
- **`agent/probe/deploy.py`, `run_probe.py`, `prod_shape.py`, `gemini3.py`** — working `agent_engines.create(...)` deployment, working invocation patterns, working Gemini-3 lazy-init subclass (Phase 2's reference implementation).
- **`agent/probe/run_r31.py`, `run_r32.py`** — the R3 test scripts. `run_r31.py` is the verified `:appendEvent` payload (`author='system'`, RFC3339 timestamp, camelCase). `run_r32.py` is the verified Cloud Function handoff pattern (read first NDJSON line → `reader.cancel()` → `controller.abort()` → 202).
- **`functions/probe-stream-query.js`** — the working NDJSON streaming reader for Vertex AI streamQuery responses (Vertex's `?alt=sse` is _not_ standard SSE; it's NDJSON. Phase 5 extracts `_readFirstNdjsonLine` from this file).
- **`agent/worker_main.py`** — the production code being replaced. The plan calls out specific line ranges to mirror (fencing pattern at `:201-287`, heartbeat loop at `:434-451`, terminal sequence at `:1095-1349`, empty-reply check at `:1292`). Read those passages before writing the GEAR equivalents.
- **`agent/superextra_agent/firestore_events.py`** — `map_event`, `extract_sources_from_grounding`, `write_event_doc`. The plugin's `on_event_callback` reuses these unchanged; do not reimplement.
- **`agent/probe/deployed_resources.json`** — resource IDs of the five live probe Agent Runtime instances under `superextra-site` / `us-central1` (project number 907466498524). They stay deployed until Phase 9 cleanup; you can target them for ad-hoc verification without redeploying.

### 3. External docs — do NOT rely on training knowledge

CLAUDE.md says "verify, don't guess" and that applies here in spades. The platform's behaviour drifted from its docs in four places during probing. Always fetch the live source:

- **ADK** — `https://adk.dev/llms.txt` (top-level TOC), `https://github.com/google/adk-samples` (canonical patterns), `https://github.com/google/adk-python` (API signatures + recent changes).
- **Vertex AI Agent Engine REST** — fetch live (`gcloud` CLI help or Google Cloud docs site). The probe results are the authoritative reference for the endpoints we _use_; for anything not in the probe results, fetch live before guessing.
- **Firebase Functions Gen 2 termination semantics** — relevant to Phase 5. Background work after `res.send()` is officially undefined; the plan uses explicit `controller.abort()` + `reader.cancel()` for that reason.
- **Svelte 5 / SvelteKit 2 / Tailwind v4** — there is an MCP server (`mcp__svelte__*`) that returns official docs. Use it for any Phase 6 question. CLAUDE.md mandates it.

### 4. Environment facts you cannot derive

| Fact                                           | Value                                                                                                                                                                  |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GCP project                                    | `superextra-site`                                                                                                                                                      |
| GCP project number                             | `907466498524`                                                                                                                                                         |
| Region                                         | `us-central1`                                                                                                                                                          |
| Agent Runtime runtime SA                       | `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com`                                                                                                    |
| Worker SA (Cloud Run, rollback window)         | `superextra-worker@superextra-site.iam.gserviceaccount.com`                                                                                                            |
| Staging bucket for `agent_engines.create(...)` | `gs://superextra-site-agent-engine-staging`                                                                                                                            |
| Hosting sites                                  | `superextra-landing` (`landing.superextra.ai`), `superextra-agent` (`agent.superextra.ai`)                                                                             |
| Dev server                                     | port 5199, managed by `systemctl --user` — never run `npm run dev` manually (CLAUDE.md)                                                                                |
| Live IAM (verified 2026-04-27)                 | runtime SA has `aiplatform.reasoningEngineServiceAgent`, `datastore.user`, `logging.logWriter`. **Missing**: `secretmanager.secretAccessor` — Phase 1 grants it.       |
| Existing Secret Manager secrets                | `ELEVENLABS_API_KEY`, `RELAY_KEY`, `probe-test-key`. **Missing**: `APIFY_TOKEN`, `GOOGLE_PLACES_API_KEY`, `SERPAPI_API_KEY`, `JINA_API_KEY` — Phase 1 provisions them. |

### 5. Verified-not-working — don't re-litigate

These were tested live and confirmed broken/missing. Don't waste time rediscovering:

- `sessions.patch` cannot mutate `sessionState`. Platform error explicitly redirects to `:appendEvent`. (R3.1)
- `:appendEvent` rejects Unix-float timestamps; requires RFC3339 string. (R3.1)
- `:appendEvent` rejects snake_case field names; requires camelCase (`invocationId`, `stateDelta`, `sessionState`). (R3.1)
- `sessionId` regex is `[a-z][a-z0-9-]*[a-z0-9]` — no underscores, no uppercase. Use `se-{sid}` shape. (R3.1)
- Vertex AI `:streamQuery?alt=sse` is NDJSON, not standard SSE. EventSource clients fail; line-by-line JSON parsing works. (R2.7)
- Agent Runtime logs do NOT surface in Cloud Logging API even with full IAM. Firestore-driven observability stays. (R2.6)
- Removing function source from `functions/index.js` does NOT auto-delete deployed Gen 2 functions. Explicit `firebase functions:delete` required. (R3 cleanup)
- ADC quota project must be `superextra-site` for `firebase deploy` from the VM. Either edit `~/.config/gcloud/legacy_credentials/.../adc.json` or set `GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site`. (R3 setup)

### 6. Build / test / lint discipline

CLAUDE.md is authoritative. Brief reminder of the four test suites that gate every PR touching this code:

```bash
npm run test                                            # Vitest (chat-state, etc.)
cd functions && npm test                                # Cloud Function tests
npm run test:rules                                      # Firestore rules emulator
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v     # agent Python tests
```

Plus: `npm run lint`, `npm run check` (svelte-check), `npm run format`. CI runs all of these before deploy.

### 7. Phase-completion criteria

Each phase has its own "Verification" block. Treat it as a hard gate — do NOT advance to the next phase until that block runs green. The plan is sized so phases are independently verifiable; if a phase's verification can't pass, the design has drifted and you should stop and re-read the cross-cutting decisions before patching around it.

For UI work in Phase 6: CLAUDE.md mandates Chrome DevTools MCP for any browser verification. A passing Vitest suite is necessary but not sufficient — the visual smoke test is the real gate.

### 8. Working with this plan, not against it

This plan went through 9 reviewer rounds. Every line that looks defensive (retries, fences, ordering constraints, optimistic guards) is there because a specific failure mode was identified and verified. Before "simplifying" something, find the corresponding revision-history entry — it will name the scenario the simplification would re-break. If it doesn't, that's the only time it's safe to simplify.

If you discover a scenario the plan doesn't cover: stop, document it, ask. Don't paper over it with defensive code; the plan's whole shape is "verified mechanics + minimum scaffolding". Adding speculative defensive layers is the failure mode the lean pass (v3.6) explicitly removed.

---

## Context

Migration approved per the v3 proposal. Reviewer found six implementation-spec gaps in v3 that need resolving in code (not just in the proposal):

1. **Frontend optimistic submission** — agentStream now blocks ~60–90s waiting for first NDJSON line; today's `chat-state.svelte.ts:528` waits for that POST to return before `selectSession`. Without an optimistic flip, the user sees a 60s blank screen on every first turn.
2. **Plugin-level fenced writes + status transitions** — current worker fences heartbeat/terminal writes via `currentAttempt + currentWorkerId` (`agent/worker_main.py:201, 243, 356`). The new plugin needs equivalent guards, keyed by `currentRunId` + `status`.
3. **Per-invocation plugin state** — concurrent invocations on the same Agent Runtime container would corrupt a singleton heartbeat task or sequence counter. Plugin state must be a map keyed by `invocation_id`.
4. **Status transitions** — `before_run_callback` must atomically set `sessions/{sid}.status='running'` AND `turns/{nnnn}.status='running'` (mirror of `worker_main.py:356,363`); `after_run_callback` must do the same for terminal states.
5. **Verified `:appendEvent` payload** — R3.1 used `author='system'`; v3 prose drifted to `author='agentStream'`. Use the exact tested value.
6. **Pre-handoff failure handling** — if `:createSession`/`:appendEvent`/`:streamQuery`/first-line-read fails after the Firestore session txn already wrote `status='queued'`, agentStream must flip to `status='error'` and return 502, mirroring the existing pattern at `functions/index.js:371-383`.

Goal: complete-but-lean implementation. Code that works reliably. No symptom-fixing — fix root causes. Keep the surface area for bugs small.

---

## Cross-cutting design decisions

**Single fence: `currentRunId` + `status`.** Today: `(currentAttempt, currentWorkerId)`. After migration: `currentRunId` plus the doc's `status` field. The status transition `queued → running` is itself an exclusive lock — only one Firestore txn can flip it. Once a run is `'running'`, the only way to leave that state is via the same plugin's terminal write OR a watchdog/cleanup flip — both advance status, which the fence catches. Adding a separate `currentInvocationId` field doesn't catch a single scenario the simpler `(currentRunId, status='running')` pair doesn't.

Drop `currentAttempt`, `currentWorkerId` (Cloud-Tasks-takeover concepts that don't apply to Agent Runtime), and don't add `currentInvocationId`. Net: −2 Firestore fields, +0. `invocation_id` stays in plugin docs (`probe_runs/...`) and Cloud Logging for debugging — just not as a fencing field on the session doc.

**Coexistence rule for `currentAttempt`/`currentWorkerId`.** GEAR-path runs DO NOT read these fields — the plugin's fence is `(currentRunId, status='running')` only. But the Cloud Run worker keeps using them through the rollback window: `worker_main.py` reads/writes them on every `transport='cloudrun'` session, and removing them from the worker's writes before Phase 9 would break the legacy fence. So both paths coexist by _transport_, not by _codepath_.

**Implementation deviation (shipped as-of Stage B):** rather than branch the agentStream txn body on `transport`, the shipped `agentStream` writes the same `perTurn` payload — `currentAttempt: 0`, `currentWorkerId: null` — for both transports (see `functions/index.js:324`, the `perTurn` block applied to both `t.set` first-message path and `t.update` follow-up path). For gear runs these fields are **inert writes** the plugin never reads or updates. The simplification keeps the txn body uniform and avoids a stale-on-rollback hazard where flipping `GEAR_DEFAULT` back to `'cloudrun'` would have to also remember to start writing the legacy fence fields. Trade-off accepted: two extra Firestore fields per gear session through the GEAR window. **Phase 9 cleanup:** when the worker is decommissioned, drop `currentAttempt` and `currentWorkerId` from `perTurn` in `agentStream` (one delete, two field references); the Firestore migration script removes them from existing docs.

**`GearRunState` — single object owns all per-invocation state.** Replaces today's nine local variables in `worker_main.py:1095-1230` (`final_reply`, `final_sources`, `specialist_sources`, `specialist_sources_seen`, `mapping_state`, `timeline_builder`, `timeline_writer`, `note_tasks`, `title_task`) plus the heartbeat task. Plugin keeps `dict[invocation_id, GearRunState]`. `before_run_callback` constructs and registers; `on_event_callback` mutates accumulator fields directly; `after_run_callback` cancels heartbeat first, then writes terminal state from accumulated values, then pops.

**No per-run lock.** Today's worker has zero locks and runs the same concurrency surface for months without races. The discipline that makes this safe: builder mutation methods (`add_note`, `observe_event`) are synchronous and `await`-free, so they execute atomically once they start. `TimelineWriter` owns its own internal lock for its Firestore writes. Note tasks only touch the builder via these synchronous methods. We're not introducing any new race by relocating this pattern.

**Sync Firestore client + `asyncio.to_thread` everywhere — matches existing code.** `firestore_events.write_event_doc:98` uses sync `firestore.Client` and wraps with `asyncio.to_thread(ref.set, doc)`; the worker's transactional helpers use `firestore.transactional` (sync). The plugin and its helpers MUST use the same pattern — passing an `AsyncClient` to the reused `write_event_doc` would break it. All transactional logic functions are sync; the async wrapper does `await asyncio.to_thread(_logic, fs.transaction(), ...)`.

**Two fenced-write helpers, different predicates:**

- **`claim_invocation(state)`** — used ONCE by plugin's `before_run_callback` to take ownership. Predicates inside the transaction: `data.currentRunId == state.run_id` AND `data.status == 'queued'` AND turn `data.status == 'pending'`. If session is already `'error'` or `'complete'` (handoff failed and cleanup wrote error, or watchdog flipped it), short-circuit by **returning a `types.Content` from `before_run_callback`** — the ADK runner at `agent/.venv/.../runners.py:819` checks `isinstance(early_exit_result, types.Content)` and wraps the content into an Event itself; returning a bare Event would NOT take this branch. On predicate match: atomically write `status='running'`, `lastHeartbeat`, `lastEventAt`, and turn `status='running'`.
- **`fenced_session_and_turn_update(state, session_updates, turn_updates)`** — used by heartbeat ticks, terminal writes, and `lastEventAt` bumps. Predicates: `data.currentRunId == state.run_id` AND `data.status == 'running'`. The `status == 'running'` predicate prevents resurrecting a run that the watchdog or `gearHandoffCleanup` already flipped to `'error'`. Mirrors the spirit of `worker_main.py:341` ("if status in ('complete', 'error'): noop_complete"). Raises `OwnershipLost` on any predicate failure.

**`gearHandoff(sid, runId, message, ...)` — one CF-side helper for the dispatch sequence.** Wraps: idempotent `:createSession` (treat ALREADY_EXISTS as success), `:appendEvent`, `:streamQuery` with `AbortController`, first-NDJSON-line read, `reader.cancel()` + `controller.abort()`, transactional session+turn cleanup on any failure with internal timeout. One unit test covers the happy path; one covers each failure shape. **No `adkSessionCreated` boolean** — the existing `isFirstMessage` path in agentStream's Firestore txn determines whether to call `:createSession`, and ALREADY_EXISTS treats network-retry duplicates idempotently.

**Write-class taxonomy** — three classes with different error semantics:

- **Critical** — takeover (status='running'), terminal write (complete/error). `fencedSessionAndTurnUpdate`, propagate `OwnershipLost`, log.
- **Heartbeat** — periodic `lastHeartbeat`. Fenced; on `OwnershipLost` exit task cleanly; on transient blip log + continue.
- **Best-effort** — timeline events, source extraction, `lastEventAt` ticks per event. `try/except` swallow + log; never halt the run.

**Empty-reply sanity check** (mirrors `worker_main.py:1292`). `after_run_callback` checks `GearRunState.final_reply` is non-empty after stripping. If empty: terminal write with `status='error'`, `error='empty_or_malformed_reply'`. NOT `status='complete'`. This catches the case where no final event is ever emitted (synth crash, model returns empty, etc.) and is the existing worker behaviour we must preserve.

**Failure cleanup writes session+turn transactionally** (mirrors `watchdog.js:172-186`). Both today's worker terminal writes (`worker_main.py:1349`) and the watchdog write session AND turn together. agentStream's pre-handoff failure cleanup must do the same (existing `enqueue_failed` path at `index.js:371-383` is a known inconsistency we don't perpetuate). `gearHandoff` includes a transactional `fencedSessionAndTurnUpdate` cleanup helper.

**App-level timeout for `gearHandoff` cleanup, with shared `AbortController`.** CF `timeoutSeconds: 90`. Internal `Promise.race` budget for the dispatch sequence: ~75s. **One `AbortController` is constructed at `gearHandoff` scope and passed into every `fetch` call** (`createSession`, `appendEvent`, `streamQuery`); when the deadline rejects, we call `controller.abort()` so all in-flight HTTP work is cancelled — not just streamQuery. Without this hoist, losing-side fetches keep running as background work and Firebase's documented "no progress after termination" warning bites. Cleanup runs synchronously in the catch block under the remaining ~15s of CF budget.

**Frontend optimistic submission with `optimisticPendingSid` guard + local rollback.** `chat-state.svelte.ts:534` `selectSession(sid)` moves _before_ `await postAgentStream(...)`. **The session listener at `chat-state.svelte.ts:307` flips `loadState='missing'` immediately on a server-confirmed `exists=false`** — without protection, the user sees "Couldn't load this chat" briefly while waiting for agentStream's Phase 1 txn to land.

Add `optimisticPendingSid: string | null` to chat-state. While `optimisticPendingSid === activeSid`, the listener suppresses the `missing` transition (keeps `loadState` as `'loading'`). The pending state clears on whichever happens first: (a) doc materializes (`exists=true`, normal transition to `'loaded'`), (b) POST resolves successfully (let the listener take over), (c) ~3s rollback timer fires (POST never resolved, still no doc → real failure: deselect, surface error).

If POST rejects after the doc materializes (Phase 2+ failure), the doc already has `status='error'` from `gearHandoffCleanup` — listener renders error via existing `loadState` machinery. No frontend rollback needed for that path.

**A/B via `transport: 'cloudrun' | 'gear'`.** Sticky per-session, set on first turn. agentStream reads it for follow-ups; legacy worker handles `'cloudrun'` sessions through the rollback window.

---

## Phase 1 — Local prerequisites + secret provisioning (1 day)

**Files**:

- `agent/requirements.txt` — append `google-cloud-secret-manager`
- `functions/package.json` — `google-auth-library` already added in R3 setup, keep
- `agent/probe/probe_plugin.py:64` — `invocation_id` field already added in R3 setup, keep

**IAM grants verified live (2026-04-27).** The `-re` runtime SA currently has:

- `roles/aiplatform.reasoningEngineServiceAgent` (default)
- `roles/datastore.user` (granted in R1)
- `roles/logging.logWriter` (granted in R2.6 troubleshooting)

**Missing — must grant before Phase 3 runs:**

```bash
PROJECT_NUMBER=907466498524
gcloud projects add-iam-policy-binding superextra-site \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None
```

**Secret Manager secrets to provision before Phase 3.** Currently only `ELEVENLABS_API_KEY`, `RELAY_KEY`, `probe-test-key` exist. The agent secrets are NOT yet provisioned:

```bash
# Replace existing Cloud Run env vars with Secret Manager entries
echo -n "$APIFY_TOKEN_VALUE"        | gcloud secrets create APIFY_TOKEN        --data-file=- --replication-policy=automatic --project=superextra-site
echo -n "$GOOGLE_PLACES_API_KEY_VAL"| gcloud secrets create GOOGLE_PLACES_API_KEY --data-file=- --replication-policy=automatic --project=superextra-site
echo -n "$SERPAPI_API_KEY_VAL"      | gcloud secrets create SERPAPI_API_KEY    --data-file=- --replication-policy=automatic --project=superextra-site
echo -n "$JINA_API_KEY_VAL"         | gcloud secrets create JINA_API_KEY       --data-file=- --replication-policy=automatic --project=superextra-site  # if used
```

Source values: copy from current Cloud Run service env vars (`gcloud run services describe superextra-worker --format='value(spec.template.spec.containers[].env)'`). Verify each secret resolves before Phase 3:

```bash
gcloud secrets versions access latest --secret=APIFY_TOKEN --project=superextra-site | wc -c
```

**ADC quota project** — already done in R3 setup; document in `docs/deployment-gotchas.md`.

---

## Phase 2 — Lazy-init Gemini subclass (½ day)

**File**: `agent/superextra_agent/specialists.py:31-51`

Replace the eager `g.api_client = Client(...)` in `_make_gemini` with a `GeminiGlobalEndpoint(Gemini)` subclass that lazy-builds the Client on first `api_client` access. Pattern verified by R2.4. ~30 LOC.

**Reuse**: identical pattern from `agent/probe/gemini3.py:23-51` (the R3 working version).

**Verification**: `cloudpickle.dumps(_make_gemini("gemini-3.1-pro-preview"))` succeeds (no `_thread.lock` error). Existing `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` passes.

---

## Phase 3 — Secret Manager runtime fetch with env-first fallback (½ day)

**File**: `agent/superextra_agent/secrets.py` (NEW)

Add `get_secret(name: str) -> str` helper that **tries `os.environ[name]` first, falls back to Secret Manager only if absent**. This single helper handles all four runtime contexts without needing IAM grants on every SA:

| Context                            | env var present?                                           | Path taken     | IAM needed                                           |
| ---------------------------------- | ---------------------------------------------------------- | -------------- | ---------------------------------------------------- |
| Cloud Run worker (rollback window) | YES (set by `deploy.yml:244`)                              | `os.environ`   | none beyond what's there today                       |
| Agent Runtime (gear)               | NO (reserved by platform; no way to inject secrets as env) | Secret Manager | `secretmanager.secretAccessor` on `-re` SA (Phase 1) |
| Local dev                          | YES (from `agent/.env`)                                    | `os.environ`   | none                                                 |
| CI tests                           | YES (from GHA secrets)                                     | `os.environ`   | none                                                 |

```python
import os
from functools import lru_cache
from google.cloud import secretmanager

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
_client: secretmanager.SecretManagerServiceClient | None = None

def _get_client() -> secretmanager.SecretManagerServiceClient:
    global _client
    if _client is None:
        _client = secretmanager.SecretManagerServiceClient()
    return _client

@lru_cache(maxsize=32)
def get_secret(name: str) -> str:
    """Resolve a secret value. env var first (Cloud Run/local/CI),
    Secret Manager fallback (Agent Runtime). Cached after first read."""
    val = os.environ.get(name)
    if val:
        return val
    resp = _get_client().access_secret_version(
        name=f"projects/{PROJECT}/secrets/{name}/versions/latest"
    )
    return resp.payload.data.decode("utf-8")
```

**Replace ONLY real secret reads** — leave config envs (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `K_SERVICE`, `GEMINI_VERSION`, etc.) as direct `os.environ.get(...)`. Secrets to migrate (use **the existing env var names as Secret Manager IDs** — consistent across both code paths):

- `APIFY_TOKEN`
- `GOOGLE_PLACES_API_KEY`
- `SERPAPI_API_KEY`
- `JINA_API_KEY` (if used by `web_tools.py`)

Each call site changes from `os.environ["APIFY_TOKEN"]` to `get_secret("APIFY_TOKEN")`. The Phase 1 `gcloud secrets create APIFY_TOKEN` matches the env var name verbatim.

**Why env-first matters for the rollback window:** `deploy.yml:244` injects `APIFY_TOKEN`, `GOOGLE_PLACES_API_KEY`, `SERPAPI_API_KEY` as Cloud Run env vars. The worker SA `superextra-worker@superextra-site.iam.gserviceaccount.com` has only `aiplatform.user` and `datastore.user` (verified live 2026-04-27) — no Secret Manager grant. Without the env-first fallback, the rollback worker would 403 on every tool call. We could grant the worker SA `secretmanager.secretAccessor` instead, but env-first means **zero IAM changes to the rollback path** — a smaller, safer migration delta.

**Verification**: unit tests for `get_secret` — env-set returns env value (no Secret Manager call), env-unset hits Secret Manager once, second call cached. Integration: deploy probe with `env_vars={}` (forcing Secret Manager path), invoke a tool that reads a secret, verify success.

---

## Phase 4 — `FirestoreProgressPlugin` + `GearRunState` (2 days)

**New files:**

- `agent/superextra_agent/gear_run_state.py` — the `GearRunState` accumulator class
- `agent/superextra_agent/firestore_progress.py` — the `FirestoreProgressPlugin` thin wrapper around `GearRunState`
- (helpers `claim_invocation`, `fenced_session_and_turn_update`, and `OwnershipLost` live inline in `firestore_progress.py` — single consumer, no separate module needed)
- `agent/tests/test_gear_run_state.py` — `GearRunState` unit tests (mutation discipline, accumulation, finalize sequence including straggler cancellation, empty-reply terminal logic)
- `agent/tests/test_firestore_progress.py` — plugin lifecycle tests (callback wiring, per-invocation isolation)

### 4.1 `GearRunState` — the accumulator

```python
@dataclass
class GearRunState:
    # Identity
    sid: str
    invocation_id: str   # debug-only; not used as Firestore fence
    run_id: str
    turn_idx: int
    user_id: str

    # Mutable accumulators (mirror worker_main.py:1095-1230)
    final_reply: str | None = None
    final_sources: list[dict] = field(default_factory=list)
    specialist_sources: list[dict] = field(default_factory=list)
    specialist_sources_seen: set[str] = field(default_factory=set)
    mapping_state: dict[str, Any] = field(default_factory=lambda: {"place_names": {}})
    timeline_builder: TurnSummaryBuilder = ...     # constructed in __post_init__
    timeline_writer: TimelineWriter = ...          # constructed in __post_init__
    note_tasks: list[asyncio.Task] = field(default_factory=list)
    title_task: asyncio.Task | None = None
    seq: int = 0

    # Lifecycle
    heartbeat_task: asyncio.Task | None = None

    def observe_event(self, event) -> list[dict]:
        """Mutate accumulator from one ADK event. Returns a list of
        timeline-event dicts for the caller to feed to
        `timeline_writer.write_timeline(...)` one by one. TimelineWriter
        has its own internal lock so concurrent writes are safe.

        All mutation methods on self and on TurnSummaryBuilder are
        synchronous (no `await` inside them), so concurrent coroutines
        can't interleave with these mutations — control only yields at
        `await` points, and there are none here.

        Mirrors worker_main.py:1120-1230 logic."""
        mapped = map_event(event, self.mapping_state)
        self.timeline_builder.observe_event(event, self.mapping_state)
        timeline_event_dicts = mapped["timeline_events"]
        self._merge_grounding_sources(mapped.get("grounding_sources") or [])
        self._drain_tool_sources(event)
        self._maybe_emit_note_tasks(mapped["milestones"])
        if mapped.get("complete") is not None and self.final_reply is None:
            self._capture_final(mapped["complete"])
        self.seq += 1
        return timeline_event_dicts

    async def stop_heartbeat(self) -> None:
        """Cancel the heartbeat task. Called FIRST in after_run so a late
        tick can't clobber status=complete with a fresh lastHeartbeat.
        Mirrors worker_main.py:454 _cancel_heartbeat."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await asyncio.wait_for(self.heartbeat_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def finalize(self) -> tuple[dict, dict, str]:
        """Build (session_terminal_update, turn_terminal_update, status)
        from accumulated state. Sequence:
          1. Bounded-wait note tasks, then CANCEL stragglers and gather.
             Notes that finish in time get to write a live timeline event
             AND contribute to the summary. Stragglers are cancelled so
             they can't mutate timeline_builder after build_summary() runs.
             (asyncio.wait() with timeout does NOT cancel pending — only
             returns sets.)
          2. Close timeline_writer AFTER notes are settled. If we close
             first, a note task that resumes from its await would mutate
             timeline_builder but its write_timeline call would silently
             no-op — turnSummary would contain a note the live UI never
             saw. Close-after-drain keeps the live timeline and summary
             in sync.
          3. Await title task with bounded timeout (asyncio.wait_for
             cancels on timeout, so no straggler concern there).
          4. Sanity check on final_reply (empty → error per worker_main.py:1292)
          5. Build the two payloads from now-stable state
        """
        if self.note_tasks:
            _done, pending = await asyncio.wait(
                self.note_tasks, timeout=NOTE_TASK_DRAIN_TIMEOUT_S
            )
            for t in pending:
                t.cancel()
            # Gather ALL note tasks, not just pending. asyncio.wait() does
            # not retrieve results from `done` tasks — if a note task
            # raised an exception and finished within the timeout, that
            # exception sits unretrieved on the task and asyncio logs
            # "exception was never retrieved" at GC. Gathering everything
            # with return_exceptions=True consumes results uniformly,
            # silences the warning, and gives one place to inspect/log
            # straggler failures if we ever need to.
            await asyncio.gather(*self.note_tasks, return_exceptions=True)
        await self.timeline_writer.close()
        title = None
        if self.title_task is not None:
            try:
                title = await asyncio.wait_for(self.title_task, timeout=TITLE_TIMEOUT_S)
            except (asyncio.TimeoutError, Exception):
                title = None
        # All background mutators of timeline_builder are now done or cancelled.
        # Safe to read.
        if not self.final_reply or not self.final_reply.strip():
            return (
                {"status": "error", "error": "empty_or_malformed_reply",
                 "updatedAt": firestore.SERVER_TIMESTAMP},
                {"status": "error", "error": "empty_or_malformed_reply"},
                "error",
            )
        session_update = {"status": "complete", "updatedAt": firestore.SERVER_TIMESTAMP}
        if title is not None:
            session_update["title"] = title
        turn_update = {
            "status": "complete",
            "reply": self.final_reply,
            "sources": self.final_sources,
            "turnSummary": self.timeline_builder.build_summary(),
            "completedAt": firestore.SERVER_TIMESTAMP,
        }
        return session_update, turn_update, "complete"
```

`cleanup_background_tasks()` is no longer needed — `finalize()` cancels and gathers all stragglers before returning. After `finalize()`, no task on this `GearRunState` is still alive.

**Concurrency discipline (no lock needed):** all mutation methods on `GearRunState` and on `TurnSummaryBuilder` are synchronous — no `await` inside them. Once a mutation starts, no other coroutine can interleave because there are no suspension points. `TimelineWriter` owns its own internal lock for its Firestore writes (`worker_main.py:885`). Note tasks call only these synchronous mutation methods between their own `await`s. This is the same pattern today's worker uses, verified in production. **This is a discipline rule — any future mutator added to GearRunState/builder must stay sync and await-free, or this safety property breaks.**

**The dict map is per-instance.** Concurrent invocations get separate `GearRunState` objects in `dict[invocation_id, GearRunState]` — no cross-run contention to coordinate.

### 4.2 `fencedSessionAndTurnUpdate` — the critical-write helper

```python
class OwnershipLost(Exception): ...

async def fenced_session_and_turn_update(
    fs: firestore.Client,
    state: GearRunState,
    session_updates: dict,
    turn_updates: dict,
) -> None:
    """Two-doc transactional write that fences on currentRunId and
    status='running'. Raise OwnershipLost on either mismatch. Mirror of
    worker_main.py:234-287 with the post-migration fence keys."""
    session_ref = fs.collection("sessions").document(state.sid)
    turn_ref = session_ref.collection("turns").document(f"{state.turn_idx:04d}")

    @firestore.transactional
    def _logic(tx, session_ref, turn_ref):
        snap = session_ref.get(transaction=tx)
        data = snap.to_dict() or {}
        if data.get("currentRunId") != state.run_id:
            raise OwnershipLost(f"runId: expected={state.run_id} actual={data.get('currentRunId')}")
        # Status predicate prevents resurrecting a watchdog/cleanup-flipped
        # error state. Mirrors worker_main.py:341 no-op-on-terminal pattern.
        if data.get("status") != "running":
            raise OwnershipLost(f"status: expected=running actual={data.get('status')}")
        tx.update(session_ref, session_updates)
        tx.update(turn_ref, turn_updates)

    # Sync transactional logic wrapped via asyncio.to_thread — matches
    # existing worker pattern at worker_main.py:221, 229.
    await asyncio.to_thread(_logic, fs.transaction(), session_ref, turn_ref)
```

A single-doc variant (`fenced_session_update`) for heartbeat ticks where the turn doc isn't touched. Same fence-check shape.

### 4.2.1 Bounded retry on `claim_invocation` and terminal write only

The two writes where a transient Firestore failure causes a _bad outcome_ — not just delayed error rendering — are claim and terminal:

- **Terminal write failure without retry = data loss.** When `after_run_callback` does the fenced terminal write, the entire accumulated answer (`final_reply`, `final_sources`, `turn_summary`) lives in process memory inside the `GearRunState`. If the write raises a transient `DeadlineExceeded` and we don't retry, the exception propagates and `_states.pop()` discards `per`. The answer is unrecoverable. Watchdog catches the stuck `'running'` status 5 min later and renders `'pipeline_wedged'` error — but the actual successful answer is gone. Rare event (~Firestore 99.99% SLA), but worth the ~10 LOC.
- **Claim failure without retry = 30-min queue timeout.** Less catastrophic (no work was done yet), but the helper is shared so the cost is the same.

Heartbeat ticks do NOT retry — the 30-second tick interval IS the natural retry, matching today's worker pattern at `worker_main.py:438-449` (try/except, log, continue). Adding inner retry duplicates that loop.

Best-effort writes (timeline events, `lastEventAt` bumps) also don't retry — they swallow + log; next callback's write supersedes anyway.

```python
async def _retry_critical(coro_factory, *, max_attempts=3, base_delay=0.25):
    """Retry transient Firestore errors with exponential backoff. NEVER
    retries OwnershipLost — definitive ownership signal, not transient.
    Used at the two call sites where transient failure causes a bad
    user outcome: claim_invocation and terminal fenced write."""
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except OwnershipLost:
            raise
        except (GoogleAPICallError, RetryError, DeadlineExceeded):
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
```

After exhaustion: `claim` propagates → `before_run` returns `_halt_content()` → run aborts cleanly, queue timeout in 30 min. `terminal` propagates → `after_run` logs `event=terminal_write_exhausted` with full context → run sits in `'running'` until watchdog catches `lastEventAt` staleness at 5 min → `status='error'` with reason `pipeline_wedged`. The answer is still lost in this case (rare double-failure: transient blip + retry exhaustion), but the watchdog ensures the database converges to the correct error state.

### 4.2.2 Plugin granularity — one claim per root-runner invocation

Production agents use `SequentialAgent` / `ParallelAgent` sub-agent composition, NOT `AgentTool`. Confirmed at `agent/superextra_agent/agent.py:259-282`. ADK fires plugin run-level callbacks (`before_run_callback`, `after_run_callback`) once per root-runner invocation — not once per sub-agent. So `claim_invocation` runs ONCE per turn, the heartbeat task lives for the full 7–15 min pipeline, and `after_run_callback` writes the single terminal state covering all sub-agent output. If we ever introduce `AgentTool` wrappers (which DO trigger their own runner invocations), revisit this granularity assumption.

### 4.3 `FirestoreProgressPlugin` — thin lifecycle wrapper

```python
class FirestoreProgressPlugin(BasePlugin):
    def __init__(self, project: str):
        super().__init__(name="firestore_progress")
        self._project = project
        self._fs: firestore.Client | None = None
        self._states: dict[str, GearRunState] = {}

    @override
    async def before_run_callback(self, *, invocation_context):
        # 1. Read sid + (runId, turnIdx) from session.state (set by agentStream's :appendEvent)
        # 2. Construct GearRunState
        # 3. claim_invocation with retry on transient errors. Fences on
        #    currentRunId, status='queued', turn.status='pending'. Writes
        #    status='running', turn.status='running' atomically.
        #    On OwnershipLost (status already 'error'/'complete', or runId
        #    moved on): return _halt_content() to short-circuit cleanly.
        state = _build_state(invocation_context)
        try:
            await _retry_critical(lambda: claim_invocation(self._fs, state))
        except OwnershipLost as e:
            log.warning("claim_invocation lost sid=%s: %s", state.sid, e)
            return _halt_content(reason="invocation_not_claimable")
        except Exception as e:
            log.error("claim_invocation exhausted sid=%s: %s", state.sid, e)
            return _halt_content(reason="claim_exhausted")
        # 4. Register + spawn heartbeat
        self._states[invocation_context.invocation_id] = state
        state.heartbeat_task = asyncio.create_task(_heartbeat_loop(self._fs, state))
        return None  # proceed normally

    @override
    async def on_event_callback(self, *, invocation_context, event):
        per = self._states.get(invocation_context.invocation_id)
        if per is None:  # plugin saw an event for an unregistered run; ignore
            return None
        timeline_writes = per.observe_event(event)
        # Best-effort timeline writes (TimelineWriter has its own internal lock)
        for tw in timeline_writes:
            try:
                await per.timeline_writer.write_timeline(tw)
            except Exception:
                log.exception("timeline write failed; continuing")
        # Best-effort lastEventAt fenced update — fence includes
        # status='running' so a flipped session doesn't get re-bumped.
        await _best_effort_lastEventAt(self._fs, per)
        return None

    @override
    async def after_run_callback(self, *, invocation_context):
        per = self._states.pop(invocation_context.invocation_id, None)
        if per is None:
            return
        # Order matters and matches worker_main.py:
        # 1. stop_heartbeat — late ticks can't clobber the terminal write
        # 2. finalize — closes writer, cancels straggler notes, awaits
        #    title with timeout, builds payload from stable state
        # 3. fenced terminal write with retry on transient errors (data
        #    loss prevention — the answer is in process memory only)
        await per.stop_heartbeat()
        session_update, turn_update, status = await per.finalize()
        try:
            await _retry_critical(
                lambda: fenced_session_and_turn_update(
                    self._fs, per, session_update, turn_update
                )
            )
        except OwnershipLost:
            # Status no longer 'running' (watchdog/cleanup flipped),
            # OR currentRunId moved on. Don't resurrect.
            log.warning("ownership lost before terminal write sid=%s", per.sid)
        except Exception as e:
            # Retry exhausted on transient error. Run stays in 'running'
            # until watchdog catches lastEventAt staleness (5 min).
            log.error(
                "terminal_write_exhausted sid=%s runId=%s reply_len=%s: %s",
                per.sid, per.run_id, len(per.final_reply or ""), e,
            )
```

### 4.4 Reuse from existing code (no rewrite)

- `agent/superextra_agent/firestore_events.py` — `map_event`, `extract_sources_from_grounding`, `write_event_doc`. Called from `GearRunState.observe_event`.
- `worker_main.py` `TurnSummaryBuilder`, `TimelineWriter` — extract into `agent/superextra_agent/timeline.py` so they're importable by both worker (during rollback window) and plugin.
- `worker_main.py` heartbeat loop pattern (`:434-451`) — copy structure into `GearRunState._heartbeat_loop`.
- `worker_main.py` note-task helpers (`_emit_note_task`, deterministic note text) — extract into `agent/superextra_agent/notes.py` for shared use.

### 4.5 Plugin registration

`agent/superextra_agent/agent.py:284-288`:

```python
app = App(
    name="superextra_agent",
    root_agent=_router,
    plugins=[ChatLoggerPlugin(), FirestoreProgressPlugin(project=PROJECT)],
)
```

### 4.6 Verification

`agent/tests/test_gear_run_state.py`:

- `observe_event` mutations don't interleave (no `await` inside; verified by inspecting all mutation methods)
- Note tasks pending after `finalize()` bounded wait are cancelled and gathered, so `timeline_builder.build_summary()` reads stable state
- Empty `final_reply` → `finalize()` returns `('error', ...)` not `('complete', ...)`
- Note-task and title-task cancellation doesn't leak when `cancel()` is called

`agent/tests/test_firestore_progress.py`:

- Per-invocation isolation (two simulated invocations on the same session don't see each other's `final_reply`)
- `before_run` writes both session AND turn docs atomically; raises `OwnershipLost` on `currentRunId` mismatch or `status != 'queued'`; returns `_halt_content()` on already-terminal status
- `after_run` cancels heartbeat BEFORE terminal write (late tick doesn't clobber)
- Fenced terminal write rejects when `status != 'running'` (watchdog or cleanup flipped to error)
- `finalize()` builds error-payload when `final_reply` is empty/whitespace
- `_retry_critical` retries on `GoogleAPICallError`/`DeadlineExceeded` with bounded attempts; never retries `OwnershipLost`
- Heartbeat loop logs and continues on transient blip; exits only on `OwnershipLost`

---

## Phase 5 — `agentStream` rewrite + `gearHandoff` helper (1.5 days)

**Files:**

- `functions/index.js` — agentStream branches on `transport`; bump `timeoutSeconds: 30 → 90`
- `functions/gear-handoff.js` (NEW) — `gearHandoff()` helper encapsulating the full dispatch sequence including cleanup
- `functions/index.test.js` — new test cases for gearHandoff happy path and each failure shape

### 5.1 `gearHandoff` helper

```javascript
import { GoogleAuth } from 'google-auth-library';
import { FieldValue } from 'firebase-admin/firestore';

const VERTEX_BASE = 'https://us-central1-aiplatform.googleapis.com';
const RESOURCE = 'projects/{N}/locations/us-central1/reasoningEngines/{ID}';
const HANDOFF_DEADLINE_MS = 75_000; // leaves ~15s under CF's 90s timeout for cleanup

export async function gearHandoff({ sid, runId, turnIdx, userId, message, isFirstMessage }) {
	// ONE controller shared across createSession, appendEvent, and streamQuery.
	// When the deadline wins, abort() cancels every in-flight fetch — without
	// this, losing-side fetches keep running as background work and
	// Firebase's "no progress after termination" warning bites.
	const controller = new AbortController();
	const deadlineTimer = setTimeout(() => controller.abort(), HANDOFF_DEADLINE_MS);
	try {
		return await Promise.race([
			_doHandoff({ controller, sid, runId, turnIdx, userId, message, isFirstMessage }),
			_deadlineReject(HANDOFF_DEADLINE_MS)
		]);
	} finally {
		clearTimeout(deadlineTimer);
		// controller.abort() is idempotent; calling it ensures any straggler
		// fetch that survived the race also gets cancelled.
		controller.abort();
	}
}

async function _doHandoff({ controller, sid, runId, turnIdx, userId, message, isFirstMessage }) {
	const token = await _getToken();
	const adkSid = `se-${sid}`;
	const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

	// 1. Idempotent createSession on first turn — ALREADY_EXISTS treated as success
	if (isFirstMessage) {
		const r = await fetch(`${VERTEX_BASE}/v1beta1/${RESOURCE}/sessions?sessionId=${adkSid}`, {
			method: 'POST',
			signal: controller.signal,
			headers,
			body: JSON.stringify({ userId, sessionState: { runId, turnIdx, attempt: 1 } })
		});
		if (!r.ok) {
			const body = await r.text().catch(() => '');
			if (!body.includes('ALREADY_EXISTS')) throw new Error(`createSession_failed:${r.status}`);
		}
	}

	// 2. appendEvent — verified shape from R3.1 (author='system', RFC3339 timestamp, camelCase)
	const ar = await fetch(`${VERTEX_BASE}/v1beta1/${RESOURCE}/sessions/${adkSid}:appendEvent`, {
		method: 'POST',
		signal: controller.signal,
		headers,
		body: JSON.stringify({
			author: 'system',
			invocationId: `agentstream-${runId}`,
			timestamp: new Date().toISOString(),
			actions: { stateDelta: { runId, turnIdx, attempt: 1 } }
		})
	});
	if (!ar.ok) throw new Error(`appendEvent_failed:${ar.status}`);

	// 3. streamQuery + first-NDJSON-line read + clean abort
	const sqRes = await fetch(`${VERTEX_BASE}/v1/${RESOURCE}:streamQuery?alt=sse`, {
		method: 'POST',
		signal: controller.signal,
		headers,
		body: JSON.stringify({
			class_method: 'async_stream_query',
			input: { user_id: userId, session_id: adkSid, message }
		})
	});
	if (!sqRes.ok) throw new Error(`streamQuery_not_ok:${sqRes.status}`);

	const reader = sqRes.body.getReader();
	try {
		await _readFirstNdjsonLine(reader); // throws if stream ends without a line
	} finally {
		await reader.cancel().catch(() => {});
		// controller.abort() called by the outer finally; that cancels the
		// streamQuery fetch as the supported clean-disconnect verified by R3.2.
	}
	return { ok: true };
}

// Transactional cleanup helper — fences on currentRunId, updates session+turn atomically
export async function gearHandoffCleanup(db, sid, runId, turnIdx, errorReason) {
	const sessionRef = db.collection('sessions').doc(sid);
	const turnKey = String(turnIdx).padStart(4, '0');
	const turnRef = sessionRef.collection('turns').doc(turnKey);
	await db.runTransaction(async (tx) => {
		const snap = await tx.get(sessionRef);
		if (!snap.exists) return;
		const data = snap.data();
		if (data.currentRunId !== runId) return; // newer turn already moved on; don't clobber
		if (data.status === 'complete' || data.status === 'error') return; // race: terminal already written
		tx.update(sessionRef, {
			status: 'error',
			error: errorReason,
			updatedAt: FieldValue.serverTimestamp()
		});
		tx.update(turnRef, { status: 'error', error: errorReason });
	});
}
```

### 5.2 agentStream branching

The existing Firestore session txn (`functions/index.js:236-333`) is extended to **capture transport into an outer-scope variable inside the transaction**, matching the existing pattern for `creatorUid`, `isFirstMessage`, etc. that gets read after commit:

```javascript
// Outer-scope, captured by the txn callback
let transport = 'cloudrun';
// ... existing txn opens ...
await db.runTransaction(async (t) => {
  const snap = await t.get(sessionRef);
  const existing = snap.exists ? snap.data() : null;
  // ... existing checks ...

  // Capture transport on every txn attempt. Follow-ups preserve;
  // first turn picks initial value from allowlist.
  // CRITICAL: legacy sessions written before the transport field existed
  // have no field at all. After the default flip, the obvious
  // `existing?.transport ?? chooseInitialTransport(...)` would route those
  // legacy sessions to `'gear'` on follow-up — but their workers are
  // already running on Cloud Run and their session state is in the legacy
  // shape. Branch on `existing` (not on the field) so legacy sessions
  // default to `'cloudrun'`; only first-turn-of-a-new-session ever picks
  // the initial transport.
  transport = existing
    ? (existing.transport ?? 'cloudrun')
    : chooseInitialTransport(submitterUid);

  if (isFirstMessage) {
    t.set(sessionRef, {
      ...existingFirstTurnFields,
      transport,                  // ← only set on first turn
      ...perTurn
    });
  } else {
    t.update(sessionRef, {
      ...perTurn                  // ← do NOT include transport; preserves existing value
    });
  }
  // ... existing turn-doc creation ...
});

// After commit — branch on captured transport
if (transport === 'cloudrun') {
  // Existing path — enqueueRunTask + 502 cleanup unchanged
  ...
  return;
}

// Gear path — bumps timeoutSeconds to 90 at the function level
try {
  await gearHandoff({ db, sessionRef, sid: sessionId, runId, turnIdx: newTurnIdx, userId: creatorUid, message: queryText, isFirstMessage });
  res.status(202).json({ ok: true, sessionId, runId });
} catch (err) {
  console.error('gearHandoff failed:', err.message || err);
  try {
    await gearHandoffCleanup(db, sessionId, runId, newTurnIdx, `gear_handoff_failed:${err.message || 'unknown'}`);
  } catch (cleanupErr) {
    console.error('gearHandoff cleanup write failed:', cleanupErr.message || cleanupErr);
  }
  res.status(502).json({ ok: false, error: 'handoff_failed' });
}
```

### 5.3 Idempotent createSession

**No `adkSessionCreated` boolean.** Use the existing `isFirstMessage` flag (`functions/index.js:270`) to decide whether to call `:createSession`. On ALREADY_EXISTS (network retry double-dispatched): log + continue. The existing `previous_turn_in_flight` guard at `functions/index.js:261-263` blocks duplicate same-turn dispatches before we reach gearHandoff.

### 5.4 Firestore txn additions

The existing Firestore txn at `functions/index.js:236-333` is largely unchanged. The change is in **how `transport` is set** (NOT in `perTurn`, which would clobber on every follow-up):

- On `isFirstMessage`: `transport: chooseInitialTransport(submitterUid)` is in the `t.set(...)` payload alongside the other first-turn fields.
- On follow-ups: `transport` is NOT in the `t.update(...)` payload; the existing value is preserved.
- Outer-scope `let transport = 'cloudrun'` captures the value inside the txn callback on every attempt; agentStream branches on this variable after commit.

### 5.5 Reuse from existing code

- `functions/probe-stream-query.js` NDJSON parser → extract `_readFirstNdjsonLine(reader)` into `gear-handoff.js`
- Existing `functions/index.js:236-333` Firestore txn — extended with conditional `transport` write (first-turn `set` only, never on follow-up `update`) and outer-scope capture for post-commit branching

### 5.6 Verification

New `functions/index.test.js` cases:

- gearHandoff happy path — mocked fetch returns 200 + one NDJSON line, expects `reader.cancel()` and `controller.abort()` called before `res.send()`
- createSession ALREADY_EXISTS → continues to appendEvent (no error)
- appendEvent 4xx → cleanup transaction writes session+turn atomic error
- streamQuery 502 → same
- First NDJSON line never arrives within 75s → deadline rejects AND **shared `AbortController` aborts** (verifier asserts `controller.abort()` was called, mocked fetches see `signal.aborted === true`)
- gearHandoffCleanup with `currentRunId` mismatch → no-op (newer turn moved on)
- gearHandoffCleanup with already-terminal status → no-op (don't clobber)

---

## Phase 6 — Frontend optimistic submission with `optimisticPendingSid` guard (½ day)

**File**: `src/lib/chat-state.svelte.ts:521-537` (`startNewChat`), `:539-550` (`sendFollowUp`), and `:298-322` (the active-session `onSnapshot` listener)

**Three states to handle:**

- **Pre-Firestore failure** — POST rejects on auth/validation/network before agentStream's Firestore txn runs. NO session doc materializes. Local rollback required.
- **Post-Firestore failure** — agentStream's Firestore txn succeeded then `gearHandoff` failed. Session doc has `status='error'` from `gearHandoffCleanup`. Listener renders error; no frontend action needed.
- **Listener races POST** — listener attaches optimistically and gets a server-confirmed `exists=false` snapshot before agentStream's txn lands (the gap is ~0.5–1.5s). Without protection, `loadState` flips to `'missing'` and the user sees "Couldn't load this chat" briefly.

**Add `optimisticPendingSid` guard** to suppress the `missing` transition while a POST is in flight for the same sid:

```ts
let optimisticPendingSid: string | null = null;

// In the snapshot handler at chat-state.svelte.ts:307-312
if (!fromCache) {
	if (loadTimeoutHandle) {
		clearTimeout(loadTimeoutHandle);
		loadTimeoutHandle = null;
	}
	if (exists) {
		loadState = 'loaded';
		// Doc materialized — clear pending guard if it was for this sid.
		if (optimisticPendingSid === sid) optimisticPendingSid = null;
	} else if (optimisticPendingSid !== sid) {
		// Only flip to 'missing' once the optimistic window has closed.
		loadState = 'missing';
	}
	// else: keep loadState='loading' — POST still in flight, doc may yet materialize
}

async function startNewChat(query, place) {
	const sid = uuid();
	optimisticPendingSid = sid;
	selectSession(sid);
	placeContextState = place;

	try {
		await postAgentStream({
			sessionId: sid,
			message: query,
			placeContext: place,
			isFirstMessage: true
		});
		// Success: doc has materialized (or will any moment). Clear pending —
		// listener takes over for normal lifecycle.
		if (optimisticPendingSid === sid) optimisticPendingSid = null;
	} catch (err) {
		// Single getDoc check distinguishes pre-Firestore vs post-Firestore
		// failure. If the doc exists, post-Firestore: listener will render
		// status='error' from gearHandoffCleanup. If not, pre-Firestore:
		// local rollback. Use the same dynamic-import pattern this file
		// already uses (see chat-state.svelte.ts:200, :279, :447).
		//
		// Wrap getFirebase() AND the dynamic import inside the same try —
		// both can throw (offline import failure, Firebase init error,
		// auth missing). Without this, a Firebase-bootstrap failure would
		// propagate and skip the local rollback, leaving the session
		// selected with no doc ever materializing.
		let docExists = false;
		try {
			const { db } = await getFirebase();
			const firestoreMod = await import('firebase/firestore');
			const snap = await firestoreMod.getDoc(firestoreMod.doc(db, 'sessions', sid));
			docExists = snap.exists();
		} catch {} // any read/bootstrap error → treat as pre-Firestore failure
		if (optimisticPendingSid === sid) optimisticPendingSid = null;
		if (!docExists && activeSid === sid) {
			detachActiveListeners();
			clearActiveState();
			activeSid = null;
			loadState = 'idle';
		}
		throw err;
	}
	return sid;
}
```

`sendFollowUp` is simpler — already on the session, no `selectSession` call, no `optimisticPendingSid` change, no rollback. POST failure surfaces to caller.

**Verification:**

- Vitest cases in `chat-state.spec.ts`:
  - (a) Optimistic flow — successful POST: listener fires with `exists=false` first, `loadState` stays `'loading'`; then `exists=true`, flips to `'loaded'`
  - (b) Post-Firestore failure — POST rejects with 502 after `getDoc` confirms doc exists with `status='error'`: chat renders error state, no local rollback
  - (c) Pre-Firestore failure — POST rejects AND `getDoc` returns `!exists`: local rollback to idle
  - (d) Listener race — confirms `loadState` does NOT flip to `'missing'` while `optimisticPendingSid === activeSid`
- Manual UX smoke (Chrome DevTools MCP):
  1. New chat: panel renders within ~1s with user message + "researching…" placeholder; never shows "Couldn't load this chat"
  2. Forced 502 from agentStream after txn: chat shows error state, no orphan sid
  3. Forced auth failure (no Firebase token): chat resets to idle, error toast surfaces

---

## Phase 7 — A/B cutover infrastructure (½ day)

**File**: `functions/index.js` Firestore session txn (`:275-306`)

Add `transport: 'cloudrun' | 'gear'` field. Two-stage assignment, no percentage gating:

- **Stage A — developer allowlist.** Hardcoded set of UIDs (1–2 entries) gets `transport='gear'` on first turn; everyone else gets `'cloudrun'`. Soak for ~1 week. Drop a UID from the list to instantly route them back to legacy if anything regresses.
- **Stage B — default flip.** Once the allowlist soak is clean, change the default for new sessions to `'gear'`. Existing `'cloudrun'` sessions stay sticky and keep working until they drain naturally or the rollback window ends.

agentStream branches at the start of step 1 above on `transport`. **No frontend change** — the field is internal to the dispatch flow. **No percentage random-sampling logic** — for our scale, allowlist + default flip is simpler and gives instant per-user rollback without random skew.

---

## Phase 8 — Production deploy + allowlist soak + default flip (~2–3 calendar weeks)

1. Deploy production agent to staging Agent Runtime resource via `agent_engines.create(gcs_dir_name="agent_engine_staging", ...)`.
2. **Week 1 — allowlist:** developer UID(s) in the hardcoded allowlist get `transport='gear'` on new sessions; everyone else still on `'cloudrun'`. Smoke test deep queries end-to-end. Watch Firestore plugin docs, latency, error rates.
3. **Week 2 — default flip:** once the allowlist soak is clean (no unexpected errors, agent quality stable), flip the default for new sessions to `'gear'`. Existing `'cloudrun'` sessions stay sticky. Worker remains deployed and serves them.
4. **Week 3 — observe + drain:** legacy sessions naturally complete (most chats are revisited within 48h; long-tail rare). Cloud Run worker scales to zero pods once it has no traffic.
5. Hold/roll back at any point by removing UIDs from the allowlist or flipping the default back to `'cloudrun'`. Sticky transport per-session means no in-flight session is ever rerouted.

---

## Phase 9 — Cutover + cleanup (1 day, after 30-day rollback window)

1. Decommission Cloud Tasks queue + Cloud Run service.
2. Delete `agent/worker_main.py`, `agent/Dockerfile`, `enqueueRunTask` helper, `deploy-worker` GHA job.
3. Remove `adkSessionId`, `currentAttempt`, `currentWorkerId` fields in a Firestore migration script.
4. Archive `agent/probe/`, `functions/probe-stream-query.js`, R1/R2/R3 docs to `docs/archived/`.
5. Run `firebase functions:delete probeHandoffAbort probeHandoffLeaveOpen --region us-central1 --project=superextra-site --force`.

---

## Critical files

**Modified**:

- `agent/superextra_agent/specialists.py:31-51` — lazy Gemini subclass
- `agent/superextra_agent/agent.py:284-288` — register `FirestoreProgressPlugin`
- `agent/requirements.txt` — `google-cloud-secret-manager`
- `functions/index.js` — `agentStream` branches on `transport`, calls `gearHandoff`/`gearHandoffCleanup`, bumps `timeoutSeconds: 30 → 90`
- `src/lib/chat-state.svelte.ts:521-550` — optimistic `selectSession` + local rollback for pre-Firestore failures
- `firestore.indexes.json` — no change (existing 6 indexes sufficient)

**New**:

- `agent/superextra_agent/secrets.py` — lazy Secret Manager wrapper
- `agent/superextra_agent/gear_run_state.py` — `GearRunState` accumulator
- `agent/superextra_agent/firestore_progress.py` — `FirestoreProgressPlugin` lifecycle wrapper
- (claim/fence helpers + `OwnershipLost` live inline in `firestore_progress.py`)
- `agent/superextra_agent/timeline.py` — extracted `TurnSummaryBuilder` + `TimelineWriter` (shared by worker through rollback window + plugin)
- `agent/superextra_agent/notes.py` — extracted note-task helpers
- `functions/gear-handoff.js` — `gearHandoff()` + `gearHandoffCleanup()` helpers
- `agent/tests/test_secrets.py`, `test_gear_run_state.py`, `test_firestore_progress.py` — unit tests
- `functions/index.test.js` — new gear-handoff happy/failure cases

**Deleted (Phase 9 only)**:

- `agent/worker_main.py`, `agent/Dockerfile` (Cloud Run shape)
- `enqueueRunTask` helper from `functions/index.js`
- `deploy-worker` job from `.github/workflows/deploy.yml`

---

## Verification (end-to-end)

```bash
# Phase 2 — Gemini lazy subclass
cd agent && PYTHONPATH=. .venv/bin/python -c "
import cloudpickle
from superextra_agent.specialists import _make_gemini
g = _make_gemini('gemini-3.1-pro-preview')
cloudpickle.dumps(g)  # must not raise
print('OK')
"

# Phase 3-4 — agent + plugin
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v
# new tests in test_firestore_progress.py pass alongside existing suite

# Phase 5 — functions
cd functions && npm test
# new gear-handoff cases pass alongside existing intake/agentStream/agentDelete tests

# Phase 6 — frontend
npm run test          # vitest — chat-state.spec.ts cases for optimistic flow
npm run check         # svelte-check
npm run lint

# Phase 7 — staging deploy + smoke
cd agent && PYTHONPATH=. .venv/bin/python -c "
import vertexai; from vertexai import agent_engines
from superextra_agent.agent import app
vertexai.init(project='superextra-site', location='us-central1', staging_bucket='gs://superextra-site-agent-engine-staging')
remote = agent_engines.create(agent_engine=agent_engines.AdkApp(app=app), gcs_dir_name='agent_engine_staging', requirements=[...], extra_packages=[...])
print(remote.resource_name)
"

# Manual UX smoke (Chrome DevTools MCP) — confirm:
# 1. New chat: panel renders within ~1s (optimistic), progress streams from Firestore over next 7-15min
# 2. Follow-up: same shape, plugin reads new turn's runId/turnIdx from session.state
# 3. Forced agentStream 502: chat shows error state, no orphan sessions
```

---

## Out of scope

- **Memory Bank integration** — explicitly deferred per Adam's instruction (waiting on user accounts).
- **Logs auto-capture** — R2.6 found Agent Runtime logs don't surface in Cloud Logging API even with full IAM. Mitigation: keep Firestore-driven observability (which we already do). Adding `google.cloud.logging.Client.setup_logging()` to `set_up()` is optional; only do if production debugging surfaces a need post-cutover.
- **Custom container deployment** — managed packaging via `agent_engines.create(extra_packages=[...])` is sufficient. Custom container only if a specific dep collision blocks managed packaging.
- **Per-user rate limiting on the gear path** — preserve existing `uidRateLimitMap` from `functions/index.js:115-118`; no new limits needed.
- **Watchdog refactor** — existing thresholds and field names work unchanged. The plugin writes the same `lastHeartbeat`/`lastEventAt` fields the watchdog reads.

---

## Estimated total: 8–11 working days

Phases 1–7 are concurrent-friendly (Python + JS + Svelte each independent). Phase 8 is calendar time. Phase 9 lands after the 30-day rollback window.

**Revision delta vs v3.1:** Phase 1 grew from ½ → 1 day to cover real Secret Manager provisioning + IAM grant (live IAM check confirmed neither is done yet). Phase 4 picked up the `claim_invocation` helper distinct from `fenced_session_and_turn_update`, and the `stop_heartbeat` lifecycle. Phase 5 picked up the shared `AbortController` hoisted to `gearHandoff` scope. Phase 6 picked up the `optimisticPendingSid` guard. Net +1 day total beyond v3.1. The resulting code is still _less_ than today's `worker_main.py` event loop — state lives in one object with explicit ownership.

---

## Revision history

- **2026-04-26 v1** — initial implementation plan after v3 proposal approval
- **2026-04-27 v3.1** — incorporates 7 reviewer findings:
  - GearRunState accumulator — final_reply, sources, mapping_state, timeline_builder/writer, note_tasks, title_task, heartbeat all owned by one object
  - Empty-reply sanity check — terminal write goes to status='error' if final_reply blank
  - Transactional session+turn cleanup with internal deadline
  - Two fence keys: currentRunId for agentStream, currentInvocationId for plugin
  - Per-run asyncio.Lock inside GearRunState
  - Lazy Secret Manager fetch — runtime-only, not module-level
  - Drop adkSessionCreated boolean — ALREADY_EXISTS treated as success
  - Frontend local rollback for pre-Firestore failures
  - Three abstractions extracted: GearRunState, fenced_session_and_turn_update, gearHandoff
- **2026-04-27 v3.2** — incorporates 6 follow-up reviewer findings (all verified against live IAM, ADK source, and current code):
  - Phase 1 made real — secrets provisioning + `secretmanager.secretAccessor` grant on `-re` runtime SA (live IAM check showed both are missing)
  - `gearHandoff` shared `AbortController` — single controller passed to createSession/appendEvent/streamQuery; aborted on deadline so all in-flight fetches cancel together
  - Plugin `claim_invocation()` helper distinct from `fenced_session_and_turn_update` — different predicates at takeover (currentRunId match, status='queued', turn.status='pending') vs. in-flight (currentRunId+currentInvocationId+status='running'). Short-circuit via halt-content return from `before_run_callback` when session is already terminal
  - `status == 'running'` predicate added to in-flight fence — prevents resurrecting a watchdog/cleanup-flipped error state. Mirrors `worker_main.py:341` no-op-on-terminal pattern
  - Frontend `optimisticPendingSid` guard — suppresses `loadState='missing'` flip while POST is in flight (verified at `chat-state.svelte.ts:307-312` — server-confirmed `exists=false` immediately flips to 'missing')
  - GearRunState split: `stop_heartbeat()` BEFORE terminal write; `finalize_terminal_payload()` awaits notes/title; `cleanup_background_tasks()` AFTER terminal write — note tasks mutate via locked methods (verified at `worker_main.py:893-918`)
- **2026-04-27 v3.3** — 5 reviewer findings:
  - **Env-first `get_secret`** — Cloud Run worker stays alive through rollback window; `deploy.yml:244` injects `APIFY_TOKEN`/`GOOGLE_PLACES_API_KEY`/`SERPAPI_API_KEY` as env vars; worker SA has no `secretmanager.secretAccessor` (verified live). `get_secret(name)` tries `os.environ[name]` first, falls back to Secret Manager. Zero IAM changes to rollback path.
  - **Consistent secret IDs** — use existing env var names (`APIFY_TOKEN`, not `apify-token`) as Secret Manager IDs.
  - **`_halt_content` returns `types.Content`, not Event** — verified at `agent/.venv/.../runners.py:819`.
  - **`status == 'running'` predicate visible in fence pseudocode** — was in prose, now in both.
  - **Clear `currentInvocationId: null` on each queued turn** — agentStream's Firestore txn explicitly clears stale value.
- **2026-04-27 v3.4** — 3 reliability findings (all verified against `firestore_events.py:100`, `worker_main.py:135,179,221`, and existing async/sync patterns):
  - **Sync `firestore.Client` everywhere** — was using `firestore.AsyncClient` in plugin sketch, but `firestore_events.write_event_doc` (which we reuse) takes sync client and wraps with `asyncio.to_thread`. Worker matches. Plan now matches. Mixing sync/async client types breaks reused writers.
  - **`drain_pending_writes()` outside the per-run lock; `finalize_terminal_payload()` reads only under lock** — original sketch held `_lock` while awaiting note tasks, but note tasks need to acquire the same lock to apply mutations. Deadlock. Split into two methods: drain settles background work outside lock; finalize takes lock only to read accumulated state and build the payload.
  - **Bounded retry on transient Firestore errors for critical writes** — Cloud Tasks gave today's worker implicit retry on Firestore blips. Gear has no retry path; transient errors would leave runs stuck until watchdog notices (5–10 min). New `_retry_transient` helper wraps `claim_invocation`, terminal `fenced_session_and_turn_update`, and heartbeat ticks. **Never retries `OwnershipLost`** — that's definitive, not transient. Best-effort writes (timeline, lastEventAt) still swallow without retry.
- **2026-04-27 v3.5** — 2 P2 clarifications (no new behaviour, just explicit semantics) + 1 invariant pin:
  - **Heartbeat retry-exhaustion behaviour** — explicit: heartbeat loop catches post-retry exceptions, logs `event=heartbeat_exhausted`, and continues. Only `OwnershipLost` exits the heartbeat task. Rationale: transient Firestore blips shouldn't kill the liveness signal; watchdog's `lastEventAt` threshold gives a separate path.
  - **Terminal retry-exhaustion behaviour** — explicit: `after_run_callback` logs `event=terminal_write_exhausted` with full context; run stays in `'running'` until watchdog's `pipeline_wedged` sweep (5 min) flips it to `'error'`. UX cost: 5 min extra "researching…" then error. Acceptable vs. silent run loss.
  - **Plugin granularity invariant** — confirmed at `agent/superextra_agent/agent.py:259-282`: production uses `SequentialAgent`/`ParallelAgent`, NOT `AgentTool`. ADK fires `before_run_callback`/`after_run_callback` once per root-runner invocation, not per sub-agent. So `claim_invocation` runs ONCE per turn; heartbeat lives for the full 7–15 min pipeline; terminal write covers all sub-agent output. Documented as an invariant to revisit if `AgentTool` wrappers are introduced.
- **2026-04-27 v3.6** — lean pass. Six simplifications, each verified scenario-by-scenario:
  - **Drop `currentInvocationId` Firestore field.** The status transition `queued → running` is itself an exclusive lock; once running, `(currentRunId, status='running')` catches every scenario the dual-fence catches. No race traceable to needing two fence keys. ~30 LOC + 1 schema field saved.
  - **Drop heartbeat retry inside the tick.** Today's worker (`worker_main.py:438-449`) uses simple try/except continue; the 30s tick interval IS the natural retry. ~15 LOC saved.
  - **Keep claim/terminal retry only.** Tiny shared `_retry_critical` helper (~10 LOC) for the two writes where transient failure causes a bad outcome — terminal write loss = data loss (the answer lives in process memory only); claim failure = 30-min queue timeout. Heartbeat and best-effort writes don't retry.
  - **Drop the per-run `asyncio.Lock` in GearRunState.** Mutation methods are sync and await-free; `TimelineWriter` owns its own lock; today's worker has no lock and works. ~25 LOC saved.
  - **Collapse `drain_pending_writes()` + `finalize_terminal_payload()` into one `finalize()`.** Consequence of dropping the lock — no coordination needed. Sequence: close writer → drain notes (timeout-bounded) → await title (timeout-bounded with fallback) → empty-reply check → build payload. ~30 LOC saved.
  - **Replace `_waitForSessionDoc` polling with single `getDoc` check** after POST rejection. ~10 LOC saved.

  **Net v3.6 vs v3.5:** ~−155 LOC production, ~−155 LOC tests, two fewer abstraction layers (no lock, no drain/finalize split), one fewer Firestore field, one fewer concept to explain. Estimated effort drops from 9–12 days back to 8–11 days. The lean version handles every verified failure mode while removing every defensive layer that only protected against speculative scenarios.

- **2026-04-27 v3.7** — race fix + spec cleanup (all 7 verified):
  - **`finalize()` race fix.** `asyncio.wait(timeout=...)` does NOT cancel pending tasks (verified per Python docs); pending notes could mutate `timeline_builder` after `build_summary()` started reading. Now `finalize()` explicitly cancels stragglers and gathers them before reading state. Eliminates `cleanup_background_tasks()` — no longer any task left to clean up after `finalize()` returns.
  - **Stale `currentInvocationId` text removed** from forward-looking spec sections (context line 13, helper docstring line 299). Revision-history mentions kept since they're historical record.
  - **Frontend Firebase handle fixed** — `getFirebase()` returns `{ app, auth, db }` (verified at `src/lib/firebase.ts:79-83`); pseudocode now correctly destructures `db`.
  - **Test list updated** — drops "serialized by per-run lock" / `finalize_terminal_payload` references; adds "no `await` inside mutation methods" + "stragglers cancelled before summary read".
  - **`observe_event` typing/docstring corrected** — returns `list[dict]` of timeline event dicts, not coroutines. Concurrency framing changed to "no coroutine interleaving because these methods contain no await" (precise reason) instead of "atomic at bytecode boundaries" (different concept).
  - **Percentage rollout dropped.** `USE_AGENT_RUNTIME_PCT` random-sampling replaced with developer allowlist → default flip. Simpler for our scale, instant per-user rollback. Phase 8 timeline reframed to ~2–3 calendar weeks.
  - **`_firestore_writes.py` folded into `firestore_progress.py`.** Single consumer; separate module wasn't earning its place.
- **2026-04-27 v3.8** — pseudocode-correctness pass (5 fixes verified against actual file contents):
  - **Transport captured inside the txn**, mirroring the existing `creatorUid`/`isFirstMessage` pattern at `functions/index.js:236-333`. Outer-scope `let transport = 'cloudrun'`; inside the txn callback `transport = existing?.transport ?? chooseInitialTransport(submitterUid)`. First-turn `t.set(...)` includes `transport`; follow-up `t.update(...)` does NOT include `transport` (preserves existing value — never clobbers a sticky session).
  - **Note finalization order swapped:** drain notes first (with bounded wait + cancel stragglers), THEN close timeline_writer, THEN build summary. Previous order (close, then drain) created a window where a resuming note task could mutate `timeline_builder` but its `write_timeline` would silently no-op against the closed writer — `turnSummary` would contain a note the live UI never saw. New order keeps live timeline and summary in sync.
  - **`SERVER_TIMESTAMP` → `firestore.SERVER_TIMESTAMP`** in Python pseudocode. Bare `SERVER_TIMESTAMP` would be a `NameError`.
  - **Frontend pseudocode uses dynamic Firestore import** — `const firestoreMod = await import('firebase/firestore'); firestoreMod.getDoc(firestoreMod.doc(db, 'sessions', sid))` — matching the existing pattern at `chat-state.svelte.ts:200, 279, 447`.
  - **Stale wording cleaned up:** "lock semantics" in test-file description, "feature flag" reference in Phase 5.4, "two fields above" in Phase 5.5, `cleanup_background_tasks` in v3.1 revision-delta sentence (it never shipped — was introduced and removed within v3.5 → v3.7).
- **2026-04-27 v3.9** — final reviewer corrections before implementation (4 fixes, all verified against current code):
  - **(P1) Transport fallback for legacy sessions.** Changed `existing?.transport ?? chooseInitialTransport(...)` to `existing ? (existing.transport ?? 'cloudrun') : chooseInitialTransport(...)`. Sessions written before the `transport` field existed have no field at all — the original fallback would route them to `'gear'` after the default flip, but their state shape and dispatch path are still legacy. Branching on `existing` (not on the field) keeps legacy sessions on `'cloudrun'`; only first-turn-of-a-new-session ever picks the initial transport.
  - **(P2) Frontend rollback: getFirebase + dynamic import inside try/catch.** Both can throw (offline import failure, Firebase init error, auth missing); without wrapping them in the same `try`, a Firebase-bootstrap failure would propagate from the catch block and skip the local rollback — leaving the session selected with no doc ever materializing. Now any read/bootstrap error is treated as pre-Firestore failure.
  - **(P2) `finalize()` gathers all note tasks, not just pending.** `asyncio.wait()` does not retrieve results from `done` tasks — if a note task raised and finished within the timeout, the exception sat unretrieved and asyncio logged "exception was never retrieved" at GC. Now `asyncio.gather(*self.note_tasks, return_exceptions=True)` after cancelling stragglers consumes results uniformly.
  - **(P2) Coexistence rule for `currentAttempt`/`currentWorkerId`.** Made explicit: GEAR plugin doesn't read or write these, but the Cloud Run worker keeps using them through the rollback window for `transport='cloudrun'` sessions. Both paths coexist by transport, not by codepath. Phase 9's Firestore migration removes the leftover fields after the worker is decommissioned.
- **2026-04-27 v3.10** — onboarding section for executing agent. No design changes; the implementation surface is unchanged from v3.9. Added "Executing this plan — onboarding for a fresh agent" section bundling: (1) reading order across the proposal/overview/probe-results, (2) verified-working code in `agent/probe/` to study before writing equivalents, (3) external doc URLs (ADK, Vertex AI, Firebase, Svelte MCP) the agent should fetch live rather than recall from training, (4) environment facts the agent can't derive (project number, runtime SA email, staging bucket, missing IAM grants and secrets), (5) verified-not-working findings from probing (sessions.patch, timestamp formats, NDJSON-not-SSE, etc.) so they're not re-litigated, (6) the four-suite test discipline from CLAUDE.md, (7) phase-completion gates, (8) the lean-design covenant from v3.6 — don't add defensive layers without naming a verified failure mode.
