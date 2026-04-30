# Agent routing — collapse to lead-as-synthesizer + drop floors

**Date:** 2026-04-29
**Owner:** Adam (PM); execution: Claude
**Status:** Implemented and deployed 2026-04-30
**Predecessors:**

- `docs/agent-routing-rearchitecture-deploy-log-2026-04-29.md` — AgentTool migration shipped 2026-04-29 (commit `a313b50`).
- `docs/agent-routing-floors-handoff-2026-04-29.md` — earlier deferred-floors handoff (now folded into this plan).

## Goal

Collapse the research pipeline from four steps to two, aligning with the
canonical lead-agent-as-synthesizer pattern in Anthropic's Research
multi-agent system and Google ADK's `academic-research` sample. Concretely:

- **Drop the dedicated Synthesizer agent.** The lead orchestrator emits the
  user-facing report directly from its tool-response history. No
  separate state read + re-LLM step.
- **Drop the Gap Researcher agent.** Coverage self-checking and
  failure-recovery move into the lead's iterative-dispatch loop.
- **Remove the five query-type-coverage floors** from the orchestrator
  prompt. Replace them with evidence-surface coverage planning plus
  richer specialist descriptions. The replacement is scalable because
  it asks what evidence the question needs, not which hard-coded query
  bucket the wording resembles.

Target pipeline:

```
Router → SequentialAgent[Enricher, ResearchLead] → follow_up
```

Four pipeline steps become two. Aligned with Google ADK's
`academic-research` sample shape: single LlmAgent coordinator that
plans + dispatches + iterates + emits final.

## Constraints (from Adam, 2026-04-29)

1. **Lean and clean.** Simple over comprehensive. Pragmatic over
   defensive.
2. **Speed.** No extensive eval cycles. Minimal pre-merge gates. Ship
   and monitor.
3. **OK to drop functionality** during transition rather than
   maintaining backward-compat shims for old behavior.
4. **Complete and reliable, not bulletproof.** We accept that some
   edge-case behaviors get simplified or dropped. We can re-add later
   if production traffic surfaces a real need.
5. **Identify complications and discuss them up front** — but the
   answer to most should be "simplify, ship, polish later."

## Research summary

Delegated external research; full report in this session's history.
Citations baked into each claim below.

**Anthropic Research multi-agent system**
([anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)):
the lead agent owns plan + dispatch + iteration decision + intermediate
synthesis. There is **no separate auditor or critic**: "The
LeadResearcher synthesizes these results and decides whether more
research is needed — if so, it can create additional subagents or
refine its strategy." Anthropic's only post-lead agent is a
`CitationAgent` for citation post-processing; we don't have a citation
schema, so we don't need that.

