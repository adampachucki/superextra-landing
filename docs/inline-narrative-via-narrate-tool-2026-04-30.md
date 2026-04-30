# Inline narrative via `narrate()` tool — implementation plan

**Date:** 2026-04-30 (revised same day after source-level review)
**Status:** Proposed. Pending Phase 0 spike before commitment.
**Owner:** Adam (PM) + agent platform.
**Related preview:** `src/routes/dev/progress-preview` (four UI variants), `src/lib/components/agent/{ProgressEventRow,ProgressWrapper}.svelte`.

This document captures the research, learnings, motivation, and concrete plan for replacing our current end-of-phase Gemini-Flash note generation with **inline LLM narrative driven by a model-callable `narrate(text)` no-op tool**, captured into the timeline at event-mapping time. The design pulls visual ideas from `willchen96/mike` (typed lifecycle events, collapsible "Working" wrapper, drip animation) and a structural idea from OpenAI's Codex chat surface (narrative-primary, activity-secondary). It produces personalized prose at the model's native turn cadence, eliminates the separate Gemini Flash note round-trip, and ships at roughly net-zero LOC against current `main` (further reduced if the preview route is deleted in Phase 9).

**Post-ship addendum (2026-04-30):** Phase 6's typewriter-drip animation on note paragraphs was cut during Phase 7 verification — see the execution log. The shipped `LiveActivity.svelte` renders `{ev.text}` directly. Drip can come back as a separate iteration if real users miss it.

**Revision note (same-day):** A first draft of this plan asserted that ADK serializes tool calls within a turn and that specialists run sequentially under `AgentTool`. Both are wrong against ADK 1.28 and our own orchestrator instructions:

- `agent/.venv/lib/python3.12/site-packages/google/adk/flows/llm_flows/functions.py:387-404` runs every function call in a single LLM response in parallel via `asyncio.create_task` + `asyncio.gather`.
- `instructions/research_lead.md:54` explicitly tells the orchestrator to "Dispatch in parallel — emit all tool calls in a single response so they execute concurrently." Specialists are AgentTools in research_lead's tool list (`agent.py:148-152`), so multiple specialists race.

This rewrite reflects the correct mechanism: capture `narrate` at event-mapping time (the function-call event is yielded _before_ tool execution, per `base_llm_flow.py:914-918`), don't side-effect from inside the tool, and keep frontend layout to a single chronological wrapper rather than per-phase grouped batches.

---

## How to use this document

If you're new to this thread, read in order:

1. **Part 1 — Motivation & context.** Why we're touching live-progress UX at all.
2. **Part 2 — Research journey.** The four hypotheses we tested, what we found about each, and the surprises that changed the design.
3. **Part 3 — Solution.** The `narrate(text)` tool design and why it beats the alternatives.
4. **Part 4 — Implementation plan.** Phase-by-phase, including the de-risking spike that gates everything else.
5. **Part 5 — Risk register.**
6. **Part 6 — Out of scope.**
7. **Part 7 — References.**

If you're a returning reader, skip to Part 4 for the phases.

---

## Part 1 — Motivation & context

### The UX problem

Our current live-progress UI (`src/lib/components/restaurants/StreamingProgress.svelte`, ~91 lines) groups timeline events by family ("Searching the web", "Google Maps", "TripAdvisor", "Google reviews", "Public sources", "Warnings") and renders them as flat lists with no per-event live state. Every detail row looks the same whether it's currently happening or finished an hour ago. The reader sees a static-feeling block that updates by accretion.

User feedback (Adam, 2026-04-30): the existing UI "feels dumb and clunky." Reference points the user wants us to draw from:

- **`willchen96/mike`** — an OSS legal-AI platform that ships a much livelier per-event lifecycle UI: spinner-to-dot status indicator per row, verb tense flips ("Reading X" → "Read X"), connector line linking activities, collapsible "Working / Completed in N steps" wrapper.
- **OpenAI Codex / ChatGPT Agent surface** — narrative-first design where the model emits short first-person prose between activity batches. The user's eye flows through prose; activity is supporting evidence underneath, expandable on demand.

### What "good" looks like

The Codex-style preview at `/dev/progress-preview` (Codex tab) shows the target: a "Working for 47s" header, then a one-paragraph narrative, then a collapsed activity batch summarizing what happened ("Found 2 venues, fetched 1,691 reviews across 2 platforms"), then another narrative, then the live activity batch streaming events. The narrative gives intent and pacing; the activity gives evidence.

### Constraints from the user

Quoted directly from the design conversation:

- "I want personalized prose mid-run."
- "Explore how to do it neatly — clean and fast."
- "We don't have time for 20-turn evals. We'll run faster simulation and spike."

So we need **personalized LLM-written narrative**, **clean code** (ideally net-negative), and **≤500ms perceived latency**, validated by a small spike rather than a formal eval harness.

---

## Part 2 — Research journey

We tested four hypotheses in order. Each shifted the design.

