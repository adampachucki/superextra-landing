# Synthesizer Malformed Function Call Plan Review

Date: 2026-04-21

Review target: [docs/synthesizer-malformed-function-call-plan.md](/Users/adampachucki/src/superextra-landing-vm/docs/synthesizer-malformed-function-call-plan.md)

## Verdict

The updated plan is much better scoped.

The earlier architectural concerns are now gone:

- no retry-agent wiring
- no duplicate prompt file
- no `AUTHOR_TO_OUTPUT_KEY` misuse
- no empty-placeholder response that transiently writes `final_report=""`

What remains is narrower and concentrated in Phase 2 telemetry. The current revision is close to implementation-ready, but the measurement plan still has one blocking accuracy issue and one smaller logging-shape issue.

## Findings

### Finding 1

#### [P2] Structured fallback logs still do not support the Phase 2 query as written

File: `docs/synthesizer-malformed-function-call-plan.md:75-85`

Phase 2 expects to query `jsonPayload.reason` and separate fallback events by reason, but the worker's structured log formatter only serializes a fixed key set from [worker_main.py](/Users/adampachucki/src/superextra-landing-vm/agent/worker_main.py:63).

That key set includes `event`, but not `reason`. As written, `jsonPayload.event="synth_fallback"` would work, but `jsonPayload.reason="MALFORMED_FUNCTION_CALL"` would not be reliably available in Cloud Logging.

The fallback-side session filtering is also underspecified. The worker logs include `sid`, but the proposed synthesizer log call in [agent.py](/Users/adampachucki/src/superextra-landing-vm/agent/superextra_agent/agent.py:168) does not currently describe how `sid` would be attached from ADK callback context.

### Finding 2

#### [P2] The Phase 2 denominator does not isolate synth turns

File: `docs/synthesizer-malformed-function-call-plan.md:144-152`

This denominator counts every `run_complete`, but the numerator counts only synthesizer fallback events.

In this app, `run_complete` also includes follow-up turns and router clarifications, neither of which uses `code_execution`, so the resulting percentage will understate the real synthesizer fallback rate. The plan itself says the sample should be "organic turns that had `code_execution` enabled", but the proposed denominator query does not identify that population.

The fix is to add a synth-specific completion signal or derive the denominator from synth-authored terminal events instead of whole-run completions.

## Recommendations

### Recommendation 1

Keep the new staged plan shape.

The rewrite correctly simplified the solution:

- Phase 1 is now a narrow UX and telemetry change
- Phase 2 delays architectural decisions until there is real prod data
- Phase 3 prefers the simplest reliable option, which is removing `code_execution` from the primary synth path if the rate is materially high

That overall direction should stay.

### Recommendation 2

Tighten the structured logging contract before relying on Phase 2.

Either:

- widen the worker formatter's structured key allowlist to include `reason`
- and explicitly attach `sid=callback_context.session.id` in the synth fallback log call

or:

- relax the Phase 2 plan and describe a query that only depends on fields already known to reach Cloud Logging

Without that, the telemetry section promises a level of filtering and bucketing that the code path does not yet guarantee.

### Recommendation 3

Fix the denominator before using Phase 2 rates to drive product decisions.

Good options:

- emit a synth-specific completion event in logs
- derive the denominator from synth-authored terminal events rather than `run_complete`
- or otherwise mark turns where `code_execution` was actually enabled

Any of those would produce a defensible fallback rate. The current denominator would not.

## Bottom Line

This plan is now substantially more targeted and simpler than the original revision.

I would not reopen the old retry-agent design.

I would make the two telemetry fixes above, then execute the staged plan.

## Verified References

- Vertex `GenerateContentResponse` / `FinishReason`: [cloud.google.com/vertex-ai/docs/reference/rest/v1/GenerateContentResponse](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/GenerateContentResponse)
- Vertex code execution docs: [cloud.google.com/vertex-ai/generative-ai/docs/multimodal/code-execution](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/code-execution)
- Vertex code execution outcomes: [docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/Content](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/Content)
- ADK state docs: [adk.dev/sessions/state](https://adk.dev/sessions/state/)
- Local implementation references:
  - [agent.py](/Users/adampachucki/src/superextra-landing-vm/agent/superextra_agent/agent.py:168)
  - [worker_main.py](/Users/adampachucki/src/superextra-landing-vm/agent/worker_main.py:63)
  - [readonly_context.py](/Users/adampachucki/src/superextra-landing-vm/agent/.venv/lib/python3.12/site-packages/google/adk/agents/readonly_context.py:58)