**Google ADK official guidance**
([adk.dev/agents/multi-agents](https://adk.dev/agents/multi-agents/)):
both LLM-driven delegation and explicit `AgentTool` invocation are
first-class. ADK's own framing depends on clear specialist
descriptions, appropriate coordinator instructions, and choosing the
workflow shape that fits the use case. That supports our direction:
one coordinator lead with `AgentTool` specialists, not a separate
synth pass maintained only for defensive fallback behavior.

**ADK samples — the deciding signal:**

- **`academic-research`** ([adk-samples](https://github.com/google/adk-samples/tree/main/python/agents/academic-research)):
  single `academic_coordinator` LlmAgent with specialists wrapped as
  `AgentTool`. Coordinator emits the final response itself. **No
  synthesizer.** This is our target shape.
- **`deep-search`** ([adk-samples](https://github.com/google/adk-samples/tree/main/python/agents/deep-search)):
  keeps a dedicated `research_evaluator` critic AND a dedicated
  `report_composer_with_citations`. The composer earns its keep
  because it consumes a _structured outline_ (`report_sections`) and a
  citation tag system. **We don't have those structures, so the analog
  doesn't apply.**

**LangGraph supervisor**
([langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py)):
supervisor is the synthesizer by default. Library ships
`create_forward_message_tool` specifically to avoid "potential
misrepresentation of the worker's response through paraphrasing." The
canonical anti-pattern is _unnecessary re-synthesis_ — exactly what
our current Synthesizer step does.

**Verdict from research:** for our setup (8 specialists, single
user-facing report, no structured citation schema), the
`academic-research` shape is the right collapse target. Our current
Synthesizer step is the LangGraph paraphrase-loss anti-pattern: it
re-LLMs content the lead already has in tool-response context.

## Target architecture

### Pipeline

```
Router (LlmAgent, sub_agents=[research_pipeline, follow_up])
└── research_pipeline (SequentialAgent, 2 steps)
    ├── Enricher (LlmAgent, fetches Places data → places_context)
    └── ResearchLead (LlmAgent, AgentTool specialists → emits final_report directly)
```

### State keys (after the change)

| Key                                                 | Written by                                         | Read by                                                                                  | Status                                                                                    |
| --------------------------------------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `places_context`                                    | Enricher                                           | ResearchLead, specialists, follow_up                                                     | unchanged                                                                                 |
| `_target_lat`, `_target_lng`, `_target_place_id`    | Enricher                                           | specialists (via geo bias)                                                               | unchanged                                                                                 |
| `pricing_result`, `marketing_result`, etc. (8 keys) | Specialists (state_delta forwarding via AgentTool) | ResearchLead's tool-response context during the same run; follow_up only if needed later | unchanged                                                                                 |
| `final_report`                                      | ResearchLead                                       | follow_up, frontend                                                                      | **moved** from Synthesizer to ResearchLead                                                |
| `final_report_followup`                             | follow_up                                          | nothing (terminal)                                                                       | unchanged                                                                                 |
| `research_plan`                                     | nobody                                             | nobody                                                                                   | **DROPPED** (was orchestrator → synth + gap + follow_up; nothing reads it after collapse) |
| `gap_research_result`                               | nobody                                             | nobody                                                                                   | **DROPPED** (gap researcher gone)                                                         |
| `_drafting_started`                                 | nobody                                             | nobody                                                                                   | **DROPPED** (was a synth lifecycle marker that fed frontend typewriter polish)            |

### ResearchLead prompt shape

The orchestrator's current 118-line prompt is the starting point.
Modifications:

- **Drop floors entirely** (lines 78-100). Replace with
  evidence-surface coverage planning plus the description-driven
  principles already at lines 33-35.
- **Absorb synth's job** by adding sections on:
  - Output format (executive summary, structured headings by insight theme not specialist name, premise-assessment translation, follow-up questions).
  - Chart syntax (the existing `chart` fenced-block JSON schema from `synthesizer.md:42-56`).
  - Depth preservation (the "thorough briefing, not executive summary" rule).
- **Reframe step 11** ("Summarize the plan") to be the **final report**: the lead's last message after all tool calls return is now the user-facing report, not a separate plan summary.
- **Keep and sharpen step 8** as pre-dispatch evidence-surface
  coverage planning. Merge the post-dispatch sufficiency check with
  step 10's iterative dispatch loop.

Final prompt size estimate: ~140-160 lines (current 118 - 25 floors - 15 dup + 30 synth + 10 chart + 5 polish). Manageable.

### Floor replacement — evidence-surface coverage planning + rich descriptions

The eval (Variant B vs A) showed that **rich descriptions alone don't
match floors** (10/12 Gemini, 11/12 Opus). Floors aren't replaced by
descriptions alone. They are replaced by **descriptions plus a
structured pre-dispatch evidence-coverage check**. This keeps the
lead in control, aligns with ADK's coordinator-plus-`AgentTool`
pattern, and matches the cheap, high-signal step the current prompt
already has in the current research-lead prompt.

**The check sharpens to a structured form:**

> Before emitting any tool calls, identify the evidence surfaces needed
> to answer the question: live operating signals, menu/pricing data,
> customer voice, review trajectory, social/search/ad positioning,
> local market context, labor/economics, and location/trade-area
> dynamics. For each material surface, name the specialist whose
> description uniquely covers it. If a material surface has no covering
> specialist, either add one or assign it to `dynamic_researcher_1`
> with a focused brief that names the surface. Do not skip this step.

This generalizes to phrasings the floor matrix wouldn't anticipate,
because it operates on the evidence the question requires, not the
phrasing of the question. That's the scalable replacement Adam asked
for. ADK's `deep-search` sample uses a heavier variant (a separate
`research_evaluator` LlmAgent with a `Feedback` Pydantic schema in a
LoopAgent). That is not the right default for our 8-specialist,
single-report shape.

**Apply targeted description fixes** that the eval surfaced (per
floors-handoff doc):

- **`review_analyst`** — add closure-detection role (review-velocity
  flatlines, defensive owner-responses).
- **`marketing_digital`** — add price-positioning signal (promo
  frequency, value-prop messaging).
- **`dynamic_researcher_1`** — add explicit pair-with-`operations`
  rationale for wage/labor.
- **`menu_pricing`** — verify currently-operating signal via delivery
  platforms is present.

Descriptions tell the lead _what each specialist surfaces_; the
pre-dispatch check forces the lead to commit to material coverage
before spending compute. The post-tool sufficiency check then asks
whether any material surface is still weak and triggers one focused
extra round only when needed. Together they replace floors. Without
re-running the eval, this is the bet.

## What we drop (and what we lose)

Per Adam's "OK to simplify functionality for the time being":

| Dropped                                | What we lose                                                                                                                                                                                                     | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Synthesizer agent                      | Re-LLM pass that could clean up rough orchestrator output                                                                                                                                                        | Anti-pattern per LangGraph; lead has the data in tool-responses already                                                                                                                                                                                                                                                                                                                                                                                              |
| **Synth fallback callback entirely**   | Deterministic stitch from specialist outputs when the model returns empty content. Without it, an empty lead response should fail loudly as `empty_or_malformed_reply`, not produce a stitched synthetic report. | Per Adam's "lean and clean — drop functionality if it complicates." Empty model responses are rare in production (we haven't seen one in the deploy log smokes). Keep the terminal sanity gate and fix the root cause if production traffic surfaces this as a real failure mode.                                                                                                                                                                                    |
| Gap researcher agent                   | Phase-2 fallback that fires when a called specialist errored ("Research unavailable: X")                                                                                                                         | Lead can see the same error in the tool_response and call again with a focused brief or use `dynamic_researcher_1`. Iterative dispatch covers this role.                                                                                                                                                                                                                                                                                                             |
| `research_plan` state key              | Orchestrator's structured plan summary (core question, premise audit, competitive set, specialists called)                                                                                                       | Follow-up agent currently reads this for context. After collapse, follow-up reads only `final_report` — which contains all the same information narratively. Lose: the structured form. Gain: one fewer state key, one fewer prompt template variable.                                                                                                                                                                                                               |
| Floors (5 query-type-coverage rules)   | Hard guarantee that specific queries dispatch a minimum specialist set                                                                                                                                           | Replaced by **rich descriptions + evidence-surface coverage planning** (see "Floor replacement" section above). Eval showed B-without-floors-or-coverage-check lost 11-1; this plan ships **B + targeted description fixes + sharpened coverage check**, which is the scalable replacement. If quality regresses in production observation, first sharpen descriptions and coverage wording. Re-add floors only as an emergency hotfix.                              |
| `_drafting_started` state marker       | Frontend's typewriter-effect gating (read by `firestore_events.py:175`, mapped to a `drafting` event consumed by `src/lib/chat-state.svelte.ts:401`)                                                             | **Intentional UI simplification per Adam's "OK to limit UI scope."** The typewriter effect is polish, not function. Reports will appear when the lead's response completes, without the typewriter staging. If the UX regression is unacceptable in production, re-add by emitting an explicit drafting event from the lead's `before_model_callback` on its first turn after dispatch — but keep the marker out of `state.state_delta` so it doesn't pollute state. |
| Tests for synth + gap + floor variants | ~30 test functions across `test_synth_fallback.py`, `test_gap_researcher.py`, parts of `test_instruction_providers.py`, plus the `_drafting_started` test                                                        | They test agents and behaviors that no longer exist. Delete with the agents.                                                                                                                                                                                                                                                                                                                                                                                         |

## What we keep (and why)

| Kept                                                             | Why                                                                                                                                                                                                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Enricher                                                         | Focused, bounded, has caching mechanism. Inlining its work into the lead grows the prompt and reimplements caching. Not worth it.                                                                                                          |
| Pre-dispatch evidence-surface coverage check                     | **The scalable floor replacement.** Addresses the exact undercoverage failure mode the eval surfaced. Sharpened to a structured form: name the material evidence surfaces and the specialist covering each one before emitting tool calls. |
| Specialists, AgentTool wrapping, descriptions, plugin guards     | Working in production today. No change.                                                                                                                                                                                                    |
| `places_context`, geo-bias state keys                            | Used by specialists, working. No change.                                                                                                                                                                                                   |
| Follow-up agent                                                  | Working in production. Just remove its `research_plan` injection (one line).                                                                                                                                                               |
| Premise assessment in lead's prompt                              | The "test assumptions, surface CONTRADICTED verdicts" framing is a quality feature visible in production reports (deploy-log smoke #1). Keep, but reframe so the verdicts are translated into report prose, not echoed as labels.          |
| Reconnaissance phase (3-5 google_search queries before dispatch) | Working in production; informs premise assessment. Keep.                                                                                                                                                                                   |
| Existing plugin lifecycle + nested-invocation guards             | Already verified in production. No change.                                                                                                                                                                                                 |

## Complications + how we treat them

Adam asked to identify these explicitly. Each one is real; each gets a
deliberate "simplify and ship" answer.

### 1. Lead's prompt grows materially

The merged prompt is ~140-160 lines (vs current orchestrator 118).
Concern: prompt bloat, instructions getting lost.

**Treat:** ship and watch. Production smoke #1 already shows the
current 118-line prompt produces structured output reliably. ~40 more
lines for the synthesis rules is well within Gemini 3.1 Pro's
attention. If we see specific instructions getting dropped (e.g.
charts not emitted, follow-up questions missing), we tune then.

### 2. Lead's context per turn grows

Lead now sees: instruction (~150 lines, ~3K tokens) + reconnaissance
search results (~5K tokens) + N specialist tool_responses (5-10K each
× 3-5 specialists = 25-50K tokens) + maybe iterative dispatch
tool_responses. Total per-turn context: 50-100K+ tokens.

**Treat:** Gemini 3.1 Pro has a 1M-token context. We're nowhere near
the ceiling. The synthesizer was already getting all this content via
state injection (`include_contents='none'`); we just stop the round-trip
and serve from tool-response context directly. Net token usage **goes
down**, not up.

### 3. Follow-up agent loses `research_plan` context

Currently follow-up's prompt injects `research_plan` (the structured
plan summary) alongside `final_report` and `places_context`. After
collapse, no `research_plan` exists. Follow-up reads only
`final_report` + `places_context`.

**Treat:** simplify follow-up's prompt template; drop the
`{research_plan}` placeholder. The full `final_report` contains
everything follow-up needs: the answer, the evidence, the structure.
We lose the explicit structured plan, but follow-up has been
working off `final_report` as its primary signal anyway.

### 4. Gap researcher's failure-recovery role gets reassigned

Today: if a specialist errors, gap researcher runs 3 google_search
queries to fill the gap. Under collapse: lead sees the
`Research unavailable: X` text in the specialist's tool_response and
must decide what to do.

**Treat:** add one line to the lead's prompt: "If a specialist tool
returns 'Research unavailable: ...', call `dynamic_researcher_1` with
a brief that names the specific angle the failed specialist would have
covered, OR call the failed specialist again with a more focused
brief." This makes the lead's iterative dispatch absorb gap research's
job. Loses: dedicated gap-researcher quality auditing. Gains: simpler
pipeline.

### 5. `firestore_events.py` references `research_plan`

`firestore_events.py:163-164` maps `research_plan` state_delta into a
`milestones.plan_ready_text` Firestore field. The frontend may render
this as a "research plan" timeline marker.

**Treat:** delete those two lines. If the frontend timeline visibly
lacks a "plan ready" marker after deploy, accept the UI regression
(per Adam's "I'm OK with limiting scope"). If it renders something
that depends on the marker existing (likely degrades gracefully —
just no marker, not a hard error), accept and decide later.

### 6. AUTHORING.md drift

References to gap researcher, synthesizer, and `research_plan`
throughout the doc.

**Treat:** trim AUTHORING.md to match the new pipeline. ~10 min of
edits.

### 7. Pickle / agent_engines.update behavior

Lead's prompt is bigger, more callbacks attached. Risk: cloudpickle
fails on something new.

**Treat:** run the same cloudpickle smoke that ran cleanly in the
prior migration. Same gate, same cost (~10 min). If it fails, fix the
specific issue. Don't add cloudpickle support speculatively.

### 8. Empty model response is a real failure mode without the fallback

Current `_synth_fallback_callback` fires on the synthesizer's response
and stitches a deterministic report from specialist outputs in state
when the model returns empty / no_text_parts / error_code. Under
collapse, this callback is **deleted entirely** per Adam's "lean and
clean."

**Treat:** accept the regression. If the lead's `LlmResponse` is
empty or whitespace-only, the Firestore mapper should not map it to a
terminal `complete` payload and `GearRunState.finalize()` should write
`empty_or_malformed_reply`. This is the intended fail-loud behavior:
no blank report and no synthetic stitched answer. Production smokes
have not surfaced an empty-response failure in any of the recent
migration runs. If we see one or two in the wild post-deploy, add a
minimal root-cause-oriented guard, for example a one-line
`after_model_callback` that returns a plain "model returned no
content" error message. Do **not** re-add the stitched fallback unless
production evidence says empty model output is common enough to justify
that complexity.

### 9. `_drafting_started` IS read by the frontend

Earlier draft of this plan claimed "no readers." Wrong. It's read by
`firestore_events.py:175`, mapped to a `drafting` event, consumed by
the frontend at `src/lib/chat-state.svelte.ts:401` to gate the
typewriter-effect rendering.

**Treat:** drop the marker entirely (per Adam's "OK to limit UI
scope"). The frontend's typewriter effect was a polish layer that
showed "drafting…" between dispatch end and report start. Without the
marker, reports appear when the lead's response completes — same
final state, fewer intermediate UI stages. If post-deploy UX feels
abrupt, we re-add a one-line emission from the lead's
`before_model_callback` on its post-tool-call response.

### 10. P0 — Terminal author mapping in firestore_events.py

`firestore_events.py:185` only treats `synthesizer` and `follow_up` as
terminal authors for `final_reply`. Without an update, the lead's
`final_report` state_delta won't be recognized as terminal,
`GearRunState.finalize()` won't see a `final_reply`, and turns will
write `empty_or_malformed_reply` per `gear_run_state.py:307`.

**Treat:** non-negotiable. Update the terminal-author mapping to
include `research_lead` (or whatever name we settle on). This is
explicit in the execution plan as Step 5 below. Test it before
merging.

### 11. Iterative dispatch is currently unobserved in production

Production smokes 1-3 all showed parallel one-shot dispatch. Whether
the lead actually iterates when warranted is unverified.

**Treat:** ship. If iterative dispatch never fires on real queries,
that's a quality observation we can act on later (sharpen the
prompt's "when warranted" criteria). The capability is wired; usage
is the model's call.

## Execution plan

Step-by-step. ~4-6 hours of focused work.

### 1. Description fixes (~2 hours)

Edit `agent/superextra_agent/specialist_catalog.py`. Targeted updates
to four specialist descriptions per the floors-handoff doc:

- `review_analyst` — closure-detection role.
- `marketing_digital` — price-positioning signal.
- `dynamic_researcher_1` — pair-with-operations rationale.
- `menu_pricing` — verify currently-operating language is present.

### 2. Build the merged ResearchLead prompt (~1 hour)

Create the merged prompt as
`agent/superextra_agent/instructions/research_lead.md`. Structure:

1. Role line.
2. Date prefix instruction.
3. `{places_context}` injection.
4. Follow-up handling (slimmed; reads from existing specialist results
   directly, not via `research_plan`).
5. Process steps:
   - Analyze the question (premise audit).
   - Reconnaissance (3-5 google_search).
   - Identify material evidence surfaces.
   - Pick specialists by unique signal (no floors).
   - Craft specific briefs.
   - Dispatch in parallel (one-shot for well-defined queries).
   - Post-result sufficiency check + iterate if a material surface is
     still weak.
   - Emit final report.
6. Domain boundaries (kept verbatim).
7. **NEW** — Output format section: executive summary, headings by
   insight theme, depth preservation, premise-assessment translation,
   follow-up questions.
8. **NEW** — Chart syntax (copy from `synthesizer.md:42-56`).
9. Key principles + What you do NOT do (slimmed).

Delete the old synthesizer prompt file: `synthesizer.md`.

### 3. Wire the new agent.py (~1 hour)

In `agent/superextra_agent/agent.py`:

1. Rename `research_orchestrator` to `research_lead`. New configuration:
   - `output_key="final_report"` (was `research_plan`).
   - **No** `after_model_callback` — synth fallback dropped entirely.
   - Keep tools: `[google_search, fetch_web_content, *AgentTool(spec, include_plugins=True) for spec in ALL_SPECIALISTS]`.
2. **Delete** `_make_synthesizer`, `_synthesizer_instruction`,
   `_SYNTHESIZER_TEMPLATE`, `_SYNTHESIZER_KEYS`, `_mark_drafting`,
   `_synth_fallback_callback`, `_classify_synth_response`,
   `_build_fallback_report`. All gone.
3. Update pipeline:
   ```python
   research_pipeline = SequentialAgent(
       name="research_pipeline",
       sub_agents=[_make_enricher(), research_lead],
       description="Enriches context, then plans + dispatches + synthesizes in one lead agent.",
   )
   ```
4. Delete `make_gap_researcher` import and call.
5. In `_orchestrator_instruction` (rename to
   `_research_lead_instruction`), drop the `prior_plan` injection
   (no `research_plan` anymore). Keep the `existing` results detection
   for follow-up turns.

### 4. Delete the gap researcher (~15 min)

In `agent/superextra_agent/specialists.py`:

- Delete `make_gap_researcher`.
- Delete `_should_run_gap_researcher`.
- Delete `_gap_researcher_instruction`.
- Delete `_GAP_RESEARCHER_TEMPLATE`, `_GAP_RESEARCHER_KEYS`.

In `agent/superextra_agent/specialist_catalog.py`:

- Delete the `gap_researcher` Specialist entry from `SPECIALISTS`.
  This collapses `SPECIALISTS == ORCHESTRATOR_SPECIALISTS`. The two
  names now describe the same set; pick one. Recommend: keep
  `SPECIALISTS` as the only name, remove `ORCHESTRATOR_SPECIALISTS`
  alias since it's no longer derived.

Delete `agent/superextra_agent/instructions/gap_researcher.md`.

### 5. Update firestore_events.py — terminal mapping + drop dead refs (~30 min)

**P0 — terminal author mapping.** At
`agent/superextra_agent/firestore_events.py:185`, the terminal-author
list currently includes `synthesizer` and `follow_up`. Add
`research_lead` (or whatever the new lead's `name=` is — keep it
`research_lead` for grep-friendliness). Without this, the lead's
`final_report` state_delta won't trigger turn finalization and
`GearRunState.finalize()` will write `empty_or_malformed_reply` per
`gear_run_state.py:307`. Add a unit test that synthesizes a fake
state_delta event from `research_lead` and verifies the mapping
recognizes it as terminal.

**Drop dead refs.** Delete `firestore_events.py:163-164`
(`research_plan` → `plan_ready_text` mapping). Delete the
`_drafting_started` → `drafting` event mapping at
`firestore_events.py:175`. Both are dead after this collapse.

In `agent/superextra_agent/instructions/follow_up.md` and
`_follow_up_instruction` in `agent.py`: drop `{research_plan}`
placeholder + the corresponding values dict entry.

### 6. Update tests (~45 min)

- **Delete** `agent/tests/test_synth_fallback.py` — fallback is
  removed entirely; the file tests behavior that no longer exists.
- **Delete** `agent/tests/test_gap_researcher.py` — gap researcher gone.
- **Update** `agent/tests/test_instruction_providers.py` — match new
  lead instruction shape (no `{research_plan}`, no `gap_research_result`).
- **Update** `agent/tests/test_specialist_catalog.py` — drop assertions
  on `gap_researcher` and `ORCHESTRATOR_SPECIALISTS` (now equal to
  `SPECIALISTS`).
- **Add** to `agent/tests/test_firestore_events.py` — new test:
  `state_delta` event with `final_report` from `research_lead` author
  is recognized as terminal. **This is a P0 gate** per the reviewer's
  finding; without it, deploy ships broken turn finalization.
- **Add** one negative empty-output test — a `research_lead` event with
  empty or whitespace `final_report` must not map to `complete`; the run
  should end through the existing `empty_or_malformed_reply` path. This
  locks in the decision to remove the stitched fallback while keeping
  terminal behavior explicit.
- **Update** `agent/tests/test_firestore_progress.py` — verify
  `_state_for_event` test still passes; the runId-routing logic is
  unchanged. Drop any `_drafting_started`-touching assertions.

Run `cd agent && PYTHONPATH=. .venv/bin/pytest tests/`. Fix specific
failures only, no opportunistic refactors.

### 7. Update AUTHORING.md (~10 min)

Trim references to synthesizer, gap researcher, `research_plan` state
key. New pipeline diagram.

### 8. Pre-merge gates (~15 min)

- All four test suites pass: pytest, vitest, functions, rules.
- Cloudpickle smoke: `cloudpickle.dumps(app.root_agent)` clean.
- ESLint + svelte-check: pre-existing warnings only.

That's it. **No floor eval re-run. No A/B comparison.** Adam's call:
ship and observe.

**Execution update, 2026-04-30:** collapse implementation shipped in
commits `22d2540` and `8fb24d3`, then deployed to Agent Engine via
operation `8495080385296728064`. Agent pytest, Vitest, Cloud Functions
tests, `npm run build`, `npm run check`, cloudpickle smoke,
stale-reference scan, and live smoke coverage passed. Firestore rules
tests were blocked in one local VM because Java was not installed for
the emulator, then covered by CI during the deploy path.

### 9. Deploy

Per the prior migration's deploy log:

1. Single squash commit on `agent-routing-eval` branch.
2. PR → CI green → merge to `main`.
3. Manual `agent_engines.update(...)` against the production
   Reasoning Engine (don't forget
   `GOOGLE_APPLICATION_CREDENTIALS=/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json`).
4. One production smoke through `agent.superextra.ai/chat`.

### 10. Post-deploy monitoring (~no work, just observe)

Watch for ~1 week:

- Are reports still structured (executive summary, headings,
  follow-up questions)?
- Do charts still emit when warranted?
- Is the lead dispatching the right specialists for
  openings/closings, pricing, wage/labor queries (the prior floor
  cases)?
- Any new error patterns in Firestore session logs?

If any of these regress, we have specific diagnoses to act on. We
don't pre-build for them.

## Risks

| Risk                                                                                                        | Likelihood         | Mitigation                                                                                                                                                                                                                                          |
| ----------------------------------------------------------------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lead's merged prompt loses instructions and reports lose structure                                          | Medium             | Watch first 5-10 prod sessions. Sharpen prompt if specific instructions get dropped.                                                                                                                                                                |
| Lead doesn't dispatch the right specialists for prior-floored queries (review_analyst on closures, etc.)    | Medium             | Watch dispatch counts in Firestore session events. If a known query type drops a previously-floored specialist, first sharpen the relevant specialist description and evidence-surface wording. Re-add floors only as an emergency hotfix.          |
| Gap-recovery via iterative dispatch doesn't work (lead doesn't see "Research unavailable:" and re-dispatch) | Low                | Specialists rarely error catastrophically in practice. If we see a session with a failed specialist + no recovery, add explicit "if you see Research unavailable, do X" to the prompt.                                                              |
| Lead's response is empty in production (no fallback exists anymore)                                         | Low                | We have no evidence of empty model responses in recent deploys. If one shows up post-deploy, the run should fail as `empty_or_malformed_reply`; fix the cause or add a plain error callback. Do not restore the stitched synth fallback by default. |
| Terminal-author mapping forgotten or misconfigured                                                          | **High if missed** | Pre-merge gate: explicit test that a `final_report` state_delta from `research_lead` is recognized as terminal. Manual sanity-check on staging via Chrome MCP if any doubt.                                                                         |
| Cloudpickle fails on the new shape                                                                          | Low                | Same gate as last time; catches it pre-merge.                                                                                                                                                                                                       |
| Frontend timeline shows oddities (no plan_ready marker, etc.)                                               | Medium-low         | Accept per "OK to limit UI scope." Fix specifically if a user-visible feature breaks.                                                                                                                                                               |

## What this plan deliberately does NOT do

- **Doesn't run the floors eval.** Per Adam's call. Ship the change;
  validate via production observation.
- **Doesn't run a Variant-A-vs-Variant-B-collapsed eval.** Same.
- **Doesn't reimplement gap research as a structured-output critic
  inside a LoopAgent** (the deep-search shape). That's a future
  decision if iterative dispatch proves insufficient — and per
  Anthropic, it's likely not needed for our specialist count and
  query distribution.
- **Doesn't reorganize the enricher.** Keep as-is.
- **Doesn't add a citation schema** like Anthropic's CitationAgent. We
  don't need it; sources are inline in specialist outputs already.
- **Doesn't preserve `research_plan` for the frontend's timeline.**
  Accepting the UI regression.

## Acceptance criteria (lean)

Pre-merge:

- [x] All four test suites pass. Local status: pytest, Vitest, and
      functions pass; rules blocked by missing Java in one VM and
      covered by CI.
- [x] **Terminal-author mapping test passes** — `research_lead` →
      `final_report` state_delta recognized as terminal. P0; without
      this turns won't finalize.
- [x] **Empty-output negative test passes** — empty/whitespace
      `final_report` from `research_lead` does not map to `complete`
      and ends through the existing `empty_or_malformed_reply` path.
- [x] Cloudpickle smoke passes.
- [x] No leftover `synthesizer`, `gap_researcher`, `research_plan`,
      `gap_research_result`, `_drafting_started`, `_synth_fallback_callback`,
      `_mark_drafting`, `_classify_synth_response`, `_build_fallback_report`
      references in production code.

Pre-deploy:

- (none — no staging dance)

Post-deploy:

- [x] One production query through the UI returns a structured report
      (executive summary, ≥2 headings by insight theme, follow-up
      questions, sources cited).
- [x] **Turn finalizes correctly** (`session.status=complete`,
      `turn.status=complete`, `final_reply` populated). This is the
      load-bearing P0 verification — if this fails, the terminal
      mapping wasn't done correctly and we hotfix.
- [x] No new errors in Vertex AI Agent Engine logs in the first hour.

That's it. Ship.

## Time estimate

- Description fixes: 2 hours
- Merged prompt: 1 hour
- agent.py + specialists.py + catalog wire-up: 1.5 hours
- Tests: 30 min
- Docs: 10 min
- Pre-merge gates: 15 min
- Deploy + smoke: 30 min

**Total: ~5-6 hours focused work.**

## Sources

- Anthropic Research multi-agent system: https://www.anthropic.com/engineering/multi-agent-research-system
- ADK multi-agent docs: https://adk.dev/agents/multi-agents/
- ADK academic-research sample (collapsed pattern): https://github.com/google/adk-samples/tree/main/python/agents/academic-research
- ADK deep-search sample (split pattern; doesn't apply here): https://github.com/google/adk-samples/tree/main/python/agents/deep-search
- Google Cloud Blog — Build a deep research agent with Google ADK: https://cloud.google.com/blog/products/ai-machine-learning/build-a-deep-research-agent-with-google-adk
- LangGraph supervisor: https://github.com/langchain-ai/langgraph-supervisor-py
- LangChain subagents personal-assistant pattern: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant
- Internal: floors handoff doc and rearchitecture deploy log (links at top of this doc)
