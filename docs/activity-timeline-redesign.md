# Activity Timeline Redesign

## Summary

Replace the current progressive-updates UI with a simpler, Codex-shaped turn timeline.

The redesign keeps the durable execution substrate introduced by the pipeline-decoupling work, but replaces the user-facing activity contract, frontend state model, and rendering approach. The goal is to remove the current layered progress system, stop exposing internal activity noise directly to the user, and produce a calmer append-only experience that is easier to understand, easier to maintain, and easier to review.

This document is intended to be decision-complete for implementation review and external technical review.

## Why This Redesign Exists

The current activity-updates approach is the wrong abstraction for the product experience.

What exists today:

- The browser keeps two parallel progress concepts: `streamingProgress` and `streamingActivities`.
- The UI renders a sectioned progress widget with category-specific behavior.
- The backend emits activity objects shaped around internal tools and pipeline stages.
- The frontend contains logic to reconcile status updates, attempt changes, special IDs, category-specific animations, and terminal edge cases.

Why that is a problem:

- The user sees a system-status widget rather than a readable research transcript.
- The UI contract is more complicated than the value it creates.
- The model is fragile because the UI expects activity IDs and completion patterns that the backend does not consistently produce.
- Multiple code paths exist only to preserve the old widget rather than represent durable product meaning.
- The current design treats symptoms in several places instead of fixing the root cause: the wrong activity model.

The redesign therefore starts from a clean contract rather than iterating the current one.

## Reference Shape

The UX reference is the Codex activity view shared in the review thread.

The important characteristics of that reference are:

- One top line showing elapsed working time.
- Short plain-language commentary entries in a linear transcript.
- A smaller machine summary directly below each commentary entry.
- Lower-prominence raw activity details below that.
- Append-only behavior. Entries appear; they do not keep changing state.
- Calm layout. It is not a dashboard, checklist, or animated state machine.

The redesign should copy that structural pattern, adapted to Superextra's research workflow.

## Sources Consulted

### Codebase

- [`src/lib/chat-state.svelte.ts`](../src/lib/chat-state.svelte.ts)
- [`src/lib/firestore-stream.ts`](../src/lib/firestore-stream.ts)
- [`src/lib/components/restaurants/ChatThread.svelte`](../src/lib/components/restaurants/ChatThread.svelte)
- `src/lib/components/restaurants/StreamingProgress.svelte`
- [`agent/superextra_agent/firestore_events.py`](../agent/superextra_agent/firestore_events.py)
- [`agent/worker_main.py`](../agent/worker_main.py)
- [`agent/superextra_agent/agent.py`](../agent/superextra_agent/agent.py)
- [`agent/superextra_agent/specialists.py`](../agent/superextra_agent/specialists.py)
- [`agent/superextra_agent/chat_logger.py`](../agent/superextra_agent/chat_logger.py)
- [`agent/tests/test_firestore_events.py`](../agent/tests/test_firestore_events.py)
- [`agent/tests/test_worker_main.py`](../agent/tests/test_worker_main.py)

### Internal docs

- [`docs/pipeline-decoupling-plan.md`](./pipeline-decoupling-plan.md)
- [`docs/pipeline-decoupling-fixes-plan.md`](./pipeline-decoupling-fixes-plan.md)
- [`docs/pipeline-decoupling-spike-results.md`](./pipeline-decoupling-spike-results.md)

### External docs

