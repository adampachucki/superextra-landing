# Activity Timeline Redesign — Review

Reviewed against the codebase, `spikes/adk_event_taxonomy_dump.json`, ADK and Firestore docs, and ADK community issues. Goal of the review: check whether the plan can land the Codex-shaped UX, whether it actually simplifies, and whether the moving parts hold together end-to-end. Edge-case defensiveness is out of scope by request.

## TL;DR

**Ship it, with four tightening edits before implementation starts.** The plan's core thesis — replace the current progress-widget contract with a small append-only timeline driven by milestone notes + grouped detail rows — is right. The durable transport below it is already correct, and the current UI is demonstrably the wrong abstraction. The four edits below are not edge-case defense; they close real gaps in the plan that will bite during implementation.

## What the plan gets right (verified)

- **Transport substrate is sound and should not change.** `src/lib/firestore-stream.ts`, `functions/agentCheck.js`, watchdog, fenced session write — all fine. The plan correctly keeps them.
- **The current UI really is overcomplicated.** `StreamingProgress.svelte` is 428 lines of typewriter groups, dot phases, section-done heuristics, staggered reveals, and `analyze-synthesizer` special-casing. `ChatThread.svelte` has three distinct render paths for streaming state (the bare `streamingProgress` loop, the `StreamingProgress` component in two places). `chat-state.svelte.ts` carries two parallel progress concepts and a bespoke `all-complete` collapse rule (`chat-state.svelte.ts:280-286`). 68 call-sites reference the old-contract symbols across `src/` and `functions/`. The plan's deletion list is accurately scoped.
- **`_first_function_call` really is lossy.** Confirmed empirically from `spikes/adk_event_taxonomy_dump.json`: event 15 (`review_analyst`) carries **3 parallel `function_call` parts** in a single ADK event (three `find_tripadvisor_restaurant` calls); event 16 carries the 3 matching `function_response` parts. Current mapper emits one UI row where the backend actually did three calls. Fixing this is a genuine correctness win, not cosmetic.
- **No partial-text streaming.** Spike B observed 0 partial-text events over 21 events in a full pipeline run; docs confirm this is default-RunConfig behavior. The plan's decision to keep "fake typing" as an end-phase effect only is correct.
- **Milestone boundaries exist and are observable.** `places_context` state_delta (event 4 in the dump), `research_plan` state_delta (event 7), `set_specialist_briefs` function_call (event 5), and specialist `*_result` state_deltas are all real, stable signals the worker already sees. The plan's four milestones map cleanly onto them — with one exception, below.
- **Reliability assumptions match the code.** Append-only Firestore event subcollection, collection-group query filtered by `(userId, runId)`, session doc as sole terminal source, runId-scoped dedup in `chat-state.svelte.ts` — the plan's rebuild-on-reload claim falls out of the transport behavior already verified in `docs/pipeline-decoupling-spike-results.md`.
- **ADK supports multiple function_call parts idiomatically.** `event.get_function_calls()` / `event.get_function_responses()` is the documented accessor ([ADK Events](https://google.github.io/adk-docs/events/)). Parallel tool-call events are the ADK default since v1.10.0 ([ADK Tool Performance](https://google.github.io/adk-docs/tools-custom/performance/)). The new mapper contract is aligned with the framework, not fighting it.

## What needs to tighten before implementation

### 1. Specify the "Drafting" trigger mechanism (the plan leaves this as a known-unknown)

**Problem.** Plan §Milestone Model says "Drafting — Trigger: synthesizer start." In the observed event stream, the synthesizer emits a single `is_final=True` event (its own output). There is no pre-final "synth started" event from the runner. Without a chosen mechanism, the drafting row would either (a) land at the same instant the answer lands, making it useless, or (b) need a flaky client-side "no events for N seconds" heuristic.

**Pick one, in order of preference:**

1. **`before_agent_callback` on the synthesizer agent** (cleanest). Set `callback_context.state["_drafting_started"] = True`; the runner emits a state_delta event ahead of the synthesizer's own work. Mapper detects `_has_state_delta(event, "_drafting_started")` and emits the drafting timeline event. This is the documented ADK mechanism for lifecycle-based synthetic events.
2. **Worker-side inference.** Watch `set_specialist_briefs`' brief keys, count specialist `*_result` state_deltas as they arrive, emit a synthetic drafting event server-side when the set is complete. Works, but couples the worker to orchestrator internals.
3. **Client heuristic.** Do not use. Noisy, timing-dependent, will misfire on slow specialists.

Locking option 1 before Phase 1 is cheap and removes an underspecified hinge of the whole timeline.

### 2. Note #3 ("Research underway") — the upgrade path is underspecified

Plan §Milestone Model: "deterministic placeholder immediately when source work starts … upgrade to one LLM-written note once the first meaningful specialist output exists."

Two problems the plan should answer explicitly:

- **What does "first meaningful specialist output" mean when specialists run in parallel?** Per `agent.py:249-253`, the `specialist_pool` is a `ParallelAgent`; several specialist `is_final` events arrive in quick succession. Pick: first non-`NOT_RELEVANT` specialist result (by event order) — the state_delta key matters, not the author. The current `_has_state_delta` already filters `NOT_RELEVANT`; reuse it.
- **Does the upgraded row replace the placeholder or append?** Plan §Experience Rules says "Visible rows do not switch between pending, running, and complete … append-only." An upgrade-in-place contradicts that. Either explicitly allow one in-place replacement for this single row (and document why it's an exception) or make the upgrade append a new note row and drop the placeholder at persist-time. Either is fine; silence is not.

### 3. Count definitions have one ambiguity that matters

Plan §Counting Rules:

- `queries` → "from `google_search` and `search_restaurants`". But `search_restaurants` is a Places text-search (see `_activity_id_for_tool` in `firestore_events.py:386`), not a web search. Users will read "Reviewed 5 venues, opened 7 sources, 3 searches" as 3 web searches. Either split web-queries from place-searches in the UI summary line, or drop `search_restaurants` from the `queries` count and only include `google_search`. The latter is simpler and matches user intuition.
- `sources` → "unique normalized URLs from `fetch_web_content` and other explicit source-open events that expose URLs". `fetch_web_content` URLs come from `function_call.args.url` — straightforward. The "other explicit source-open events" phrase is vague; in this pipeline it effectively means `grounding_metadata.grounding_chunks[].web.uri` (already harvested by `extract_sources_from_grounding`) plus tool-sourced URLs accumulated via `_tool_sources` in `worker_main.py:659-661`. Listing the exact sources in the plan avoids "what did we forget" in review.

### 4. Hybrid LLM notes — budget and kill-switch should be explicit

Plan §Note Generation Architecture caps at two LLM calls (plan-ready, research-underway-upgrade) with 3-second timeout and deterministic fallback. That framing is sound. Two tightenings:

- **Sequence with the pipeline, don't race it.** The LLM-note call should not block event emission. Kick it off when the milestone input is ready, post-write to Firestore when it resolves (or let the deterministic note stand). Otherwise a slow note-call blocks the user's perceived progress for 3 seconds per note.
- **Explicit kill-switch.** A single env var (`DISABLE_NOTE_LLM=true`) that forces deterministic-only. Plan already has the fallback path; making it flag-flippable in prod is a ~5-line addition that's worth having before the first user sees a weird LLM note in production.

## Things the plan marks as decided that I'd challenge mildly

- **"First-person commentary because Codex is first-person."** Superextra's voice per `CLAUDE.md` is "minimalistic, product-focused, avoid you/your." First-person is fine for the Codex reference but isn't automatically fine for this product. Worth a second look at the four deterministic strings in the plan before they ship — "Checking the venue and likely peer set before drafting the answer" reads like a person; the Superextra voice would say "Identifying the venue and likely peer set." Same structural plan, different voice. Not blocking, but worth a pass.
- **Keeping commentary + machine-summary but dropping raw details after completion.** Plan §After-the-turn says the compact summary drops raw detail rows by default. That's the right default but is asymmetric with "expandable" UX: users who click to expand a completed turn probably want everything, not just the four notes. Cheap improvement: keep `detail` count totals (already in `TurnCounts`) in the persisted `TurnSummary`, but don't persist individual detail-row text. One-line trade captured.

## Things the plan explicitly descopes — good

- **No second live narration agent.** Correct. A second agent writing ambient prose would double LLM cost, add latency, and be the exact "hack on a hack" the user wants gone.
- **No compatibility shims.** Correct. The old contract is the bug. Every line of translator code would carry the rot forward.
- **No per-token streaming.** Correct. RunConfig default emits zero partial-text events; there is nothing to stream even if we wanted to.

## Known ADK gotchas that don't block but worth knowing

- **`EventActions` state_delta merge bug** (google/adk-python [#1938](https://github.com/google/adk-python/issues/1938)): when multiple function_call parts in one event each update state, only the last state update survives the merge. This does NOT affect the plan — the new mapper counts from function_call args and function_response content directly, not from state_delta. Worth a one-line test comment noting that we deliberately don't rely on state_delta for per-call accumulation.
- **`before_agent_callback` signature is kwargs-only.** `CLAUDE.md` / `docs/deployment-gotchas.md` already calls this out; the drafting-trigger implementation (recommendation #1 above) must use `(*, callback_context)`.

## Implementation-order nit

Plan §Implementation Sequence lists backend contract → worker builder → agentCheck → frontend state → renderer → reply attachment → delete old → docs. That order is right in principle, but the first merge should be a worker-writes-new-events + frontend-still-renders-old-UI checkpoint so the new mapper can be validated against a real run before any UI deletion lands. Concretely:

1. New mapper writes new event shapes; **don't delete old event shapes yet**. Worker emits both for a single deploy.
2. Flip the frontend to the new renderer behind a `?newTimeline=1` URL param.
3. Once new UX is confirmed on a live run, delete the old emissions, delete old frontend code.

This is one extra deploy's worth of dual-emission, but it avoids the "the new thing is live and broken" failure mode and is cheaper than reverting the whole PR. The plan's "no compatibility shims" stance is about durable code, not about rollout safety — those are different concerns.

## Bottom line

The plan is the right shape. Its claims line up with the code and with ADK's actual event model. The four tightenings above are small — a paragraph each — and removable friction before coding starts. Once the drafting trigger, upgrade-in-place rule, count definitions, and LLM-note budget are locked, this is directly implementable and meaningfully simpler than what ships today.

## Sources

- [ADK Events](https://google.github.io/adk-docs/events/)
- [ADK Tool Performance / Parallel Tool Calls](https://google.github.io/adk-docs/tools-custom/performance/)
- [ADK Callbacks: Types](https://google.github.io/adk-docs/callbacks/types-of-callbacks/)
- [ADK Custom Agents](https://google.github.io/adk-docs/agents/custom-agents/)
- [ADK EventActions merge bug #1938](https://github.com/google/adk-python/issues/1938)
- [ADK Discussion #4301 — yielding custom messages](https://github.com/google/adk-python/discussions/4301)
- [Firestore Realtime Listeners](https://firebase.google.com/docs/firestore/query-data/listen)
- Internal: `docs/pipeline-decoupling-spike-results.md` (§B event taxonomy; §D collection-group query), `spikes/adk_event_taxonomy_dump.json` (21-event dump; event 15 = 3 parallel function_call parts)