### Hypothesis A: Borrow mike's UX as-is, ship it on our existing event vocabulary

**What mike does** (`/tmp/mike-review/frontend/src/app/components/assistant/AssistantMessage.tsx:340-790`, `shared/PreResponseWrapper.tsx:1-74`):

- Server-Sent Events from Express → browser, framed as `data: {json}\n\n`.
- Typed event vocabulary: `tool_call_start`, `doc_read_start` → `doc_read`, `doc_find_start` → `doc_find`, `doc_created`, `doc_edited`, `reasoning_delta`, `content_delta`, `citations`.
- Per-event spinner ⇄ dot status indicator (`AssistantMessage.tsx:440-444` etc.) — same pattern repeated across every block component.
- Vertical connector line drawn between dots (`showConnector` predicate at `AssistantMessage.tsx:1203-1204`).
- Collapsible `<PreResponseWrapper>` that auto-minimizes once response text starts rendering, with a `hasMinimizedRef` latch to prevent re-opening.
- Drip animation in `useAssistantChat.ts:147-177` revealing 8 chars every 16ms from a buffered target — decouples typewriter rendering from network jitter.
- **Crucially: no narrative**. mike streams assistant text + tool events. There's no separate prose layer between activity batches.

**What we ported.** A first cut of mike's UI primitives is implemented in:

- `src/lib/components/agent/ProgressEventRow.svelte` (~48 lines) — spinner ⇄ dot row with optional connector.
- `src/lib/components/agent/ProgressWrapper.svelte` (~117 lines) — collapsible "Working / Completed in N steps" shell with sticky-minimize latch (Svelte 5 runes; the latch is in `everMinimized` $state with $effect-driven mutation).
- `src/routes/dev/progress-preview/+page.svelte` (~530 lines) — preview route with four variants (live run side-by-side with legacy; collapsed; Codex-style; error mid-run) gated by tabs so only one animates at a time.

**Conclusion.** Borrowing mike's UI is genuinely cheap: ~200 lines for the visual primitives. But mike doesn't help us with the Codex-style narrative layer — that's something we'd be adding from scratch.

### Hypothesis B: We already have narrative — just render it inline

**Surprise finding.** Our pipeline already emits notes at three milestones (`agent/superextra_agent/gear_run_state.py:152-207`), but only **one of the three** uses an LLM:

- `context_started` (line 159) → emits a deterministic note immediately, synchronous, no LLM.
- `research_started` (line 171) → emits a deterministic note immediately, synchronous, no LLM.
- `research_result_text` (line 184) → spawns `_emit_note_task` as an `asyncio.Task` that calls Gemini 2.5 Flash with an 8-second timeout (`notes.py:35` — bumped from 3s to 8s in commit `005ca78`). This is the only milestone with personalized prose.

Today's deterministic strings ("I'm checking the venue…", "I'm validating signals…", "I'm comparing evidence…") are the bland part of the existing UX; the personalized one (after a specialist returns its output_key) is what the user actually wants more of.

These notes write to the same Firestore timeline our `liveTimeline` listener reads (`src/lib/chat-state.svelte.ts:469-510`), and `StreamingProgress.svelte:53` already filters them. **The plumbing for inline notes exists.** What's missing is personalization at _every_ phase boundary, not just the post-specialist one.

**Why this isn't quite the answer.** Two costs:

