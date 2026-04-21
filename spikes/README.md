# Spikes — pipeline-decoupling validation

This directory holds the de-risk spike code that was run against the live
`superextra-site` project before committing to the `docs/pipeline-decoupling-plan.md`
implementation. **All findings are in `docs/pipeline-decoupling-spike-results.md`.**

## Why this lives in the repo

Three reasons:

1. **`adk_event_taxonomy_dump.json`** is a real Runner-event capture from a
   live pipeline run. It's the fixture Phase 2's event mapper should be tested
   against — don't regenerate unless the agent definition changes materially.
2. **Reproducibility**: if a future spike is ever needed (e.g. upgrading ADK,
   changing Agent Engine IDs), the patterns here are proven-to-work starting
   points.
3. **Audit trail**: the assumptions that drove plan decisions are visible here
   with live-run evidence, not just prose.

## Files

| File                           | Spike     | What it does                                                                                                                         |
| ------------------------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `adk_runner_spike.py`          | A         | Confirms `Runner(app=app, session_service=VertexAiSessionService(...))` works in-process, plugins fire, Agent Engine persists state. |
| `adk_event_taxonomy_spike.py`  | B         | Runs a real research query end-to-end, captures every ADK `Event` shape.                                                             |
| `adk_event_taxonomy_dump.json` | B output  | **Fixture**: 27 real events from a 2:43 full-pipeline run. Use as test input for Phase 2's mapper.                                   |
| `adk_runner_spike_events.json` | A output  | Trivial "hi" run event dump (1 router event + persisted state).                                                                      |
| `cloudtasks_oidc/`             | C / H / I | FastAPI echo service used to verify Cloud Tasks → Cloud Run OIDC delivery, dispatch-deadline behaviour, and revision-rollout drain.  |
| `firestore_query_spike.py`     | D         | Exercises the planned Firestore query + index + onSnapshot pattern. Verifies cross-user isolation.                                   |
| `bundle_size_spike.js`         | G         | Measures Firebase v10 modular SDK chunk size via a throwaway SvelteKit route.                                                        |
| `firestore_rules_test.js`      | F         | Mocha starter for `@firebase/rules-unit-testing` — move to repo root + run via Firebase emulator during Phase 1.                     |

## How to rerun any spike

All spikes need one-time local ADC setup on the workstation:

```bash
# VM's GCE metadata ADC lacks `cloud-platform` scope; fall back to user creds:
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<user>/adc.json
export GOOGLE_CLOUD_PROJECT=superextra-site
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
```

Then for Python spikes:

```bash
cd agent && PYTHONPATH=. .venv/bin/python ../spikes/<spike>.py
```

For Node spike:

```bash
node spikes/bundle_size_spike.js
```

## Cleanup discipline

Any GCP resources created should have `spike-` prefix in their name and be
deleted at the end of the spike run. The only persistent GCP leftovers we
intentionally kept:

- Firestore composite index on `events` collection group with fields
  `(userId, runId, attempt, seqInAttempt)` — matches the plan's
  `firestore.indexes.json`.
- `cloudtasks.googleapis.com` enablement on project `superextra-site` (enabled
  during validation; would be required anyway for Phase 8 deploy).

Everything else is cleaned up.

## When this directory becomes obsolete

After Phase 2 extracts `adk_event_taxonomy_dump.json` into the worker test
suite as a proper fixture (e.g. under `agent/tests/fixtures/`), this whole
directory can be deleted. Until then, **keep**.
