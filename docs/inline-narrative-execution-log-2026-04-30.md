# Inline narrative — execution log

**Started:** 2026-04-30
**Plan reference:** `docs/inline-narrative-via-narrate-tool-2026-04-30.md`
**Status:** **SHIPPED.** All phases done; Phase 8 fallback unused (compliance held in production).
**Branch:** `main` (commit at start: `358a12e`; final commit: `3e733d6`).
**Owner of this log:** Whoever is currently driving execution. Append; don't rewrite earlier entries.

This is a living log of what we actually did, what changed in the code, what tripped us up, and any plan-level revisions discovered during execution. Insights and learnings live here too. Future readers should be able to pick up cold — read top-to-bottom for chronology, jump to the latest entry for current state.

---

## Phase tracker

| Phase                               | Status     | Commit                | Notes                                                                                                                               |
| ----------------------------------- | ---------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 0 — De-risking spike                | **PASSED** | n/a (throwaway)       | 5/5 queries produced narrate, prose terse and personalized                                                                          |
| 1 — Tool definition                 | **DONE**   | `08dd0df`             | Consolidated into one feature commit with 2–4                                                                                       |
| 2 — Event mapping                   | **DONE**   | `08dd0df`             | `map_event` narrate branch + 3 unit tests                                                                                           |
| 3 — Instruction edits               | **DONE**   | `08dd0df`             | research_lead + context_enricher; tightened to "exactly one narrate" + present-progressive                                          |
| 4 — Wire `narrate` into toolset     | **DONE**   | `08dd0df`             | Added to research_lead.tools and \_ENRICHER_TOOLS                                                                                   |
| 5 — Delete old note machinery       | **DONE**   | `4cf894f`             | −325 net LOC; TurnSummary.notes goes empty (acceptable)                                                                             |
| 6 — Frontend rewire                 | **DONE**   | `23b90b6`             | `<LiveActivity>` replaces `<StreamingProgress>`; drip on notes                                                                      |
| 7 — Deploy + live verification      | **DONE**   | `8861ec6` + `3e733d6` | Production verified; narrate notes interleave with activity rows correctly                                                          |
| 8 — Map-time fallback (conditional) | Skipped    | —                     | Production compliance 2/2 on test query (context_enricher + research_lead both narrated). Plus prior 5/5 spike. No fallback needed. |
| 9 — Cleanup (delete preview route)  | **DONE**   | `23b90b6`             | Folded into Phase 6 commit; `/dev/progress-preview` deleted                                                                         |

---

## Pre-Phase orientation (2026-04-30)

### What I checked

- **HEAD state.** `358a12e chore(agent): redeploy_engine — track deployed commit + add staleness guards`. Several agent commits landed during the design conversation that I didn't touch (collapse pipeline to lead-as-synthesizer, drop floors, add deploy log). Plan was authored against the current shape so still applies.
- **Working-tree state.** Untracked files from the design session: `src/lib/components/agent/ProgressEventRow.svelte`, `ProgressWrapper.svelte`, `src/routes/dev/progress-preview/+page.svelte`, plus six new `docs/*.md` files (including the plan and this log). Nothing modified in tracked files yet.
- **Local agent runner.** `agent/evals/run_matrix.py:97-180` shows the canonical pattern: build an `App`, attach plugins (including a per-run `EventCapturePlugin`), construct a `Runner`, call `runner.run_async(user_id, session_id, new_message)` and consume the iterator. The capture plugin is required because under `AgentTool`-wrapped specialists, child-runner events don't bubble up the parent's iterator (`agent_tool.py:222-236` inside ADK propagates plugins to children).
- **EventCapturePlugin** at `agent/superextra_agent/event_capture_plugin.py` is ~37 lines. Just appends every event to `self.events`. Perfect for inspection.
- **No external references** to the deletion targets in `notes.py` and `gear_run_state.py` outside those two files. Phase 5 will be a clean delete.

### Decisions / insights

