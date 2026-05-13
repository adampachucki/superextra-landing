# Report Writer Stage Plan

Date: 2026-05-12  
Status: implemented; revised 2026-05-13 to remove lead-authored writer brief

## Problem

The current research pipeline asks one agent, `research_lead`, to plan research,
brief specialists, judge evidence sufficiency, and write the final report.

That has created a compression point. Specialist reports can contain useful
names, numbers, source limits, counter-signals, and local observations, but the
final answer often preserves only the highest-level takeaways. Prompt changes
have not reliably fixed this because the architecture still routes all
specialist evidence through the lead's synthesis step.

For this product, the better bias is to surface too much relevant evidence
rather than lose useful findings.

## Decision

Add a terminal `report_writer` agent after `research_lead`.

Use the revised B2 flow:

```text
context_enricher
-> research_lead
   - plans the research
   - briefs specialists
   - calls specialists through AgentTool
   - records internal research_coverage for audit and future loop checks
-> report_writer
   - reads full specialist reports directly from state
   - reads Places context directly from state
   - does not receive lead-authored summary, emphasis, or outline
   - writes final_report
```

The writer produces the user-visible final answer. The final answer does not
return to the lead.

## Why B2

B2 keeps the process deterministic while removing the lossy synthesis layer.
The lead still owns planning, specialist dispatch, sufficiency checks, and
focused extra rounds. It no longer gives the writer a brief.

This revision came from live-session review. Even a constrained writer brief
became a subtle compression layer because the lead could name some findings,
omit others, and shape the report outline. The writer now reads only Places
context and full specialist reports.

## Research Coverage Contract

`research_coverage` is internal. It is useful for audit, debugging, evals, and a
future LoopAgent-style completeness check. The Report Writer does not read it.

The coverage note may contain:

- user question and response language;
- target restaurant, market, geography, and competitor set;
- operator decision or learning goal;
- specialists called;
- original brief issued to each specialist;
- evidence surfaces covered;
- source gaps, failed checks, stale evidence, or weak evidence;
- unresolved questions that could justify another focused research round.

The coverage note must not contain:

- key findings;
- top takeaways;
- implications;
- recommendations;
- discovered-entity priority lists;
- pre-written report sections.

This keeps the lead in the research-control role and the writer in the evidence
integration role.

## Writer Contract

The `report_writer` should:

- treat specialist reports as the primary source material;
- preserve every distinct finding, insight, data point, caveat, source limit,
  and implication connected to the question or Places context;
- treat each specialist report, especially its `Writer Material` section, as
  must-carry material unless an item is duplicated or clearly outside the
  question;
- preserve distinct insights, caveats, source limits, and implications rather
  than compressing the report to the highest-level takeaways;
- retain names, dates, numbers, prices, sample sizes, quotes, ranges, source
  limits, counter-signals, and uncertainty;
- make all relevant concrete findings visible in the format that fits the
  evidence: table, grouped bullets, short sections, or compact narrative;
- include grounded implications for the target venue when one is known;
- connect findings across specialists rather than listing reports one by one;
- bias toward dense, useful reporting over executive-summary brevity;
- tighten prose only by removing exact duplicated wording, internal process
  notes, and irrelevant dead ends; do not shorten by dropping distinct
  findings, evidence, caveats, source notes, examples, or implications;
- avoid new web research and new factual claims not grounded in the supplied
  reports or Places context;
- write `final_report`.

The writer should produce an integrated report, not a summary of summaries.

## Specialist Output Contract

Specialists should not compress their evidence into only the top takeaways.
They should surface all useful material they find: findings, citations,
source notes, exact data, quotes, caveats, failed checks, counter-signals,
considerations, and implications for the target venue. The bias is intentional:
the writer can remove duplicated or irrelevant material, but it cannot recover
findings that specialists never surfaced.

## Dynamic Research Slots

The lead should call at least two non-dynamic specialists plus at least one
dynamic researcher in every research report. Use dynamic researchers as added
deepening passes when the task needs flexible deep dives, cross-signal
connections, cause or mechanism research, implications, conflicts,
second-order effects, verification, non-standard evidence, or a focused extra
round. Do not let a dynamic researcher replace a core evidence surface. Use
`dynamic_researcher_1`, then `dynamic_researcher_2`, then
`dynamic_researcher_3`. Each writes a separate state key, so a later dynamic
call does not overwrite an earlier one.

## Recommended Pipeline

Current:

```text
Router
-> research_pipeline
   -> context_enricher
   -> research_lead
      -> specialists through AgentTool
```

Target:

```text
Router
-> research_pipeline
   -> context_enricher
   -> research_lead
      -> specialists through AgentTool
   -> report_writer
```

Implementation shape:

```python
research_lead = LlmAgent(
    name="research_lead",
    ...
    output_key="research_coverage",
)

report_writer = LlmAgent(
    name="report_writer",
    model=MODEL_GEMINI,
    instruction=_report_writer_instruction,
    description="Writes the final user-facing research report from specialist evidence.",
    tools=[],
    output_key="final_report",
    generate_content_config=ORCHESTRATOR_THINKING_CONFIG,
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[_make_enricher(), research_lead, report_writer],
)
```

The writer instruction provider should inject `places_context` and every
available specialist output from `SPECIALIST_RESULT_KEYS`. It should not inject
`research_coverage`.

## Completion Plumbing

Today the app treats `research_lead` as a final-response author. That must
change.

Required changes:

- `research_lead` no longer writes `final_report`;
- `report_writer` writes `final_report`;
- Firestore event mapping treats `report_writer` as the final research author;
- final capture should not accept `research_lead` as the user-visible report.

This is necessary because `GearRunState` captures the first complete reply. If
the lead remains a completion author, the app can still publish the brief
instead of the writer's report.

## Why Not Pure Option B

Pure option B would make the lead call `report_writer` as another `AgentTool`.
That is technically possible: ADK AgentTool runs the child agent, returns the
child response as the tool result, and forwards child state changes back to the
parent context.

It is still a weaker fit here because the lead would control when the writer
runs and could continue after the writer. Finality becomes indirect: a child
tool-agent has to be treated as the terminal user reply while the parent lead
still owns the outer turn.

B2 keeps the useful dynamic brief but makes writer execution deterministic.

## LoopAgent Path Later

The later loop should wrap research completeness, not final writing.

Target future shape:

```text
context_enricher
-> research_loop
   -> research_round
   -> sufficiency_checker
-> report_writer
```

The loop can run one or two bounded research rounds until completeness criteria
are met. The writer should still run once after the loop has stopped.

This keeps responsibilities clean:

- loop: decide whether research is complete enough;
- specialists: produce evidence;
- writer: integrate all evidence into the final report.

Do not put the writer inside the loop unless the product explicitly needs draft
revision. The current problem is missing evidence in the final answer, not
iterative prose polishing.

## Lean Implementation Steps

1. Add `instructions/report_writer.md`.
2. Change `research_lead.md` so the lead writes `research_coverage`, not
   `final_report`, and so the coverage note stays internal.
3. Add `_report_writer_instruction(ctx)` in `agent.py`.
4. Add `report_writer` in `agent.py` with no tools and
   `output_key="final_report"`.
5. Change `research_pipeline` to run `context_enricher`, `research_lead`,
   `report_writer`.
6. Update Firestore event mapping so `report_writer` is the final research
   author.
7. Add focused tests for instruction injection and final-response mapping.
8. Run agent tests and a small eval sample against previous outputs.

Keep this small. Do not add schemas, validators, callbacks, extra agents, or
looping in the first pass.

## Evaluation

The current rubric already scores faithfulness, completeness, specificity, and
investigative stance. Add two report-writer checks:

- Detail retention: the final report preserves relevant specialist findings,
  including concrete names, numbers, dates, source limits, and counter-signals.
- Cross-specialist synthesis: the final report connects findings across
  evidence surfaces instead of summarizing each specialist independently.

The key comparison is pairwise: current pipeline vs writer-stage pipeline on the
same captured prompts.

## Source Basis

- Google ADK workflow agents: deterministic sequential, parallel, and loop
  orchestration.
  https://raw.githubusercontent.com/google/adk-docs/main/docs/agents/workflow-agents/index.md
- Google ADK multi-agent systems: shared session state, `output_key`,
  AgentTool, and fan-out/gather patterns.
  https://raw.githubusercontent.com/google/adk-docs/main/docs/agents/multi-agents.md
- Google ADK LoopAgent: bounded iterative refinement with max iterations or an
  explicit stop condition.
  https://raw.githubusercontent.com/google/adk-docs/main/docs/agents/workflow-agents/loop-agents.md
- Google ADK evaluation: evaluate both final response and trajectory/tool use.
  https://raw.githubusercontent.com/google/adk-docs/main/docs/evaluate/index.md
- ReAct: tool-using agents benefit from interleaving reasoning and external
  actions, but tool use and final response remain distinct concerns.
  https://openreview.net/forum?id=WE_vluYUL-X
- Self-RAG and CRAG: retrieval quality and self-checking matter; more retrieval
  alone does not guarantee better final answers.
  https://openreview.net/forum?id=hSyW5go0v8
  https://arxiv.org/abs/2401.15884
- Multi-document synthesis research: modern summarizers can be sensitive to
  input order and imperfect at aggregating conflicting inputs, so preserving
  source reports for the terminal writer is preferable to lead-compressed
  summaries.
  https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00687/124262/Do-Multi-Document-Summarization-Models-Synthesize
- Chain of Density: useful summaries balance information density and
  readability; here the product should intentionally bias toward higher
  information density.
  https://arxiv.org/abs/2309.04269
