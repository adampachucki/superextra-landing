# Synthesizer MALFORMED_FUNCTION_CALL — staged response plan

Supersedes the earlier plan at this path that proposed a full retry-agent wiring. Rewritten 2026-04-21 after the review at `docs/synthesizer-malformed-function-call-plan-review.md`.

## Context

The synthesizer (`_make_synthesizer` in `agent/superextra_agent/agent.py:267`) calls Gemini's built-in `code_execution` tool to render matplotlib charts inline. When Vertex returns `error_code="MALFORMED_FUNCTION_CALL"` (or an empty response), `_embed_chart_images` (lines 168-264) substitutes a stitched fallback from specialist outputs and prepends this user-visible banner:

> _Note: final synthesis hit a model-level error (MALFORMED_FUNCTION_CALL) — typically during chart generation. The detailed specialist findings below are the raw research captured before synthesis failed._

Investigation brief: `docs/synthesizer-malformed-function-call-brief.md`. Prod sighting at 2026-04-21 12:39 UTC (Noma Copenhagen, sid=`07a071be-106d-4e6d-9de6-5f830721eb84`).

### Evidence — classified by confidence

**Confirmed by official docs:**

- Vertex `FinishReason.MALFORMED_FUNCTION_CALL` = "The model generated a function call that is syntactically invalid and can't be parsed." ([Vertex GenerateContentResponse](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/GenerateContentResponse)).
- Gemini 3.1 Pro supports `code_execution` as a built-in tool; code sandbox has a 30s timeout that surfaces as `OUTCOME_DEADLINE_EXCEEDED` (a separate, non-overlapping failure mode).

**Confirmed by local code inspection:**

- `_embed_chart_images` stitches the fallback on `error_code` or empty/no-text response (agent.py:181-212).
- The synth runs with `stream: False` (verified in the 2026-04-21 worker logs for the Noma run).
- `LlmAgent.__maybe_save_output_to_state` (vendored ADK `llm_agent.py:821-851`) writes `state_delta[output_key] = ''.join(part.text for part in parts if part.text ...)` when the final event has truthy `content.parts` — meaning any returned `LlmResponse` with a non-empty parts list triggers a write, even if the joined text ends up empty.
- `AUTHOR_TO_OUTPUT_KEY` (firestore_events.py:44) is iterated by `worker_main.py` for specialist-source harvesting — it is not a generic agent registry.

**Inferred from community reports (not verified for this repo):**