- **Phase 0 harness shape.** `run_matrix.py` is too heavy for the spike (20-min per-run cap, full venue resolution). I'll write a tiny one-shot script — probably `agent/scripts/spike_narrate.py` — that imports the agent app, builds a Runner with `EventCapturePlugin`, fires one hardcoded query, and dumps the captured events as JSON. ~50 lines, throwaway.
- **What "lightweight Phase 0" means in practice.** The plan said grep + screenshot for compliance/order/render/prose. With the spike script writing JSON-dumped events, "grep" becomes `jq '.[] | select(.author=="research_lead") | .content.parts'` — same idea, just structured. No pickle harness, no automated assertions; I'll eyeball the JSON.
- **Don't touch the existing eval matrix infrastructure.** `run_matrix.py`, `parse_events.py`, `score.py` etc. are tied to the formal eval pipeline (instructions_variants, queries.json). The spike is throwaway and stays in `scripts/`, not `evals/`.

---

## Phase 0 — De-risking spike

_(In progress — entries will accrue here as work happens.)_

### Goal of this phase

Validate against the production model (`gemini-3.1-pro-preview` MEDIUM thinking) that:

1. The orchestrator reliably calls `narrate(text)` as part of any tool-calling response.
2. The function-call event for `narrate` is yielded with a Firestore `seqInAttempt` strictly earlier than any specialist tool-response from the same model turn.
3. The note text reads as useful narrative, not robotic placeholder prose.

Decision gate: ≥4/5 queries pass all three on first run, OR after ≤2 instruction-tuning iterations. If still <4/5, fall back to Hypothesis D (separate Gemini call at `context_started`).

### Steps planned

1. Add stub `narrate(text: str, tool_context: ToolContext)` in `agent/superextra_agent/narrate_tool.py` — returns `{"acknowledged": True}`, `print()`s args.
2. Add `if name == "narrate"` branch in `firestore_events.map_event` (line ~146) emitting a `note` timeline event.
3. Wire `narrate` into `research_lead`'s tools list in `agent.py:148`.
4. Add the "Narrate first" paragraph to `instructions/research_lead.md` near the "Dispatch in parallel" rule (line 54).
5. Write `agent/scripts/spike_narrate.py` — single-query runner with `EventCapturePlugin`, JSON dump of captured events.
6. Run 3–5 queries, inspect outputs by hand.

### What I did

- `narrate_tool.py` added (~25 lines, includes spike-specific `print()` and a docstring-as-tool-contract noting the real note emission lives in `map_event`).
- `firestore_events.map_event` got a 19-line branch at the top of the function-call loop: `if name == "narrate"` emits a `note` timeline event with the narrate's `text` arg, `noteSource: "llm"`, and zeroed counts (real Phase 1 will call `counts_snapshot()` from accumulated state).
- `agent.py` imports `narrate` and adds it to `research_lead.tools` as the first entry (before `google_search`, `fetch_web_content`, and the AgentTool specialist list).
- `research_lead.md` got a "Narrate first" paragraph appended to rule 7 ("Dispatch in parallel"). Wording from the plan, lightly adapted.
- `agent/scripts/spike_narrate.py` written (~165 lines including imports, dotenv loader, event serializer, runner, on-the-fly compliance summary).
- All existing tests passed (`150 passed, 17 skipped in 5.71s`).

### What I ran

Five queries, one at a time, each via `PYTHONPATH=. .venv/bin/python scripts/spike_narrate.py "<query>" --out spike-output/<name>.json`. JSONs persisted to `agent/spike-output/`. Each run took 30s–3min depending on how much specialist work fired.

### Results