1. **Latency, but only on the LLM-backed milestone.** The Gemini Flash call adds 1.5–3s typical, up to 8s worst-case for `research_result_text`. The other two milestones are 0ms. Switching all three to LLM-backed would multiply the latency problem.
2. **Timing coherence under parallel dispatch.** Specialists run in parallel (instructions/research_lead.md:54 + ADK's `asyncio.gather` at `functions.py:387-404`). Their detail events interleave in the timeline. A single post-specialist note can land before/after its corresponding details depending on Gemini Flash response time + Firestore jitter.

Net: keeping the separate Gemini call solves personalization for one milestone but not all three, and doesn't satisfy "≤500ms perceived latency."

### Hypothesis C: Drop the LLM, use richer deterministic templates

**The case for it.** Replace `_emit_note_task` and `_generate_timeline_note` with template strings that interpolate venue names, source counts, platform counts:

> `"Pulling Google reviews and TripAdvisor data for {venue1} and {venue2} from {source_count} sources so far."`

- Latency: 0ms (synchronous emission at milestone fire).
- Code: net **−50 lines** (deletes the LLM machinery).
- Quality: acceptable for phase-boundary "what I'm doing" lines. Loses language adaptation.

**Why we rejected this.** Adam: _"I want personalized prose mid-run."_ Templates can't match the conversational warmth of LLM-authored prose, especially when the input domain (restaurant intelligence) has a wide variety of legitimate query shapes that don't all fit a 3-template structure cleanly.

This option remains the clean fallback if Hypothesis D fails compliance.

### Hypothesis D: Capture the model's existing reasoning text as narrative

**The hypothesis.** ADK Events have `content.parts[]` where each part is text, function_call, or function_response. When an LLM produces text + tool calls in the same turn, both arrive as siblings in one Event. If our `firestore_events._collect_text` (line 419-425) walks all parts but is only invoked in router-final and research-final paths (lines 207, 231), we might be discarding usable reasoning prose mid-run. Capturing it would give us free personalized narrative at zero extra latency.

**Half-confirmed, operationally dead.** Investigation findings:

1. **Text + tool calls do share the same Event.** Confirmed by reading `firestore_events.py:124-175` (`map_event`) and `419-425` (`_collect_text`). The structure is there.
2. **But the model rarely produces useful text alongside tool calls.** Our orchestrator (`agent.py:154`) runs `gemini-3.1-pro-preview` with MEDIUM thinking; specialists run `gemini-3.1-pro-preview-customtools` with HIGH thinking (`specialists.py:77-86`). Under thinking-enabled function calling, Gemini internalizes reasoning in the reserved `thinking` part rather than volunteering narrative in the `text` part. Our existing instructions don't ask for narrative either.
3. **Free-text "narrate before tool calls" instructions are unreliable.** Compliance is observable but not guaranteed; in our case it's untested against 3.1 Pro Preview. Silent gaps in the timeline are the failure mode.

**The breakthrough idea — corrected.** Promote the narrative to a **callable tool**: `narrate(text: str)`. The model is instructed to invoke it as part of any response that calls research tools. Two important nuances against ADK 1.28:

- **Tool execution is parallel** (`functions.py:387-404`). We cannot rely on `narrate` "running first" by ordering it earlier in the function-call list — `asyncio.gather` runs them all concurrently.
- **The model-response event is yielded before any tool runs** (`base_llm_flow.py:914-918` — the function-call event is yielded at line 918, then the function-call execution loop starts at line 920). So we capture `narrate`'s `text` argument at _event-mapping_ time in `firestore_events.map_event`, not by side-effecting from inside the tool. The note lands in the Firestore timeline strictly before any specialist's tool-response events.

The "tool" is a no-op affordance for the schema — its only purpose is giving the model a typed slot to put its narrative into. The actual timeline write happens in `map_event`, which is already where every other timeline row gets built.

This is the path forward.

---

## Part 3 — Solution: `narrate(text)` tool

### Design — two pieces

**Piece 1: The `narrate(text)` tool is a no-op affordance.**

A new ADK tool, `narrate(text: str) -> dict`, registered on the orchestrator (`research_lead`) and the context enricher. The tool:

1. Takes a single string parameter (the one-sentence narrative).
2. Returns `{"acknowledged": True}` immediately. **It does not write to Firestore.** It does not access `TimelineWriter`. It is a typed slot for the model to put narrative into — nothing more.

Why no side effects: a side-effecting tool would need its own access to the active `TimelineWriter`, risk `seqInAttempt` collisions with the plugin's writes, and require defensive error handling around every Firestore call to keep the model's tool loop healthy on failure. The no-op design avoids all of that.

**Piece 2: The note is emitted from `firestore_events.map_event`.**

Add a branch to `map_event` (around line 146, where `_iter_function_calls` already runs):

```python
for idx, name, args in _iter_function_calls(event):
    if name == "narrate":
        text = _sanitize(args.get("text", ""))
        if text:
            mapping["timeline_events"].append({
                "kind": "note",
                "id": f"narrate:{_event_id(event)}:{idx}",
                "text": text,
                "noteSource": "llm",
                "counts": counts_snapshot(state),
            })
        continue  # don't try to map narrate as a detail event
    detail = _map_function_call(...)
```

This runs at event-mapping time, which `base_llm_flow.py:914-918` confirms happens _before_ the function-call execution loop starts at line 920. The note lands in the Firestore timeline with a `seqInAttempt` strictly earlier than any specialist's tool-response events that arrive afterward — even though the specialists themselves run in parallel.

**Piece 3: Instruction edits.**

Each agent's instruction adds a "Narrate first" directive:

> The first tool call in any response that calls tools must be `narrate(text)` with a one-sentence (≤25 words) statement, in the user's language, of what you're about to investigate and why. Reference specific entities (venue names, neighborhoods, timeframes) when known.

Applied to **`research_lead.md` and `context_enricher.md` only** for v1. Specialists are deliberately excluded (see Part 6 — Out of scope).

### Why this beats alternatives

| Approach                                                                                      | Perceived latency                                                                | Personalization                                   | Net code                                                                  | Risk                                                                                          |
| --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Hypothesis B (current) — separate Gemini Flash call                                           | 1.5–3s on `research_result_text` only; deterministic on the other two milestones | High on one milestone, low on the others          | unchanged                                                                 | Timing coherence + latency on one milestone                                                   |
| Hypothesis C — deterministic templates                                                        | 0ms                                                                              | Low (templated)                                   | **−50**                                                                   | None, but rejected on prose quality                                                           |
| Hypothesis D early-spawn — Gemini call at `context_started` instead of `research_result_text` | 200–500ms                                                                        | Medium (plan text only)                           | **+25**                                                                   | Two LLM calls per phase                                                                       |
| **`narrate(text)` tool + event-mapping capture (this plan)**                                  | **0ms (model's normal turn cadence)**                                            | **High (full state context, in user's language)** | **roughly net-zero shipped, ~−500 if preview route is deleted (Phase 9)** | **Compliance with the "narrate first" instruction is empirical — validated in Phase 0 spike** |

### Trade-offs

- **Compliance is the only open question.** Tool-call instructions are generally easier for models to comply with than free-text instructions, but rates vary by model and prompt. Our orchestrator runs `gemini-3.1-pro-preview` with MEDIUM thinking; this combination has not been benchmarked publicly for tool-first instructions. **Phase 0 spike measures this directly against our actual production model and prompt.** No literature-based compliance number is claimed in this plan.
- **The `narrate` tool is a no-op semantic.** A tool that does nothing-but-acknowledgement is unusual. ADK samples have analogous patterns (state-mutation tools, structured-output tools), so it's defensible, but worth noting in code review.
- **Drip animation makes single-write delivery feel live.** We don't need true token streaming; the existing `src/lib/typewriter.ts` (~80 lines, RAF-based, 4 chars/frame) reveals the note progressively after it lands.

### Frontend integration

The Firestore timeline already delivers `note` events to the frontend (`chat-state.svelte.ts:478-499` — deduplicated by `(runId, attempt, seqInAttempt)`, appended in arrival order). Layout for v1 is intentionally simple:

- **One chronological "Working" wrapper per turn**, using the new `<ProgressWrapper>` + `<ProgressEventRow>`.
- **Notes render inline within the wrapper**, in the order they arrived. A note appears as a paragraph row distinct from detail rows.
- **One `createTypewriter` instance per note**, keyed by note id, drip-reveals the text on first appearance.

No `phaseIndex` / `batchId` field is needed for v1. Specialists run in parallel and their detail events naturally interleave; trying to attribute each detail back to a specific narrative would require a per-specialist batch_id we don't have. The single-wrapper layout sidesteps this entirely. If user feedback later demands per-phase collapsible batches, we can revisit and add the grouping key — but it's explicitly out of scope here.

---

## Part 4 — Implementation plan

**Total scope: ~1 working day**, structured as a 60-minute structured spike that gates everything else, then six commits.

### Phase 0 — De-risking spike (~30 min, throwaway code)

Validate the actual ADK behavior we're betting on against our **production model** (`gemini-3.1-pro-preview` with MEDIUM thinking, not 2.5 Flash). Manual run + grep + screenshot — no harness, no pickled-event capture, no automated assertions. We're checking three facts in five queries; we don't need infrastructure for that.

**Setup:**

- Add a stub `narrate(text: str, tool_context: ToolContext)` tool that returns `{"acknowledged": True}` and `print()`s its arguments. No Firestore writes.
- Add an `if name == "narrate"` branch to `firestore_events.map_event` that emits a `note` timeline event (the real Phase 1+2 implementation, in throwaway form).
- Wire `narrate` into **only** the `research_lead` agent in `agent.py:148` (one line in the tools list).
- Add the "Narrate first" paragraph to `instructions/research_lead.md` (the Phase 3 wording, in throwaway form).

**Run 3–5 representative queries** locally via the agent venv (no Agent Engine redeploy needed):

1. "What's the steakhouse landscape in Chicago?"
2. "How does Maple & Ash position vs Bavette's?"
3. "Audience profile for a high-end sushi concept in NYC"
4. "Average ticket price for casual dining in Austin"
5. "Why are Italian places losing share in LA?"

**What to check, by hand:**

- **Compliance:** grep the run's Firestore timeline for `kind: "note"` entries with id starting `narrate:`. Count how many of the 5 turns produced one. Aim for ≥4/5.
- **Order:** glance at `seqInAttempt` in the same timeline — narrate notes should sort before their specialist tool-response details. Visual scan, not assertion.
- **Render:** open the new `LiveActivity` (or the preview route stub if not yet wired) in Chrome with the dev-server pointed at the local run; screenshot. Confirm narrative reads above details.
- **Prose:** read the 5 narratives. ≤25 words? User's language? Names entities? Terse, not robotic?

**Decision gate:**

- ≥4/5 queries pass all four checks → proceed to Phase 1.
- 3/5 → tune instruction wording in `research_lead.md` and rerun, max two iterations.
- After two tuning iterations still <4/5 → fall back to Hypothesis D early-spawn (separate Gemini call at `context_started`, ~25 lines, deterministic fallback). Document the decision in a follow-up file. **Do not** attempt `before_agent_callback` enforcement; it can't see model output (see Phase 8 note below).

This spike is throwaway. Don't commit. ~10 lines of disposable code.

### Phase 1 — Tool definition (1 commit, ~15 lines)

Create `agent/superextra_agent/narrate_tool.py` (new file):

- `async def narrate(text: str, tool_context: ToolContext) -> dict[str, bool]:`
- `return {"acknowledged": True}`
- That's it. No Firestore, no state mutation, no logging beyond `log.debug`.
- ADK auto-wraps Python functions assigned to an agent's `tools=` list as `FunctionTool` objects.

Add a brief module docstring explaining that the actual note emission happens in `firestore_events.map_event` — this is the typed slot the model uses to put narrative into.

### Phase 2 — Event mapping (1 commit, ~10 lines)

Add a branch in `agent/superextra_agent/firestore_events.py:map_event`, around line 146 (where `_iter_function_calls` already iterates):

```python
for idx, name, args in _iter_function_calls(event):
    if name == "narrate":
        text = _sanitize_narrate_text(args.get("text", ""))
        if text:
            detail_events.append({
                "kind": "note",
                "id": f"narrate:{_event_id(event)}:{idx}",
                "text": text,
                "noteSource": "llm",
                "counts": _counts_snapshot(state),
            })
        continue
    detail = _map_function_call(...)
```

`_sanitize_narrate_text` is three lines: `isinstance(text, str)` check, `text.strip()`, return. No length cap — the instruction prompt already bounds output to ≤25 words, and a runaway-length narrative is a Phase 3 instruction-tuning signal, not a rendering bug. Counts come from existing state via the same helper that `_maybe_emit_notes` uses today.

Unit tests in `agent/tests/test_firestore_events.py`: synthetic Event with a `narrate` function-call → asserts a `note` timeline event with the right text, id, and counts. Synthetic Event with no narrate but a specialist call → no note emitted (sets up the Phase 7 fallback test case).

### Phase 3 — Instruction edits (1 commit, ~20 lines across 2 files)

Following `instructions/AUTHORING.md` conventions:

- `instructions/research_lead.md` — add narrate-first directive near the "Dispatch in parallel" rule (line 54), since the same response can include both `narrate` and the specialist calls.
- `instructions/context_enricher.md` — same directive, since context_enricher also calls tools (Places lookups).

**Specialists are deliberately not edited.** Their narratives would interleave under parallel dispatch and we'd need a `batch_id` to attribute them — out of scope for v1.

Wording to start from:

> **Narrate first.** The first tool call in any response that calls tools must be `narrate(text)` with a one-sentence (≤25 words) statement, in the user's language, of what you're about to investigate and why. Reference specific entities (venue names, neighborhoods, timeframes) when known. Prefer present-progressive ("Pulling Google reviews for Maple & Ash and Bavette's now") over self-reference ("I'm going to check Google reviews").

Two-pass iteration: write it, run the spike queries again to confirm the prose stays terse and useful.

### Phase 4 — Wire `narrate` into the toolset (1 commit, ~5 lines)

- Add `narrate` to `research_lead`'s `tools=[...]` list in `agent.py:148`.
- Add to `context_enricher`'s tools (look for `_make_enricher()` and the surrounding agent definition).
- Run `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`.

### Phase 5 — Delete the old note machinery entirely (1 commit, ~−110 lines net)

- Delete `_emit_note_task`, `_generate_timeline_note`, and the surrounding LLM-call helpers from `notes.py:154-221`.
- Delete `_maybe_emit_notes` from `gear_run_state.py:152-207` in full — including the `context_started` and `research_started` deterministic branches. They are not actually load-bearing fallbacks: if narrate compliance is uneven we have Phase 8 (`map_event`-time fallback) and the further fall-back to Hypothesis D early-spawn. Keeping the deterministic branches alongside narrate would leave dead code and confuse the next reader.
- Delete the `_capture_final` calls and any `note_tasks` infrastructure tied only to LLM note generation. Spot-check that the deterministic title-generation path in `notes.py` is independent (it is — different model, different code path).
- Delete the `research_result_text` milestone field from `firestore_events.map_event` if no other code reads it (`grep` first).
- Delete `NOTE_TIMEOUT_S` and `NOTE_MODEL` from `notes.py:32, 35` once `_emit_note_task` is gone. (`TITLE_MODEL` and `TITLE_TIMEOUT_S` stay — title generation is unrelated.)
- Run `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` — fix any test that imported the deleted symbols.

### Phase 6 — Frontend rewire (1 commit, ~60 lines)

- Replace the `<StreamingProgress />` block in `src/lib/components/restaurants/ChatThread.svelte:277-298` with a new `<LiveActivity />` component using `<ProgressWrapper>` + `<ProgressEventRow>`.
- **Render `chatState.liveTimeline` chronologically inside one wrapper.** Note events render as paragraph rows; detail events render as `<ProgressEventRow>`. No splitting, no per-batch grouping.
- Wire the existing `createTypewriter` from `src/lib/typewriter.ts` to drip-render each note on first appearance (one typewriter instance per note, keyed by note id, to avoid the second note overwriting the first mid-drip).
- Delete `StreamingProgress.svelte` once nothing references it.

### Phase 7 — Deploy + live verification (1 hour, no code)

- Cloud Functions auto-deploy on `main` push (per `.github/workflows/deploy.yml`).
- Manually redeploy Agent Engine via the wrapper from commit `dbf23f7` (`agent_engines.update(...)` from the agent venv).
- Re-run the same 5 spike queries against production via `agent.superextra.ai/chat`.
- Watch Firestore for narrate event arrival timing + Chrome MCP screenshot the rendered UI.
- **Pass criteria:** narrate fires on ≥80% of orchestrator and context-enricher tool-calling turns, prose is useful and terse, narrative is visibly above its corresponding specialist details.

### Phase 8 — Map-time fallback (conditional, ~10 lines)

Only if Phase 7 shows narrate misses >20% of orchestrator turns:

Add a fallback branch in `firestore_events.map_event`: when a function-call event from `research_lead` contains specialist tool names but no `narrate` call, synthesize a deterministic note from the specialist names. e.g. _"Dispatching guest_intelligence and review_analyst now."_ The note kind is the same (`kind: "note"`, `noteSource: "deterministic"`).

This is the only fallback path the plan ships with; Phase 5 deleted the old deterministic-milestone branches. The `before_agent_callback` location is wrong — it runs before the model produces output (`agent/.venv/lib/python3.12/site-packages/google/adk/plugins/base_plugin.py:198-215`) so it cannot react to the model omitting `narrate`. Returning `Content` from it bypasses the agent entirely.

### Phase 9 — Cleanup (1 commit)

- **Delete `/dev/progress-preview` route** (`src/routes/dev/progress-preview/+page.svelte`, ~530 lines). Its purpose was to validate the design visually during this conversation; the screenshots are persisted in chat and the design rationale is in this doc. Keeping the route as a permanent dev surface is +530 lines of UI scaffolding for ~zero ongoing value. The `<ProgressEventRow>` and `<ProgressWrapper>` components stay because `<LiveActivity>` uses them.
- `npm run lint && npm run check && npm run test && cd functions && npm test`.
- PR title: `feat(agent): inline narrative via narrate() tool, replace separate Gemini note call`.

---

## Part 5 — Risk register

1. **Compliance <80% with the "narrate first" instruction** — Phase 0 catches this before we commit, against the actual production model (`gemini-3.1-pro-preview` MEDIUM thinking). If Phase 7 catches it after deploy, Phase 8 fallback in `map_event` is ~10 lines. Worst case is fall back to Hypothesis D early-spawn (separate Gemini call at `context_started`), which is a known-good pattern.
2. **Narrate prose too long, robotic, or off-tone** — instruction iteration in Phase 3 is the lever. Budget two passes during the spike.
3. **Token cost** — narrate adds ~30 input + ~25 output tokens per orchestrator turn × ~3–4 turns/run = ~200 tokens/run, sub-cent at 3.1 Pro Preview rates. Ignore.
4. **Parallel specialist dispatch interleaves details** — confirmed via `instructions/research_lead.md:54` and `agent/.venv/.../google/adk/flows/llm_flows/functions.py:387-404` (`asyncio.gather`). For v1 we accept interleaving and render everything in one chronological wrapper. If user feedback later demands per-phase grouped batches, we add a `batch_id` field; explicit out-of-scope here.
5. **`map_event` event-mapping ordering** — depends on `base_llm_flow.py:914-918` yielding the function-call event before the function-call execution loop. This is current ADK 1.28 behavior. If a future ADK release changes it, we'd need to revisit; document as an assumption in the PR.
6. **Drip animation across multiple notes** — each note needs its own `Typewriter` instance to avoid the second note overwriting the first mid-drip. Handled by keying on note id in Phase 6.
7. **Model-name surface area** — orchestrator and specialists run different model variants (`gemini-3.1-pro-preview` and `gemini-3.1-pro-preview-customtools`). Compliance tested in Phase 0 is on the orchestrator only (where narrate is registered for v1). Not extending to specialists in this iteration is deliberate.

---

## Part 6 — Out of scope

- **Per-specialist narrate.** Adding `narrate` to `specialist_base.md` would multiply the prompt-engineering surface and produce interleaved notes from parallel specialists with no reliable way to attribute each note to its specialist's detail events. Defer to v2 if user feedback demands per-phase narratives, with a `batch_id` design.
- **Codex-style per-phase collapsible batches.** The preview at `/dev/progress-preview` shows this layout; v1 ships the simpler "one chronological Working wrapper with notes inline" instead, because parallel dispatch makes the per-phase grouping unattributable without the `batch_id` field. Revisit if v1's flat layout proves insufficient.
- **`before_agent_callback` enforcement of narrate.** `before_agent_callback` runs before the model produces output (`base_plugin.py:198-215`); it cannot detect that the model omitted narrate. Fallback lives in `map_event` (Phase 8) instead.
- **Token-by-token streaming of narrate output.** Tool-call argument capture is atomic at event-mapping time. Drip animation handles perceived speed. Real streaming is a separate feature, not needed for this iteration.
- **Multi-language i18n templates.** The orchestrator already replies in the user's language; narrate inherits this automatically.
- **Replacing the legacy `TurnSummary` end-of-run rollup.** The summary at the end of a turn (`StreamingProgress` "Worked for Xs" footer) is independent. Keep as-is.
- **Mike-style tool-specific event types** (`doc_read_start`, etc.) at the backend level. Our event vocabulary stays domain-specific (`note`, `detail` with `family`, `drafting`). The spinner ⇄ dot indicator is purely a frontend render of existing `kind` + arrival timing.

---

## Part 7 — References

### External — observed reference projects

- **`willchen96/mike`** — OSS legal AI platform. Cloned at `/tmp/mike-review` during research.
  - Lifecycle event taxonomy: `frontend/src/app/components/assistant/AssistantMessage.tsx:340-790`
  - `PreResponseWrapper`: `frontend/src/app/components/shared/PreResponseWrapper.tsx:1-74`
  - SSE streaming consumer with drip: `frontend/src/app/hooks/useAssistantChat.ts:147-177`
  - Backend SSE emit: `backend/src/lib/chatTools.ts:2341-2583`
  - **Key takeaway:** the per-event spinner ⇄ dot indicator and verb-tense flips are doing the bulk of the perceived liveness. Connector line and collapsible wrapper are polish.

- **OpenAI Codex / ChatGPT Agent surface** — observed via screenshot from the user.
  - Pattern: narrative paragraph, then collapsed activity batch ("Explored 2 files, ran 1 command"), then narrative paragraph, then collapsed batch ("Explored 5 files >"), then live current activity.
  - **Key takeaway:** narrative is primary content; activity is supporting evidence underneath, expandable on demand.

### External — official documentation

- **ADK index:** `https://adk.dev/llms.txt` — top-level table of contents. Follow links for specific concepts.
- **ADK samples:** `https://github.com/google/adk-samples` — canonical patterns. Worth grepping for no-op tool affordances analogous to `narrate`.
- **ADK Python source:** `https://github.com/google/adk-python` — reference for `Event`, `Part`, `ToolContext`, `before_agent_callback` signatures.
- **ADK plugin authoring** — already followed in `agent/superextra_agent/firestore_progress.py`.

### Internal — ADK 1.28 source anchors (vendored in `agent/.venv`)

These are the load-bearing claims in this plan. If the ADK version changes, re-verify.

- `google/adk/flows/llm_flows/functions.py:387-404` — function calls execute in **parallel** via `asyncio.create_task` + `asyncio.gather`. Defeats any "first tool runs first" assumption.
- `google/adk/flows/llm_flows/base_llm_flow.py:914-918` — the model_response_event (containing function-call parts) is yielded **before** the function-call execution loop starts at line 920+. This is what makes event-mapping capture work for `narrate` ordering.
- `google/adk/plugins/base_plugin.py:198-215` — `before_agent_callback` runs before the agent; returning Content bypasses the agent. Confirms it cannot react to model output, so it is _not_ a viable narrate-fallback location.

### Internal — codebase anchors (current line numbers)

**Backend (Python, `agent/superextra_agent/`):**

- `agent.py:35` — `_FAST_MODEL = _make_gemini("gemini-2.5-flash", force_global=True)` (used by notes; not the orchestrator)
- `agent.py:143-156` — `research_lead` definition (where `narrate` gets added in Phase 4)
- `agent.py:160-164` — `research_pipeline` SequentialAgent (sequential ordering applies between context_enricher and research_lead, NOT among parallel tool calls within a turn)
- `specialists.py:77-92` — model selection: `gemini-3.1-pro-preview` for orchestrator, `gemini-3.1-pro-preview-customtools` for specialists, with HIGH/MEDIUM thinking configs
- `notes.py:31-32` — `TITLE_MODEL` and `NOTE_MODEL` default to `gemini-2.5-flash` (kept for title generation; note generation is removed in Phase 5)
- `notes.py:35` — `NOTE_TIMEOUT_S = 8.0` (target for deletion in Phase 5)
- `notes.py:154-221` — `_emit_note_task` and `_generate_timeline_note` (target for deletion in Phase 5)
- `gear_run_state.py:152-207` — `_maybe_emit_notes`. Of the three milestone branches: line 159 (`context_started`) and line 171 (`research_started`) emit deterministic notes synchronously and are kept as fallback; line 184 (`research_result_text`) spawns the LLM task and is the deletion target.
- `firestore_events.py:124-175` — `map_event`. The new narrate branch goes around line 146 where `_iter_function_calls` already runs.
- `firestore_events.py:158-167` — milestone setting (`context_started`, `research_started`, `research_result_text`)
- `firestore_events.py:419-425` — `_collect_text` (used in router-final and research-final paths only)
- `firestore_progress.py:435-498` — `on_event_callback` (where the plugin sees per-event Firestore writes)
- `instructions/AUTHORING.md` — guidance for editing instructions
- `instructions/research_lead.md:54` — "Dispatch in parallel" rule. Narrate-first directive added near here in Phase 3.
- `instructions/context_enricher.md` — narrate-first directive added in Phase 3
- `instructions/specialist_base.md` — **NOT edited** in v1 (see Part 6)
- `specialists.py`, `specialist_catalog.py` — specialist registration. Not modified in v1.

**Frontend (Svelte, `src/`):**

- `lib/chat-types.ts:40-68` — `TimelineEvent` discriminated union (`note`, `detail`, `drafting`)
- `lib/chat-state.svelte.ts:469-510` — `liveTimeline` `onSnapshot` listener and dedup logic
- `lib/components/restaurants/StreamingProgress.svelte:52-90` — current note rendering (target for replacement in Phase 5)
- `lib/components/restaurants/ChatThread.svelte:277-298` — where `<StreamingProgress />` is mounted (target for rewire in Phase 5)
- `lib/components/agent/ProgressEventRow.svelte` — new (already built in preview)
- `lib/components/agent/ProgressWrapper.svelte` — new (already built in preview)
- `lib/typewriter.ts:1-82` — RAF-based drip utility, used in Phase 5

**Preview (delete in Phase 8):**

- `routes/dev/progress-preview/+page.svelte` — four-variant tabbed preview (Live / Collapsed / Codex / Error)

### Internal — related plans and prior decisions

- `docs/conversation-quality-plan-2026-04-28.md` — voice + state hygiene + ack pipeline. Note: `firestore_events.py:163-164` already captures the orchestrator's plan output as a timeline event; that work overlaps with this plan and may simplify the `narrate` capture path further once shipped.
- `docs/agent-routing-collapse-plan-2026-04-29.md` — recent routing rearchitecture, relevant for understanding `research_lead` → specialists wiring.
- `docs/adk-progress-plugin-options-2026-04-28.md` — earlier exploration of progress plugin options.
- `docs/gear-migration-implementation-plan-2026-04-26.md` — Vertex Agent Engine migration. The `agent_engines.update(...)` redeploy wrapper landed in commit `dbf23f7`.

### Commits referenced in this plan

- `005ca78` (2026-04-23) — bumped `NOTE_TIMEOUT_S` from 3s to 8s after production tail-latency failures. To be reverted as part of Phase 4 deletion.
- `a313b50` — research pipeline migration to AgentTool-wrapped specialists; established sequential dispatch under AgentTool.
- `dbf23f7` — `agent_engines.update(...)` redeploy wrapper, used in Phase 6.
- `c9ce679` (2026-04-24) — UI footer fix from the conversation-quality work; unrelated but referenced for timeline.

---

## Glossary

- **ADK** — Google's Agent Development Kit. Python framework for building tool-using LLM agents. Provides `Event`, `Part`, `ToolContext`, `before_agent_callback`, `AgentTool`.
- **Agent Engine** — Vertex AI Agent Engine Reasoning Engine. Where our agent code is hosted; redeploy via `agent_engines.update(...)`.
- **Codex pattern** — Narrative-first chat surface where LLM-written prose is the primary content and tool activity is supporting evidence underneath. Observed in OpenAI's Codex / ChatGPT Agent.
- **Drip / typewriter** — Frontend rendering technique where text is revealed progressively character-by-character on a fixed cadence, decoupled from network arrival timing. Implemented in `src/lib/typewriter.ts`.
- **Lifecycle event** — Pair of events bracketing a tool's execution (`X_start`, `X` final). mike's pattern. We don't emit these explicitly; we infer state from arrival ordering.
- **Note** — A `TimelineEvent` of `kind: 'note'` rendered as conversational prose inline within the activity wrapper. Today: deterministic notes for `context_started` and `research_started` milestones (synchronous, no LLM); LLM-backed note for `research_result_text` (Gemini 2.5 Flash via `_emit_note_task`). After this plan: notes are extracted from `narrate(text)` function-call arguments at event-mapping time in `firestore_events.map_event`. The `_emit_note_task` LLM path is removed; the two deterministic notes remain as fallback if narrate compliance is uneven.
- **`PreResponseWrapper`** — mike's collapsible "Working / Completed in N steps" shell. Reimplemented in our codebase as `ProgressWrapper.svelte`.
- **Progress preview** — `/dev/progress-preview` route with four variants demonstrating the new components in isolation.
- **Spike** — Throwaway exploratory implementation to validate a design assumption before committing to a full build. In this plan: Phase 0.