- [googleapis/python-genai#1120](https://github.com/googleapis/python-genai/issues/1120) reports `MALFORMED_FUNCTION_CALL` is disproportionately frequent on Vertex and is worsened by non-streaming mode. This is suggestive context, not a measurement of _our_ failure rate.
- No measured frequency exists for this system. Cloud Logging for the current worker has <24h of real traffic (n=1 MALFORMED hit across ~7 organic runs).

### Why staged

The earlier plan bundled a UX fix with a speculative retry architecture built on n=1 data. The review flagged (and I agree):

1. Claims that "retry without code_execution" is the correct fix rest on community evidence, not local measurement.
2. The retry design had a subtle side effect — an empty `LlmResponse` returned from `_embed_chart_images` would still write `state_delta["final_report"] = ""` via ADK's output_key path.
3. Adding `synthesizer_text_only` to `AUTHOR_TO_OUTPUT_KEY` would have widened specialist-source harvesting behavior in `worker_main.py` in an unrelated way.
4. Duplicating `synthesizer.md` into a second prompt file creates drift.

**The right sequence is: land the neutral UX fix, instrument properly, then decide from data.**

## Phase 1 — land now

Low-risk, self-contained. Does not commit the codebase to any retry or decoupling architecture.

### File: `agent/superextra_agent/agent.py`

**Edit `_build_fallback_report` (lines 139-165).** Replace the error-code-leaking banner:

```python
# OLD
f"_Note: final synthesis hit a model-level error ({error_code}) — typically "
"during chart generation. The detailed specialist findings below are the "
"raw research captured before synthesis failed._\n\n",
```

With a neutral, product-aligned message:

```python
"_Charts couldn't be generated for this report. Full research findings below._\n\n",
```

Keep the `error_code` parameter on the function — the caller still logs it via the structured `synth_outcome` event (see next section). It just stops appearing in the user-facing reply.

**No change to pipeline shape, no retry agent, no new instruction file.**

### File: `agent/worker_main.py` — widen structured-log allowlist

The JSON formatter at `worker_main.py:66-84` only serializes keys listed in `_STRUCTURED_LOG_KEYS` (line 63). Currently: `("sid", "runId", "attempt", "cloudTaskName", "workerId", "event")`. A `reason` attached via `extra=` would be dropped silently. Add it:

```python
_STRUCTURED_LOG_KEYS = ("sid", "runId", "attempt", "cloudTaskName", "workerId", "event", "reason")
```

One-word change. No other formatter logic touched. This is the prerequisite for the Phase 2 query to filter by `jsonPayload.reason`.

### File: `agent/superextra_agent/agent.py` — emit a single outcome event on every synth exit

The current `_embed_chart_images` logs warnings only on the three _failure_ branches (lines 183, 199, 208). That gives a numerator but no clean denominator — `run_complete` is the only event that fires at the worker level, and it also covers follow-up + router turns that never ran `code_execution`.

Fix: emit `event="synth_outcome"` with a `reason` facet on **every** exit path — success and failure. Both numerator and denominator then come from the same filtered population (turns where `code_execution` was actually enabled, i.e. synth ran).

```python
# Success path — right before returning the modified llm_response:
logger.info(
    "synth outcome ok",
    extra={"event": "synth_outcome", "reason": "ok"},
)

# Failure branches — replace the three existing warning calls with:
logger.warning(
    "synth outcome %s",
    reason,
    extra={"event": "synth_outcome", "reason": reason},
)
```

where `reason` is `error_code` (e.g. `"MALFORMED_FUNCTION_CALL"`), `"empty_response"`, or `"no_text_parts"` on the failure branches, and `"ok"` on the success branch.

**Not attempting per-log `sid` correlation from the callback.** ADK's `CallbackContext` doesn't expose the worker's Firestore `sid` directly — the ADK `session.id` it does expose is the Agent Engine session id, a separate identifier. For per-request drill-down, Cloud Logging's trace view already groups logs sharing `X-Cloud-Trace-Context` (auto-injected by Cloud Run), which is good enough for Phase 2 investigation. Attempting to plumb worker `sid` into ADK callbacks would need a `contextvars.ContextVar` set in the worker's `/run` handler and read in the callback — out of scope for a telemetry change.

### File: `agent/tests/test_embed_chart_images.py`

Existing assertions check the old disclaimer wording at:

- Line 31: `assert "empty_response" in text`
- Line 112: `assert "empty_response" in text`
- Line 124: `assert "no_text_parts" in text`
- Line 145: `assert "MALFORMED_FUNCTION_CALL" in text`
- Line 160: `assert "MALFORMED_FUNCTION_CALL" in text`

These were testing that the internal reason leaked into the user-facing text. After Phase 1 that's no longer true by design — update each to assert on the new neutral wording:

```python
assert "Charts couldn't be generated" in text
```

The structural tests at `_build_fallback_report` (line 164-173) continue to pass — only the leading banner changes.

### File: `agent/tests/test_embed_chart_images.py` — new tests

Two tests covering both outcome paths, so the Phase 2 Cloud Logging query is robust to future refactors:

```python
def test_success_emits_ok_outcome(caplog):
    resp = _make_llm_response([types.Part(text="real narrative")])
    with caplog.at_level(logging.INFO, logger="superextra_agent.agent"):
        _embed_chart_images(callback_context=None, llm_response=resp)
    assert any(
        getattr(r, "event", None) == "synth_outcome"
        and getattr(r, "reason", None) == "ok"
        for r in caplog.records
    )


def test_malformed_emits_failure_outcome(caplog):
    resp = _make_llm_response(None)
    resp.error_code = "MALFORMED_FUNCTION_CALL"
    ctx = SimpleNamespace(state={"market_result": "x"})
    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        _embed_chart_images(callback_context=ctx, llm_response=resp)
    assert any(
        getattr(r, "event", None) == "synth_outcome"
        and getattr(r, "reason", None) == "MALFORMED_FUNCTION_CALL"
        for r in caplog.records
    )
```

### File: `agent/tests/test_worker_main.py` (or wherever worker log tests live)

If there's existing coverage for `_JsonFormatter`, add one line to an existing test confirming `reason` is surfaced:

```python
record = make_log_record(extra={"event": "synth_outcome", "reason": "MALFORMED_FUNCTION_CALL"})
payload = json.loads(_JsonFormatter().format(record))
assert payload["reason"] == "MALFORMED_FUNCTION_CALL"
```

Skip if no such test file exists — the structured-log shape is already exercised indirectly via the agent-side tests above.

### What Phase 1 does NOT change

- `_inject_code_execution` — still runs, charts still generated on the happy path.
- `_embed_chart_images` control flow — same three branches, same stitched fallback on double-failure.
- Pipeline structure in `research_pipeline` — unchanged.
- `firestore_events.py` — unchanged. `worker_main.py` only gets the one-word `_STRUCTURED_LOG_KEYS` addition; request-handler logic untouched.
- The `_build_degraded_reply` safety net (worker_main.py:497) — unchanged.

## Phase 2 — gather data (no code, 2–4 weeks)

Let real prod traffic accumulate and compute actual rates from the structured event field introduced in Phase 1.

**Denominator** — every turn where synth ran (i.e. `code_execution` was actually enabled, because `_embed_chart_images` only runs as synth's after_model_callback):

```
resource.type="cloud_run_revision"
resource.labels.service_name="superextra-worker"
jsonPayload.event="synth_outcome"
```

**Numerator** — synth turns that hit any fallback:

```
resource.type="cloud_run_revision"
resource.labels.service_name="superextra-worker"
jsonPayload.event="synth_outcome"
jsonPayload.reason!="ok"
```

**Per-reason breakdown** — bucket the numerator by `jsonPayload.reason` to separate `MALFORMED_FUNCTION_CALL` from `empty_response` / `no_text_parts`. They may have different root causes and the Phase 3 decision should weight MALFORMED specifically, since that's the one structurally tied to `code_execution`.

Filter out `rl-*` and `verify-*` session IDs on both sides using `jsonPayload.sid` — the worker attaches `sid` as a structured key so it's available on all worker-authored logs. Note: `_embed_chart_images` runs _inside_ the ADK callback stack, not on the worker code path, so `sid` will not be on the `synth_outcome` records themselves. Per-request drill-down to a specific sid uses Cloud Logging's trace view (shared `X-Cloud-Trace-Context` groups the `synth_outcome` log together with the enclosing worker's `run_start` / `run_complete` that do carry `sid`).

Exit criterion: n ≥ 30 organic `synth_outcome` events before reading the rate as signal.

## Phase 3 — decide from data

Branch on the measured `synth_outcome` failure rate (numerator / denominator from the Phase 2 queries).

### Case A — rate < 3% of organic runs

Stop. Phase 1's neutral banner handles the rare case well enough. No architectural change. Close the brief.

### Case B — rate ≥ 3% (material)

**Take the reliability-over-charts path.** Drop `code_execution` from the primary synth so the narrative is always on the stable path. Concretely:

1. **Remove `before_model_callback=_inject_code_execution`** from `_make_synthesizer` (agent.py:276). The `_inject_code_execution` function can stay defined for future reuse or be deleted.
2. **Make the chart block in `synthesizer.md` (lines 44-50) conditional or remove it.** Parameterize via a `{chart_instructions}` placeholder in the template, resolved in `_synthesizer_instruction` based on a module-level flag (e.g. `ENABLE_SYNTH_CHARTS = False`). Gives us one prompt, one toggle.
3. **Simplify `_embed_chart_images`** — when charts are disabled there will never be `inline_data` image parts, and MALFORMED_FUNCTION_CALL specifically can't happen (the tool isn't injected). The empty-response / no-text-parts branches still matter and keep their stitched fallback.
4. **Update tests** — drop or skip tests that cover chart-specific paths when charts are disabled; keep the empty-response coverage.

What we lose: inline charts in synth output. Per current product signal (n=1 MALFORMED, brand values minimalism and reliability over matplotlib aesthetics) this is acceptable until we revisit charts as a first-class product feature.

What we gain: the narrative is never lost to a tool parse failure. Faster synth calls (no 30s code sandbox window). No retry complexity.

### Case C — rate ≥ 3% AND product signal says charts are critical

Only in this case build proper chart support — and even then, **not** the retry-on-MALFORMED design from the previous plan. Instead: decouple charts structurally via a chart-decorator agent that receives the narrative + the specialists' numerical data and emits chart specs (bar/pie/line + labeled data as JSON) that the frontend renders server-side. Separate plan, separate review, separate brief.

If a retry design is ever revisited, the reviewer's simplifications apply:

- Single parameterized synthesizer prompt with a conditional `{chart_instructions}` block, not a duplicate file.
- A custom ADK branching agent rather than SequentialAgent + callback short-circuit tricks.
- Never return an empty-text `LlmResponse` from an agent that still owns `output_key="final_report"` — either use a non-empty placeholder that doesn't fake a "complete" or restructure so the primary agent doesn't own the output_key on the failure path.
- Extend only the mapper author allowlist at `firestore_events.py:154`. Do not touch `AUTHOR_TO_OUTPUT_KEY`.

## Critical files modified (Phase 1 only)

- `agent/worker_main.py` — append `"reason"` to `_STRUCTURED_LOG_KEYS` (line 63). One-word edit.
- `agent/superextra_agent/agent.py` — banner text in `_build_fallback_report`; add an INFO `synth_outcome` log on the success exit of `_embed_chart_images`; replace the three failure warnings with structured `synth_outcome` + `reason` log calls.
- `agent/tests/test_embed_chart_images.py` — update five disclaimer assertions; add two outcome-event tests (success + failure).

Nothing else changes in Phase 1. No new files. No pipeline wiring. No `firestore_events.py` edits. No changes to the worker request handler.

## Verification — Phase 1

Tests:

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/test_embed_chart_images.py -v
```

Full agent suite and the four-suite gate from CLAUDE.md must stay green:

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v --ignore=tests/test_router_evals.py
npm run test
cd functions && npm test
npm run test:rules
```

Post-deploy live checks:

1. Run any real prompt on the happy path. Confirm: no banner in the reply, chart generation works as before.
2. If a MALFORMED fallback fires, confirm in the rendered reply that the banner says "Charts couldn't be generated for this report. Full research findings below." — not the old `MALFORMED_FUNCTION_CALL` phrasing.
3. Cloud Logging returns results with the new shape. Within a few minutes of post-deploy happy-path traffic, this query should return every synth turn:

```
resource.type="cloud_run_revision"
resource.labels.service_name="superextra-worker"
jsonPayload.event="synth_outcome"
```

Each hit carries `jsonPayload.reason` as a structured field — `"ok"` on success or the `error_code` / empty-type on failure — not regex'd out of a message string. Verify the field is actually surfaced, not silently dropped by the formatter (that's what the worker `_STRUCTURED_LOG_KEYS` widen fixes).

## Open questions to resolve before Phase 3

- **What does the product want from charts?** The Phase 3 branch between B and C depends on this. Worth deciding before telemetry lands so the Phase 3 decision is fast.
- **Do we ever surface charts from sources other than synth (e.g. specialist outputs with numerical tables)?** If yes, Case C's chart-decorator agent is a bigger win than it looks because it could render data from anywhere in the pipeline, not just synth.