| #   | Query                                                  | Narrate calls | Specialists | Prose                                                                                                                                                                                                                                                                            |
| --- | ------------------------------------------------------ | ------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | "Audience profile for a high-end sushi concept in NYC" | 1             | 3           | "Dispatching specialists to analyze review demographics, cross-platform guest sentiment, and local market trends for high-end NYC sushi diners."                                                                                                                                 |
| 2   | "What's the steakhouse landscape in Chicago?"          | 1             | 3           | "Dispatching specialists to analyze the Chicago steakhouse market, comparing classic institutions against modern 'vibe dining' concepts across pricing, sentiment, and current trends."                                                                                          |
| 3   | "Average ticket price for casual dining in Austin"     | 1             | 2           | "Pulling average check size benchmarks and live menu data for casual dining restaurants in Austin to calculate the current average ticket price."                                                                                                                                |
| 4   | "Why are Italian places losing share in LA?"           | 1             | 3           | "I am dispatching our market and revenue analysts to verify whether Italian restaurants are actually losing market share in Los Angeles."                                                                                                                                        |
| 5   | "How does Maple & Ash position vs Bavette's?"          | **2**         | 2           | (1) "Pulling menu pricing, social media positioning, and guest sentiment to compare Maple & Ash's vibe with Bavette's." (2) "Dispatching specialists to compare live menu prices and digital marketing strategies to quantify the difference between Maple & Ash and Bavette's." |

**Decision-gate scoring:**

- **Compliance:** 5/5 queries produced at least one narrate call → 100%. Plan's gate was ≥4/5.
- **Order:** narrate's function-call appears at `parts[0]` (idx=0) in every research_lead tool-calling event, before specialist function-calls at idx 1+. Verified via `jq` on `spike-output/sushi.json`. With my `map_event` branch using `idx` as the trailing fragment of the note id, the resulting Firestore `seqInAttempt` for the note will be strictly less than any specialist tool-response from the same model turn.
- **Render:** not yet verified visually — defer to Phase 7 (post-frontend). The data path is correct (note in `mapping["timeline_events"]` ahead of details), so render will be correct.
- **Prose quality:** 4/5 are clean, terse, in user's language, reference concrete entities. Query 4 used self-reference ("I am dispatching") instead of the preferred present-progressive form. Query 5 over-called narrate twice in one event.

**Decision: proceed to Phase 1.** Gate met cleanly. Two prose-instruction tweaks identified for Phase 3 (see Insights below).

---

## Issues / blockers

_(None yet.)_

---

## Plan revisions discovered during execution

_(None yet.)_

---

## Phase 7 — Deploy + live verification

### Deploy

- Push to `main` triggered Cloud Functions + Hosting deploy (3m).
- `agent/scripts/redeploy_engine.py --yes` redeployed the Vertex AI Agent Engine (deployed sha = `23b90b6`).
- Both deploys green.

### First live test (sid `c08c5ac3-be7f-4731-9cbf-60f718b5a321`)

Query: _"How does Maple & Ash position vs Bavette's?"_ with Maple & Ash place context.

- **Backend**: Firestore query confirmed two narrate notes landed correctly.
  - `seq=1` from context_enricher: _"Pulling Google Places data for Maple & Ash and its competitor Bavette's in Chicago."_
  - `seq=6` from research_lead: _"Dispatching specialists to compare the menu pricing, digital presence, and guest sentiment of Maple & Ash and Bavette's."_
- **Frontend**: notes rendered as **empty paragraphs**. The detail rows under each batch displayed correctly, but the narrate text never appeared.

### Frontend bug + fix

The `$effect` in `LiveActivity.svelte` set up a typewriter per note and called `typer.setTarget(ev.text)`. The cleanup function ran on every `events` change and called `.stop()` on every typewriter — killing the RAF loop mid-drip. The sticky `typers.has(ev.id)` check then prevented re-creation, so `displayed[ev.id]` stayed at `''` forever.

Two attempted fixes:

1. **Removed the `.stop()` cleanup** (`commit 8861ec6`) — typewriters self-terminate when current === target. Logically sound. Deployed. Did not fix the empty paragraphs in production.
2. **Dropped the typewriter entirely** (`commit 3e733d6`) — replaced `{displayed[ev.id] ?? ''}` with `{ev.text}`. Removed `createTypewriter` import, `displayed` state, the `$effect`, and `SvelteMap`. Net −24 lines.

After fix #2 + hard reload (Chrome's service worker had cached the old bundle, requiring `ignoreCache: true` to pick up the new one), the notes rendered correctly.

### Second live test — verified (sid `014166e6-f124-4c62-aed5-9efda0819cc2`)

