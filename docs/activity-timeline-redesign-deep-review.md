# Activity Timeline Redesign — Deep Review of Implementation

Reviewed against the redesign plan (`docs/activity-timeline-redesign.md`), the four review tightenings (`docs/activity-timeline-redesign-review.md`), the codebase as currently modified, all four test suites, the rendered UI in Chrome, ADK/Firestore docs, and ADK community/source-code references. Goal: a stable and clean implementation, not an exhaustive edge-case audit.

## TL;DR

**Approve, but ship as a single coordinated deploy.** The implementation matches the plan and all four prior review tightenings. All test suites pass. The new pipeline contract was verified end-to-end via simulated new-shape Firestore writes: all 14 timeline events + complete + `turnSummary` flow correctly through the listener and chat-state attaches `turnSummary` to the agent message.

The new UX renders correctly in light + dark + mobile and reads exactly like the Codex reference. The frontend is genuinely simpler than what shipped before — `StreamingProgress.svelte` shrank from 428 lines (typewriter groups, dot phases, section-done heuristics, staggered reveals) to **91 lines** of plain append-only rendering.

**One important deployment note:** the local rewrite is uncommitted/undeployed — the current Cloud Run worker still writes the OLD event contract (`type: 'activity'/'progress'`), and the deployed `agentCheck` still strips `turnSummary`. When the new frontend ships against the old worker, **users see no live timeline at all** during the cutover gap — the listener silently drops old-shape events. Reply, title, and sources still land via the session-doc terminal write, so it's degraded UX, not breakage. The `.github/workflows/deploy.yml` correctly deploys worker before hosting; that ordering matters here.

Three small follow-ups remain: a duplicated counts row at the bottom of the completed-turn summary, a small race window between LLM-note completion and the persisted summary build, and a one-line dead ternary in the timer expression. All cosmetic or low-risk; none block ship.

## How this review was performed