- [ADK Events](https://adk.dev/events/)
- [ADK Callbacks](https://google.github.io/adk-docs/callbacks/)
- [ADK Context](https://google.github.io/adk-docs/context/)
- [Firestore listeners](https://firebase.google.com/docs/firestore/query-data/listen)

## Constraints From The Actual Pipeline

This redesign is grounded in the current pipeline and real log traces.

Observed/verified constraints:

- The durable transport is already correct in broad shape: browser POST -> Cloud Function enqueue -> Cloud Tasks -> worker -> Firestore session doc plus events -> browser snapshot observers.
- The worker's event loop already sees ADK events and maps them in-process before writing to Firestore.
- The current tool layer now already preserves more per-call attribution than when this plan was first drafted:
  - API-backed provider tools write unique per-call `_tool_src_<uuid>` state keys, so parallel TripAdvisor and Google Reviews calls no longer clobber each other's source metadata inside one ADK event.
  - Places writes per-place `_place_name_<place_id>` metadata, so downstream review-source attribution can label the correct venue without extra API fetches.
  - `_target_lat` / `_target_lng` are now protected from competitor batch fetches, so geo-biased web search remains centered on the target venue rather than whichever competitor completed last.
- The pipeline has real milestone boundaries that can support user-visible progress:
  - context enrichment starts
  - Places context completes
  - orchestrator plan completes
  - specialists begin source work
  - synthesizer starts
- The pipeline does not provide reliable streaming partial-answer text before synthesis completes, so fake typing must remain an end-phase effect only.
- Some runs expose explicit search-like activity, but source-opening activity is more reliable than explicit search-query activity. The UX cannot depend on always having a visible web-search query line.
- The current mapper only takes the first function call from an ADK event. That is too lossy for a transcript-shaped activity feed.

These constraints mean the redesign should show only what the system can reliably know and avoid invented continuous narration.

## Desired User Experience

### While a turn is running

The user sees:

1. A single elapsed-time line:

   `Working for 1m 08s`

2. A linear timeline underneath it.

3. A small number of commentary entries written in plain language.

4. Under each commentary entry, one gray machine-summary line.

5. Below that, grouped raw detail rows for searches, platforms, sources, and warnings.

6. `Drafting the answer…` near the end, followed by fake typing in the final answer area.

### After the turn completes

The live activity panel disappears.

The completed agent reply keeps a compact transcript summary attached to that turn:

- collapsed by default
- headed with the final elapsed time, for example `Worked for 3m 12s`
- expandable
- when expanded, shows only the kept commentary entries and their gray summary lines
- does not keep the full raw live detail feed by default
- keeps aggregate final count totals, but not the full raw detail-row text

This keeps the useful narrative memory while removing noisy operational logs from completed turns.

### Example

```text
Working for 1m 08s

Checking the venue and likely peer set before drafting the answer.
Reviewed 5 venues, opened 7 sources

I’ve identified the strongest comparables and I’m validating them across review and public sources.
Reviewed 2 platforms, opened 9 sources

Searching the web
best premium burger berlin
site:wolt.com berlin burger

Google Maps
target venue
4 competitor profiles

TripAdvisor
matched 4 venues
fetched review pages

Drafting the answer…
```

Completed-turn summary example:

```text
Worked for 3m 12s

Checking the venue and likely peer set before drafting the answer.
Reviewed 5 venues, opened 7 sources

I’ve identified the strongest comparables and I’m validating them across review and public sources.
Reviewed 2 platforms, opened 9 sources

Pulling the findings together before drafting the answer.
Reviewed 3 platforms, opened 12 sources
```

## Experience Rules

- The timeline is append-only.
- Visible rows do not switch between `pending`, `running`, and `complete`.
- The UI does not render internal agent names or tool names directly.
- Commentary entries are sparse. Maximum 5 while a turn is live; persisted completed summaries keep at most 4.
- Commentary entries are short. Maximum about 28 words.
- Commentary entries default to first-person to match the reference, but deterministic strings should get a final product-voice pass before ship.
- Commentary entries do not speculate about work that has not started.
- Searches and source/platform details are open while the turn is running.
- After completion, only the compact summary transcript is retained with the reply.
- Fake typing starts only after the system enters the drafting phase.

## Product Decisions Locked

- Keep summary after completion.
- Show searches and sources open while the turn is running.
- Use a hybrid commentary model:
  - deterministic notes at milestone boundaries when no meaningful content exists yet
  - LLM-written note when a milestone already has real content worth summarizing
  - deterministic fallback if note generation is missing, empty, slow, or fails
- Store the kept-after-run summary attached to the agent reply rather than introducing a larger turn data model.

## New Activity Model

Replace the current progress/activity split with a single timeline.

### Browser-visible live event types

```ts
type TurnCounts = {
	webQueries: number;
	sources: number;
	venues: number;
	platforms: number;
};

type TimelineEvent =
	| {
			kind: 'note';
			id: string;
			text: string;
			noteSource: 'deterministic' | 'llm';
			counts: TurnCounts;
			ts: number;
	  }
	| {
			kind: 'detail';
			id: string;
			group: 'search' | 'platform' | 'source' | 'warning';
			family:
				| 'Searching the web'
				| 'Google Maps'
				| 'TripAdvisor'
				| 'Google reviews'
				| 'Public sources'
				| 'Warnings';
			text: string;
			ts: number;
	  }
	| {
			kind: 'drafting';
			id: string;
			text: 'Drafting the answer…';
			ts: number;
	  };
```

### Persisted completed-turn summary

```ts
type TurnSummary = {
	startedAtMs: number;
	finishedAtMs: number;
	elapsedMs: number;
	notes: Array<{
		text: string;
		noteSource: 'deterministic' | 'llm';
		counts: TurnCounts;
	}>;
	finalCounts: TurnCounts;
};
```

### Reply payload change

`ChatMessage` gains an optional `turnSummary` field used only on agent replies.

The session terminal payload and `agentCheck` response also gain `turnSummary`.

## Milestone Model

The commentary system is milestone-based, not continuously narrated.

There are exactly four note opportunities:

1. **Context start**
   - Trigger: first real context-enricher activity
   - Output: deterministic
   - Example:
     `Checking the venue and likely peer set before drafting the answer.`

2. **Plan ready**
   - Trigger: `research_plan` exists
   - Output: LLM-written, with deterministic fallback
   - Input: `research_plan`
   - Purpose: summarize what is now known about the angle of attack

3. **Research underway**
   - Trigger A: first specialist/source detail activity
   - Output A: deterministic placeholder immediately when source work starts
   - Trigger B: first specialist final event in event order whose output key passes `_has_state_delta(...)` and is not `NOT_RELEVANT`
   - Output B: LLM-written note, with deterministic fallback
   - Input B: first non-`NOT_RELEVANT` specialist result plus accumulated counts
   - Append rule:
     - if A has already emitted when B arrives, B appends as a new note in the live timeline
     - the deterministic placeholder remains live-only and is omitted from persisted `turnSummary` if B exists

4. **Drafting**
   - Trigger: synthesizer `before_agent_callback`
   - Mechanism:
     - add a kwargs-only callback `def _mark_drafting(*, callback_context): ...`
     - set `callback_context.state["_drafting_started"] = True`
     - detect that state delta in the mapper and emit the drafting timeline event before the synthesizer's final reply lands
     - treat `_drafting_started` as a progress signal even if a callback-generated ADK event is marked final
   - Output: deterministic
   - Exact text:
     `Drafting the answer…`

No other notes are emitted.

Live runs can therefore show 3-5 note rows. Persisted completed summaries keep at most 4 by dropping the provisional research-start placeholder if a later research-insight note exists.

## Note Generation Architecture

The note generator is not a second live narration system.

It is a small helper fed by existing milestone outputs.

### Allowed LLM note sources

- `research_plan`
- first real specialist output

### Invocation rules

- note generation is asynchronous and never blocks detail-row emission
- deterministic milestone notes should be emitted immediately when the milestone is reached
- if an LLM-generated note resolves later, it appends as its own note row or is skipped in favor of the deterministic fallback path
- note generation is attempted only at the locked milestones above; there is no ambient narration loop

### Not allowed

- continuous narration
- extra agent inserted into the pipeline
- note generation from raw tool-call spam

### Prompt rules

- one sentence
- first person
- no tool names
- no platform vendor jargon unless user-visible and meaningful
- no claims about unseen work
- max 28 words
- user's language

### Failure policy

- timeout: 3 seconds
- empty output: fallback
- model error: fallback
- malformed output: fallback

### Kill-switch

- environment flag: `DISABLE_NOTE_LLM=true`
- when set, the system emits deterministic-only commentary and skips all note LLM calls

### Parallel-call safety

- do not rely on `state_delta` to reconstruct per-call tool activity or counts
- per-call accumulation must come from function-call args and function-response payloads directly
- this avoids ADK multi-call `EventActions.state_delta` merge limitations when several function calls share one event

Fallback text is deterministic and milestone-specific.

## Detail Mapping

Raw detail rows are still grounded in real work, but mapped into product language.

### Tool family mapping

- `get_restaurant_details`
- `search_restaurants`
- `find_nearby_restaurants`
- `get_batch_restaurant_details`
  - family: `Google Maps`

- `find_tripadvisor_restaurant`
- `get_tripadvisor_reviews`
  - family: `TripAdvisor`

- `get_google_reviews`
  - family: `Google reviews`

- `google_search`
  - family: `Searching the web`

- `fetch_web_content`
  - family: `Public sources`

- uncertainty or failure conditions
  - family: `Warnings`

### Result-aware detail rows

The redesigned mapper must inspect both function calls and function responses when the ADK event exposes them.

If a tool response is visible:

- use it to produce a better row such as `4 competitor profiles` or `matched 5 venues`
- enrich venue labels from existing per-place metadata such as `_place_name_<place_id>` when that state is already available, rather than re-fetching names

If a tool response is not visible:

- emit a simpler call-driven row rather than inventing richer detail

### Warning rows

Warnings are shown only when there is real evidence of uncertainty or failure, for example:

- low-confidence venue matching on TripAdvisor
- structured review source unavailable
- source fetch failure worth surfacing

Warnings are not generic retries or backend noise.

## Counting Rules

The gray machine-summary line under each note is based on a count snapshot captured at note time.

### Count definitions

- `webQueries`
  - count unique normalized `google_search` query strings only
  - `search_restaurants` remains visible as a `Google Maps` detail row but does not increment the web-query count

- `sources`
  - count unique normalized URLs from:
    - `fetch_web_content` call URLs
    - `grounding_metadata.grounding_chunks[].web.uri` when they are surfaced into visible source rows or terminal sources
    - explicit tool-returned URLs that the mapper turns into visible source rows

- `venues`
  - count unique venue identifiers or normalized venue names touched by Places, TripAdvisor, or Google reviews tools

- `platforms`
  - count unique platform families encountered in the run

### Dedup rules

- repeated identical detail rows do not re-emit
- repeated identical inputs do not increment counts twice
- duplicated URLs count once
- duplicated queries count once after normalization

## Backend Design

### Keep

- worker, Cloud Tasks, Firestore session doc, event subcollection, watchdog, `agentCheck`
- session doc as the only terminal source
- collection-group event query for progress

### Replace

- current mapper contract in `firestore_events.py`
- worker-side accumulation assumptions tied to the old progress widget

### Mapper changes

Current state:

- `map_event(event)` returns zero or one emission
- `_first_function_call(event)` makes the mapper blind to additional function calls in the same ADK event

New state:

- replace the single-emission mapper with `map_event_to_timeline_events(event, state)` that can emit zero or more timeline events
- iterate all function-call parts using ADK's multi-call event accessors where available, with a `content.parts` fallback
- inspect function-response parts where available
- emit timeline detail rows in order
- emit note and drafting events only at the locked milestone boundaries
- do not use `state_delta` as the source of truth for per-call accumulation; use function calls and function responses directly

### Worker changes

Current state:

- worker writes mapped events as they arrive
- session doc terminal write contains reply, sources, title

New state:

- introduce a `TurnSummaryBuilder` inside the worker
- it tracks:
  - run start time
  - dedup state for counts
  - note snapshots
  - current count totals
- on each emitted timeline event:
  - update the builder
  - write the progress event doc
- on terminal fenced session write:
  - include `turnSummary`
  - preserve existing `reply`, `sources`, and `title`
- keep the existing `_tool_src_<uuid>` drain for terminal-source union during rollout and migration; it is still useful for API-backed provider attribution even though live timeline detail rows should be derived from function calls and function responses directly
- note generation tasks must not block event writes or terminal completion; they write their note events only if still relevant when they resolve

`turnSummary` written by the server is the source of truth for completed turns.

The browser does not reconstruct the persisted summary from its ephemeral live state.

### `agentCheck`

`agentCheck` must return `turnSummary` in the terminal payload so Firestore completion and REST recovery behave identically.

## Frontend Design

### State model

Delete:

- `StreamingStep`
- `ActivityCategory`
- `ActivityItem`
- `streamingProgress`
- `streamingActivities`
- `isStreaming` as currently defined

Add:

- `liveTimeline: TimelineEvent[]`
- `currentTurnStartedAtMs: number | null`

Keep:

- `messages`
- `loading`
- `recovering`
- `error`
- `currentRunId`

### Rendering model

Replace the current `StreamingProgress` approach in `ChatThread.svelte` with one new timeline component.

That component renders:

- `Working for ...` header while live
- commentary note rows
- gray summary line below each note
- grouped detail rows below the notes
- `Drafting the answer…`

Completed agent replies render:

- the answer body
- sources as today
- a collapsed `Worked for ...` summary using `turnSummary`

### Timer behavior

The timer is tied to the run start time.

It does not depend on any specific step being marked `running`.

### Recovery behavior

If the user reloads mid-run:

- Firestore event docs rebuild the live timeline
- if the terminal arrives via `agentCheck`, the reply and `turnSummary` are attached exactly as they would be from Firestore completion

## Cleanup Scope

This redesign is explicitly a cleanup project, not an additive compatibility layer.

### Delete entirely

- `src/lib/components/restaurants/StreamingProgress.svelte`

### Remove old logic from state and transport

- progress/activity split in `chat-state.svelte.ts`
- old `StreamCallbacks.onProgress`
- old `StreamCallbacks.onActivity`
- old activity-specific merge/update logic
- attempt-change behavior that seeds retry-only `streamingProgress`

### Remove special old-widget assumptions from backend

- category/status activity contract
- special IDs such as:
  - `search-web`
  - `data-primary`
  - `data-check`
  - `analyze-synthesizer`
  - `all-complete`
- old "section done" semantics that exist only for the current widget

### Do not keep compatibility shims

Do not build translators that preserve the old frontend model behind the scenes.

The old model is the problem.

Implement the new timeline contract directly.

One short-lived validation gate is allowed during rollout:

- worker may temporarily dual-emit old and new event shapes for one validation deploy
- frontend may temporarily gate the new timeline behind `?newTimeline=1`
- both must be deleted before the final cleanup merge

## Implementation Sequence

1. Write the new backend event and summary contract.
2. Implement the worker-side summary builder, drafting callback, and terminal `turnSummary` write.
3. Update `agentCheck` to return `turnSummary`.
4. Add a short-lived live-validation checkpoint:
   - worker dual-emits old and new event shapes
   - frontend can render the new timeline behind `?newTimeline=1`
5. Validate the new mapper and timeline on a real run.
6. Replace frontend stream subscription/state handling with `liveTimeline`.
7. Build the new timeline renderer and attach completed-turn summaries to agent replies.
8. Delete the temporary dual-emission/query-param gate, then delete the old widget and legacy activity code.
9. Update docs and tests together.

## Test Plan

### Backend mapper tests

- one ADK event with multiple `function_call` parts emits multiple timeline events
- one ADK event with `function_response` emits result-aware detail rows
- repeated identical activity dedupes correctly
- low-confidence TripAdvisor match emits a warning row
- note emission occurs only at the four allowed milestones
- drafting emits from `_drafting_started` callback state, not from a client heuristic
- no old widget IDs remain in the emitted contract

### Worker tests

- `TurnSummaryBuilder` computes counts correctly
- note snapshots store count values at emission time
- terminal session write includes `turnSummary`
- `agentCheck` returns `turnSummary`
- LLM note timeout falls back to deterministic text
- `DISABLE_NOTE_LLM=true` forces deterministic-only commentary
- research-start placeholder is omitted from persisted `turnSummary` when a later research-insight note exists

### Frontend tests

- `liveTimeline` is append-only
- rows do not change status after insertion
- completion attaches `turnSummary` to the agent reply and clears the live detail feed
- reload mid-run rebuilds timeline from Firestore events
- REST recovery attaches the same completed summary shape as Firestore
- completed reply renders compact summary rather than the old live activity widget
- validation-gated new timeline can coexist temporarily with old emissions without changing the final cleanup target

### Acceptance scenarios

- narrow query with only Places plus one specialist
- broad query with several specialists and many sources
- run with platform/source rows but no visible web-search query rows
- warning case with low-confidence TripAdvisor match
- Firestore-blocked recovery path

## Reviewer Checklist

External reviewers should focus on:

- whether the new timeline contract is the right abstraction
- whether hybrid note generation is the right complexity tradeoff
- whether `turnSummary` should live on the reply/session payload rather than a separate turn model
- whether any kept detail rows are still too operational
- whether the cleanup scope is aggressive enough to avoid legacy drag

## Assumptions

- The transport substrate from the decoupling work remains in place.
- Completed turns keep only a summary transcript, not full raw detail by default.
- First-person commentary is acceptable because it matches the selected reference style.
- `Working for ...` is the live header and `Worked for ...` is the completed summary header.
- The redesign prefers removal over compatibility where the old approach exists only to support the current progress widget.
