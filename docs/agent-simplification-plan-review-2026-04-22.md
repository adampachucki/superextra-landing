# Review of Revised `docs/agent-simplification-plan-2026-04-22.md`

## Findings

### [P1] Phase 1 currently overstates what reaches the final user-visible `sources[]`

The revised plan says deleting `_append_sources` changes nothing the UI consumes because the grounding path already produces `sources[]` for the UI. That is not true in the current flow.

What the code does today:

- `_map_specialist()` extracts specialist sources from grounding metadata and puts them on specialist **activity events** as `data.sources` (`agent/superextra_agent/firestore_events.py:260-283`).
- The worker does **not** accumulate those specialist activity-event sources into the terminal session document. In the run loop it only promotes `data.sources` from the first terminal `complete` event, which is the synthesizer/follow-up reply (`agent/worker_main.py:696-716`).
- The extra specialist-source contribution that reaches the final session doc today comes from `_extract_sources_from_state_delta()`, which parses markdown links out of accumulated specialist output text (`agent/worker_main.py:460-475`).
- The frontend displays sources from the terminal session doc reply path, not from specialist activity events (`src/lib/firestore-stream.ts:172-180`, `src/lib/chat-state.svelte.ts:313-329`).

That means deleting `_append_sources` without one more worker change will likely shrink or empty the final top-level `sources[]` list, even if specialist activity events still carry grounding sources.

The fix does not need new ADK state keys. The simplest correction is the one discussed earlier:

- keep `_map_specialist()` as-is
- accumulate `data.sources` from emitted specialist completion activity events in the worker
- dedupe them
- merge them into the terminal session `sources[]`

That preserves the final user-visible source list without keeping source markdown inside model text and without introducing new `*_sources` state plumbing.

### [P1] Phase 5 relies on a failure signal the runtime does not actually use

The revised plan says the minimal gap gate can run when any required specialist output equals the sentinel `"Agent did not produce output."`, and describes that sentinel as already written on failure. In the current code, that is not what happens.

What the code does today:

- Specialists with no brief skip before the model call and return the literal `"NOT_RELEVANT"` (`agent/superextra_agent/specialists.py:190-196`).
- Model failures return a fallback text like `"Research unavailable: <ExceptionType>"` (`agent/superextra_agent/specialists.py:200-207`).
- Tool failures return a dict with an `"error"` field, not the sentinel (`agent/superextra_agent/specialists.py:210-212`).
- `"Agent did not produce output."` is currently a **template default** used when reading missing state in the synthesizer/gap instruction builders and the existing gap skip callback (`agent/superextra_agent/agent.py:77-80`, `agent/superextra_agent/specialists.py:302-317`).

So the plan's current wording is factually wrong, and the proposed gate is weaker than it looks. If a specialist fails with the existing `"Research unavailable: ..."` fallback, the state key is still present and the proposed gate would likely skip `gap_researcher` when it should run.

The simplest corrected version is:

- treat a missing required output as a reason to run gap research
- also treat `"Research unavailable: ..."` as a reason to run gap research
- continue to ignore `"NOT_RELEVANT"` for unassigned specialists

That still avoids the heavier `{name}_error` state protocol, but it matches the runtime behavior that exists today.

## Open Questions

### Inline chart-spec blocks are a reasonable simplification tradeoff, but they do create a mixed `reply` contract

The revised plan's Phase 2 is much better than the earlier `chart_agent` proposal. It removes `code_execution`, keeps one synth, keeps one `reply` field, and avoids a new pipeline stage.

The remaining tradeoff is that `final_report` would now contain both:

- human-readable narrative
- machine-readable chart JSON fenced blocks

That will flow into:

- follow-up prompts, because `follow_up.md` injects `{final_report}` verbatim (`agent/superextra_agent/instructions/follow_up.md:5-21`)
- TTS, because the UI still sends raw `msg.text` to the TTS layer (`src/lib/components/restaurants/ChatThread.svelte:88-89`)

This is probably still the lowest-complexity way to preserve charts under the stated product constraint, but it should be treated as a conscious tradeoff. If it degrades follow-ups or read-aloud noticeably, the next fix should be a small strip/filter step for chart fences at those consumers, not a new chart pipeline.

## What Improved

The revised plan fixed the biggest problems in the earlier draft:

- no separate `chart_agent`
- no `charts[]` payload or extra pipeline stage
- no per-agent `*_sources` state keys
- no `{name}_error` state protocol
- no prompt-helper / shared-partial / `output_schema` expansion
- no speculative token or LOC promises

That is a real improvement. The revised plan is now mostly aligned with the stated simplification goal.

## Verdict

The revised plan is directionally strong and much closer to approval. I would not reject it wholesale anymore.

But two changes are still needed before calling it sound:

1. Phase 1 must explicitly preserve final terminal `sources[]` by accumulating specialist completion-event sources in the worker, not by assuming specialist grounding already reaches the session doc.
2. Phase 5 must use the runtime's real failure shapes, not the `"Agent did not produce output."` template default as if it were a written failure marker.

With those two fixes, the plan becomes a solid deletion-first simplification plan:

- remove `_append_sources`
- remove synth `code_execution`
- collapse fallback layers after live confirmation
- roll out `include_contents='none'` in stages
- keep prompt cleanup direct and local

That would remove real causes instead of adding another abstraction layer.