| Layer                                                      | Method                                                                                            | Result                                                                                                                  |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Mapper rewrite (`firestore_events.py`)                     | Read end-to-end, cross-referenced spike dump multi-call events                                    | Iterates every function_call/function_response part. Lossy `_first_function_call` removed.                              |
| Worker (`worker_main.py`)                                  | Read TurnSummaryBuilder, TimelineWriter, run-loop integration                                     | Builder + writer cleanly separated; per-call lock on writes; LLM-note tasks tracked + cancelled on terminal.            |
| Drafting trigger                                           | Read `agent.py` `_mark_drafting`, verified ADK semantics                                          | `before_agent_callback` writes `_drafting_started` to state; ADK yields a discrete state-delta event before synth runs. |
| Frontend transport (`firestore-stream.ts`)                 | Read; checked types vs new contract                                                               | Single `timeline` event type; old `progress`/`activity` deleted. `TurnSummary`/`TurnCounts` exported.                   |
| Frontend state (`chat-state.svelte.ts`)                    | Read; verified the live + recovery + resume paths                                                 | `liveTimeline`, `currentTurnStartedAtMs`, `typingMessageTimestamp` replace the old split state.                         |
| Renderer (`StreamingProgress.svelte`, `ChatThread.svelte`) | Visual inspection in Chrome at desktop + mobile, light + dark                                     | Codex-shape rendering; works in all four combinations.                                                                  |
| Tests                                                      | `npm run test`, `cd functions && npm test`, `cd agent && pytest`, `npm run lint`, `npm run check` | **88/88 vitest, 47/47 functions, 153 passed + 17 skipped pytest, 0 lint errors, 0 svelte-check errors.**                |
| ADK behavior                                               | Cross-checked adk-python source via search + issue tracker                                        | Confirmed `before_agent_callback` state-delta yields a discrete event before agent runs (issue #2992 noted).            |

E2E live pipeline was exercised in two ways:

1. **Real prompt against deployed worker.** Bypassed the Firebase init CORS issue with a Chrome MCP `initScript` that intercepts `/__/firebase/init.json` and returns the public web config. Submitted a real research query; the deployed worker ran for ~5 minutes and returned a real reply with 41 sources and a generated title. **The deployed worker (`superextra-worker-00025-ckj`, 2026-04-22 20:35) is still the OLD code**, so it wrote `type: 'activity'` and `type: 'progress'` event docs that the new frontend's listener silently discards (it only handles `type: 'timeline'`). The frontend gracefully degraded — no live timeline mid-run, but the reply, sources, and title all landed via the session-doc terminal write. No `turnSummary` was attached because (a) the worker doesn't write it and (b) the deployed `agentCheck` doesn't return it.
2. **Simulated new-contract worker.** Because the rewrite is uncommitted and not yet deployed, I wrote 14 new-shape `timeline` event docs + a `complete` session terminal with a `turnSummary` directly to Firestore for a fresh session, then attached the page's bundled listener. Result: **all 14 timeline events delivered correctly to `onTimelineEvent`, the complete event delivered with `hasSummary: true`, `summaryNotes: 3`, `summaryElapsed: 60000ms`, `srcCount: 4`, and the agent reply attached to chat-state with `turnSummary` populated**. End-to-end contract verified.

UX verification of the renderer used a temporary preview route that mounted `StreamingProgress.svelte` with realistic mock timeline data (light + dark + 390px mobile screenshots); the route was deleted after capture.

## What's right

### 1. The four prior review tightenings landed exactly as recommended

- **Drafting trigger via `before_agent_callback`** on the synthesizer (`agent.py:174-178`): `callback_context.state["_drafting_started"] = True; return None`. Mapper picks it up on `_has_state_delta(event, "_drafting_started")` (`firestore_events.py:175`) and emits a drafting timeline event. Verified via search of adk-python that this yields a discrete state-delta event ahead of the synth's first model call ([source](https://github.com/google/adk-python/blob/main/src/google/adk/agents/base_agent.py)). Test coverage in `test_drafting_state_delta_emits_drafting_event`.
- **Note #3 upgrade rule** is unambiguous: deterministic placeholder is emitted as `liveOnly: true` (`worker_main.py:1098-1106`); on real specialist content the LLM-upgrade fires; `finalize_notes` (`worker_main.py:746-748`) drops the live-only placeholder when the upgrade landed. Append-only contract preserved for the persisted summary; the brief live-only blip is kept inside the run only.
- **`queries` count includes only `google_search`** (`worker_main.py:580-583`). `search_restaurants` is correctly excluded from `webQueries` and contributes to `venues`. This matches what users expect to read as "Searched N queries".
- **LLM-note kill-switch + non-blocking** (`worker_main.py:462-463, 817-842`): `DISABLE_NOTE_LLM` env flag short-circuits to deterministic; `_emit_note_task` runs as a fire-and-forget `asyncio.create_task` — does not block the runner's event loop.

### 2. The mapper rewrite genuinely fixes the lossy single-call bug

`firestore_events.py:70-95` introduces `_iter_function_calls` and `_iter_function_responses` that walk every part of an ADK event. The empirical case from `spikes/adk_event_taxonomy_dump.json` (event 15: `review_analyst` with 3 parallel `find_tripadvisor_restaurant` calls) now produces 3 detail rows, not 1. Cross-checked against ADK docs that confirm `event.get_function_calls()` is the idiomatic accessor since v1.10.0 and that parallel tool calls land as multiple parts in a single event.

### 3. Frontend simplification is real

| File                       | Before                       | After                                                                              | Change                                                                                                                                                         |
| -------------------------- | ---------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `StreamingProgress.svelte` | 428                          | 91                                                                                 | −337 lines; deleted typewriter groups, dot-phase animation, section-done logic, staggered reveals, `analyze-synthesizer` special-case                          |
| `chat-state.svelte.ts`     | 769                          | 807                                                                                | +38 lines, but replaced two parallel progress concepts with one append-only `liveTimeline`; added `typingMessageTimestamp` for the drafting-typewriter handoff |
| `firestore-stream.ts`      | 268                          | 298                                                                                | +30 lines; removed `onProgress`/`onActivity` callbacks, added `onTimelineEvent` + `TurnSummary` types                                                          |
| `firestore_events.py`      | 391                          | 449                                                                                | +58 lines, but replaced category/status/special-ID contract with a structured `mapping` (`timeline_events` + `milestones` + `complete` + `grounding_sources`)  |
| `ChatThread.svelte`        | three streaming render paths | one timeline render + one "Starting research…" placeholder + one recovering banner | Reduced cognitive load substantially                                                                                                                           |

Net: ~+50 lines in frontend total, but the conceptual surface is dramatically smaller. `ChatThread` no longer owns the live-elapsed timer, no longer has three distinct streaming render paths, and no longer needs to reason about `analyze-synthesizer` IDs or category-specific ordering.

### 4. Backend integrity preserved

- Session doc remains the only terminal source. `terminal_update` at `worker_main.py:1233-1238` includes `turnSummary` in the same fenced txn as `status`/`reply`/`sources`/`title` — single atomic write, observers can't see a half-written terminal.
- `agentCheck` (`functions/index.js:518`) returns `turnSummary` so REST recovery and Firestore-listener completion agree on shape.
- `chat-recovery.ts` (`onReply` signature extended with `turnSummary`) and `chat-state.svelte.ts:resumeIfInFlight` (line 568) both attach `turnSummary` to the recovered message — the three completion paths (Firestore live, REST recovery, refresh-after-complete) all converge.
- Worker keeps the `_tool_src_<uuid>` drain pattern from commit `9890318` — unchanged by the rewrite, still load-bearing for parallel API tools.
- `_drafting_started` state-delta event won't be misinterpreted as the synth's terminal: `_map_synth_complete` looks for `state_delta["final_report"]` OR text content; the drafting event has neither, so it correctly returns `None` from the complete branch even though ADK reports `is_final_response()==True` for it (the [adk-python #2992](https://github.com/google/adk-python/issues/2992) quirk).

### 5. UX matches the Codex reference

Live timeline (mid-run) renders:

- `Working for Xm Ys` header with live-ticking timer
- Plain-language note rows with grey machine-summary line below each
- "Drafting the answer…" inline as a note
- Detail groups (Searching the web / Google Maps / TripAdvisor / Google reviews / Public sources / Warnings) with row text below each header

Completed reply renders:

- The answer body
- Sources pills
- A `<details>` collapsed `Worked for Xm Ys` summary expanding to the kept notes

Light + dark + mobile (390px) all render cleanly. Screenshots in `/home/adam/screenshots/timeline_preview_full.png`, `_dark.png`, `_mobile_dark.png`.

## Three follow-ups before merge

### 1. Final-counts row duplicates the last note's counts in the completed summary

`ChatThread.svelte:201-203` always renders `{formatCounts(summary.finalCounts)}` after the kept notes. Because the final note (`research_result`) is emitted near the end of the run, its counts snapshot equals the run's `finalCounts` in almost every realistic case. Result: two identical lines appear stacked, e.g.

```
... I'm comparing the strongest evidence ...
Searched 3 queries, Opened 12 sources, Checked 7 venues, Reviewed 4 platforms

Searched 3 queries, Opened 12 sources, Checked 7 venues, Reviewed 4 platforms   ← redundant
```

Confirmed visually in both light and dark mode (see screenshots above).

**Fix options (pick one):**

- Drop the standalone `finalCounts` row entirely — the last note already conveys it.
- Render `finalCounts` only when it differs from the last note's counts.

The first is simpler and matches the Codex reference (no totals row at the bottom).

### 2. LLM-note completion races persisted summary build

In `worker_main.py`:

- Line 1237: `terminal_update["turnSummary"] = timeline_builder.build_summary()` — finalizes notes (deterministic fallback wins for any LLM note still in flight).
- Line 1246: `await _fenced_update(..., terminal_update)` — commits the summary.
- Line 1251: `await _cancel_background_tasks(note_tasks)` — cancels still-pending LLM-note tasks.

If an LLM-note task completes between lines 1237 and 1251, it calls `builder.add_note(...)` which appends to `self.notes` AND writes a live timeline doc to Firestore. The live listener sees the LLM note. The persisted summary already serialized the deterministic fallback. End state: live UI showed the LLM note; the saved summary keeps the deterministic note.

Not a correctness bug (both texts are valid milestone notes), but it's a small observable inconsistency between what the user just watched and what's frozen on the reply.

**Fix:** await the LLM note tasks (or cancel them) before calling `build_summary()`. The bounded `NOTE_TIMEOUT_S=3.0` already caps the wait. Concretely: move `await _cancel_background_tasks(note_tasks)` (or `await asyncio.gather(*note_tasks, return_exceptions=True)`) to immediately before line 1237.

### 3. Cosmetic cleanups

- `StreamingProgress.svelte:67` — `formatDuration((startedAtMs ?? now) ? now - (startedAtMs ?? now) : 0)`. The ternary's false branch is dead (a millisecond timestamp is always truthy). Simplify to `formatDuration(startedAtMs ? now - startedAtMs : 0)`.
- `worker_main.py:746-752` — the second `notes = [n for n in notes if not (n["milestone"] == "research_placeholder" and n.get("liveOnly") and self.research_note_emitted)]` filter is a duplicate of the previous `if self.research_note_emitted` block. One filter is sufficient.

## Open question worth deciding

**Detail-row verbosity for tools that emit both a call and a response row.** Today, a single `find_tripadvisor_restaurant` flow produces two TripAdvisor rows ("Matching Umami" from the call, "Matched Umami" from the response), and `get_tripadvisor_reviews` adds "Reading reviews" → "34 reviews loaded". Three rows per TripAdvisor lookup. Functional but slightly busier than the Codex reference, which tends to show one row per logical step. Two cheap options:

1. Drop the call-row entirely when a response row is expected (most call→response pairs).
2. Keep the call-row but mark it visually subordinate.

Not blocking; flag and decide after a few real runs.

## Live E2E findings worth flagging

### A. Deployed worker is still old-contract

`gcloud run services describe superextra-worker` returned revision `superextra-worker-00025-ckj` (deployed 2026-04-22 20:35) — predates the rewrite. A real prompt submitted via the Chrome MCP harness produced 12 event docs in Firestore, all with `type: 'activity'` or `type: 'progress'` and the OLD `data` shape (no `kind`, `family`, `text`, `noteSource`, `counts`). The new frontend's listener `switch (doc.type)` handles only `'timeline'`, so all 12 events were silently dropped on the client. Reply (5KB structured analysis) + 41 sources + title still arrived via the session-doc terminal write. **No `turnSummary`** because the old worker doesn't write it and the deployed `agentCheck` doesn't return it.

This is not a bug in the redesign; it's the expected state until the worker is deployed. But it documents the cutover behavior precisely: **frontend-only deploy = invisible live timeline + missing post-completion summary**. The deploy workflow puts worker first, so a clean push of these changes will land both halves in the right order.

### B. Refresh-mid-flight + ?sid-matches-localStorage — pre-existing path that doesn't subscribe

If a user is mid-flight, refreshes the browser, and the URL `?sid=` matches `localStorage.activeId`, the page neither subscribes nor recovers:

- `chat-state.svelte.ts:506` `switchTo(id)` returns early when `id === currentId` — no `resumeIfInFlight` call.
- `+page.svelte:166-169` falls through to `chatState.recover()`, which requires `currentRunId` — never restored from localStorage.

End state: the listener doesn't attach. The user sees their question with no progress + no auto-recover. This is **not introduced by this rewrite** — `switchTo`'s early-return predates it, and `currentRunId` was never persisted. But this rewrite is a good moment to fix it. Two-line fix: in `+page.svelte`'s onMount, when the URL `?sid` matches the loaded conversation AND last message is from the user, call a public `resumeIfInFlight` method (currently private inside `chat-state.svelte.ts`) instead of `recover()`.

### C. ADK callback signature noted in CLAUDE.md is satisfied

`_mark_drafting(*, callback_context)` — keyword-only args, matches ADK's expectation per `docs/deployment-gotchas.md` "ADK callbacks use keyword arguments". Confirmed.

## Things checked and confirmed clean

- ADK `before_agent_callback` kwargs-only signature ✓ (`_mark_drafting(*, callback_context)`)
- ADK callback state-delta ordering ✓ (yields discrete event before agent runs)
- `is_final_response()==True` quirk for state-delta event ✓ (does not falsely trigger `_map_synth_complete`)
- `_tool_src_<uuid>` drain still in place ✓ (`worker_main.py:1064-1067`)
- Single fenced txn for `status + reply + sources + title + turnSummary` ✓
- Recovery via `agentCheck` returns `turnSummary` ✓
- Resume after refresh attaches `turnSummary` ✓ (`chat-state.svelte.ts:568`)
- All four test suites green ✓
- Lint + svelte-check ✓ (0 errors)

## Sources

- [ADK Events](https://google.github.io/adk-docs/events/) — multi-part function_call shape
- [ADK Tool Performance / Parallel Tool Calls](https://google.github.io/adk-docs/tools-custom/performance/) — confirms parallel calls in single event since v1.10.0
- [ADK Callbacks: Types](https://google.github.io/adk-docs/callbacks/types-of-callbacks/) — `before_agent_callback` semantics
- [adk-python `base_agent.py`](https://github.com/google/adk-python/blob/main/src/google/adk/agents/base_agent.py) — state-delta event yield ordering
- [adk-python issue #2992](https://github.com/google/adk-python/issues/2992) — `is_final_response()==True` for state-delta event from before_agent_callback
- [Firestore Realtime Listeners](https://firebase.google.com/docs/firestore/query-data/listen)
- Internal: `docs/activity-timeline-redesign.md`, `docs/activity-timeline-redesign-review.md`, `spikes/adk_event_taxonomy_dump.json`
