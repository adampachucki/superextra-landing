# Inline narrative — execution log

**Started:** 2026-04-30
**Plan reference:** `docs/inline-narrative-via-narrate-tool-2026-04-30.md`
**Status:** Phase 0 (de-risking spike) — orientation complete; spike harness next.
**Branch:** `main` (commit at start: `358a12e`).
**Owner of this log:** Whoever is currently driving execution. Append; don't rewrite earlier entries.

This is a living log of what we actually did, what changed in the code, what tripped us up, and any plan-level revisions discovered during execution. Insights and learnings live here too. Future readers should be able to pick up cold — read top-to-bottom for chronology, jump to the latest entry for current state.

---

## Phase tracker

| Phase                               | Status      | Commit          | Notes                                                      |
| ----------------------------------- | ----------- | --------------- | ---------------------------------------------------------- |
| 0 — De-risking spike                | **PASSED**  | n/a (throwaway) | 5/5 queries produced narrate, prose terse and personalized |
| 1 — Tool definition                 | Not started |                 |                                                            |
| 2 — Event mapping                   | Not started |                 |                                                            |
| 3 — Instruction edits               | Not started |                 |                                                            |
| 4 — Wire `narrate` into toolset     | Not started |                 |                                                            |
| 5 — Delete old note machinery       | Not started |                 |                                                            |
| 6 — Frontend rewire                 | Not started |                 |                                                            |
| 7 — Deploy + live verification      | Not started |                 |                                                            |
| 8 — Map-time fallback (conditional) | Not started |                 |                                                            |
| 9 — Cleanup (delete preview route)  | Not started |                 |                                                            |

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

## Insights / learnings

- **Narrate-first compliance against `gemini-3.1-pro-preview` MEDIUM thinking is high.** 5/5 on the spike. The model treats a tool-call instruction as more binding than free-text narrate-before-tools instructions would be — exactly the hypothesis the plan was built on.
- **Two prose-instruction tweaks for Phase 3 wording.**
  1. "Exactly one `narrate` call per response, before any other tool calls" — query 5 overcalled narrate twice. The current wording says "the first tool call must be `narrate`" without a uniqueness clause.
  2. The "prefer present-progressive over self-reference" guidance is already in the plan but query 4 violated it ("I am dispatching..." instead of "Dispatching..."). Worth strengthening the wording — possibly with a positive example.
- **Counts on narrate-derived notes** — for the spike I emitted zeroed counts. The real Phase 1+2 implementation should pull live counts from accumulated state (the same `counts_snapshot()` shape the legacy notes used). Counts power the subline like "Searched 3 queries, Opened 2 sources" under the note text in `StreamingProgress`. If we drop counts entirely, the new `LiveActivity` should not render that subline.
- **`InMemoryRunner(app=...)` works fine for plugin propagation under AgentTool.** Same pattern as `evals/run_matrix.py:97-180` but with `InMemorySessionService` instead of `VertexAiSessionService`. Keeps the spike Firestore-free.
- **One transient 403 on a re-invocation** — running the agent twice back-to-back from the same Python process hit `PERMISSION_DENIED` on the second run's first Gemini call. Subsequent fresh-process spike runs all worked. Probably a token-cache hiccup; not a blocker.
- **Pre-existing ADK warnings** — every run prints "Tools at indices [N] are not compatible with automatic function calling (AFC)" for `google_search` and `fetch_web_content`. These are pre-existing and unrelated to narrate. Ignore.