Query: _"What's the audience profile for RPM Steak?"_ with RPM Steak place context.

Visual confirmation (screenshot at `/tmp/live-narrate-WORKING.png`):

- "Working for 1m 19s" header above the wrapper.
- Collapsible "Working" wrapper with bouncing dots.
- **Narrative 1**: _"Pulling Google Places data for RPM Steak and identifying its key competitors."_ rendered as a paragraph above the first activity batch.
- Four Google Maps detail rows under it.
- **Narrative 2**: _"Investigating review demographics, guest sentiment, and social media positioning to build an audience profile for RPM Steak in Chicago."_ rendered between the Google Maps batch and the TripAdvisor/Google reviews batch.
- Six TripAdvisor + Google reviews detail rows under it.

Order: narratives appear strictly above their corresponding details. Prose is terse (≤25 words each), personalized (entity name + city + intent), in present-progressive form. Both narrates passed.

**Compliance on production: 2/2 narrates per turn (context_enricher + research_lead).** Phase 8 skipped — no fallback needed.

---

## Insights / learnings

- **Narrate-first compliance against `gemini-3.1-pro-preview` MEDIUM thinking is high.** 5/5 on the spike. The model treats a tool-call instruction as more binding than free-text narrate-before-tools instructions would be — exactly the hypothesis the plan was built on.
- **Two prose-instruction tweaks for Phase 3 wording.**
  1. "Exactly one `narrate` call per response, before any other tool calls" — query 5 overcalled narrate twice. The current wording says "the first tool call must be `narrate`" without a uniqueness clause.
  2. The "prefer present-progressive over self-reference" guidance is already in the plan but query 4 violated it ("I am dispatching..." instead of "Dispatching..."). Worth strengthening the wording — possibly with a positive example.
- **Counts on narrate-derived notes** — for the spike I emitted zeroed counts. The real Phase 1+2 implementation should pull live counts from accumulated state (the same `counts_snapshot()` shape the legacy notes used). Counts power the subline like "Searched 3 queries, Opened 2 sources" under the note text in `StreamingProgress`. If we drop counts entirely, the new `LiveActivity` should not render that subline.
- **`InMemoryRunner(app=...)` works fine for plugin propagation under AgentTool.** Same pattern as `evals/run_matrix.py:97-180` but with `InMemorySessionService` instead of `VertexAiSessionService`. Keeps the spike Firestore-free.
- **One transient 403 on a re-invocation** — running the agent twice back-to-back from the same Python process hit `PERMISSION_DENIED` on the second run's first Gemini call. Subsequent fresh-process spike runs all worked. Probably a token-cache hiccup; not a blocker.
- **Pre-existing ADK warnings** — every run prints "Tools at indices [N] are not compatible with automatic function calling (AFC)" for `google_search` and `fetch_web_content`. These are pre-existing and unrelated to narrate. Ignore.
- **Drip animation is dead, long live the narrative.** The typewriter $effect coupling between an external RAF callback and a `$state Record` either had a Svelte 5 reactivity gotcha or a deeper bug; either way, two debugging cycles (one local + autofixer-clean, one in production) didn't surface the root cause cheaply. Cutting the typewriter entirely shipped in 30 minutes and the narrative works fine without it. **Lesson:** if a "polish" feature blocks the core path, drop it on sight. Drip can come back as a separate iteration if real users miss it.
- **Service-worker / browser cache bit us in production debugging.** After deploying fix #1, Chrome MCP hit the cached bundle and showed the old broken behavior. `ignoreCache: true` on `navigate_page` (or hard-reload via DevTools) is required to verify a fresh deploy. Worth remembering for any future production-verify session.
- **Final aggregate diff vs `main` start (`358a12e`):** 6 commits, code is roughly net-flat (~+4 lines code, ~+170 LiveActivity-stack additions offset by ~−80 deletions in StreamingProgress + tests + the typewriter that we removed; backend −325 from notes/gear_run_state). Plan + log docs add ~600 lines, separately. The commit `06ac7e2` in the range was from a parallel session and not part of this work.
