# Agent routing redesign — context, motivations, findings

**Date:** 2026-04-29
**Owner:** Adam (PM)
**Status:** Investigation; pre-plan
**Related docs:**

- `docs/agent-tool-spike-findings-2026-04-29.md` — empirical spike comparing two orchestration patterns
- `docs/agent-routing-redesign-eval-plan-2026-04-29.md` — the test plan derived from these findings

## What this document is

A working journal of the agent-routing redesign investigation. Captures
why we started, what we've learned, what changed our thinking, and the
open decisions before we commit to changes. Written so a future Claude
session (or stakeholder) can pick it up cold without reading the whole
chat history.

## Background — what we have today

Superextra's research agent (`agent/superextra_agent/`) is a multi-agent
pipeline running on Google ADK 1.28 + Vertex AI Gemini 3.1 Pro. The
pipeline is composed as a `SequentialAgent`:

```
Router → ResearchPipeline[
    ContextEnricher → ResearchOrchestrator → ParallelAgent[8 specialists] → GapResearcher → Synthesizer
]
```

The `ResearchOrchestrator` decides which of the 8 specialist agents to
dispatch for a given user query, then writes briefs to session state via
a `set_specialist_briefs(briefs_dict)` tool. The `ParallelAgent` fans out
the specialists; each one's `before_agent_callback` skips itself if no
brief is in state. Outputs land in state via per-specialist `output_key`s
and feed downstream into the synthesizer's report.

Specialists today (`agent/superextra_agent/specialist_catalog.py`):
`market_landscape`, `menu_pricing`, `revenue_sales`, `guest_intelligence`,
`location_traffic`, `operations`, `marketing_digital`, `review_analyst`,
plus a flexible `dynamic_researcher_1` and a post-hoc `gap_researcher`.

Each specialist has a one-line `description` field in the catalog. The
catalog comment claims it's "used by the orchestrator prompt and as the
`LlmAgent.description`" — that turns out to be partially true (see
findings below).

## Trigger — what set this off

V2 of the orchestrator instructions (`research_orchestrator.md:84-106`)
introduced **query-type coverage requirements** — hard rules that say
e.g. "openings/closings questions MUST include market_landscape +
menu_pricing + marketing_digital + review_analyst." Five such floors,
each with rationale and "also consider" lists.

Adam's concern: these rules work for the specific phrasings listed, but
real customers ask in a million different ways. Per-rule maintenance
doesn't scale. The fundamental question: _should we be hardcoding
query-type → specialist mappings, or should the orchestrator reason about
coverage based on what each specialist actually does?_

## Goals

What we want from this redesign:

1. **Routing that scales to long-tail phrasings** — the orchestrator
   should pick correctly for queries no one wrote a rule for.
2. **Single source of truth for specialist capabilities** — descriptions
   in one place, no drift between catalog and prompt.
3. **Alignment with how research-agent systems are supposed to work**
   per Google ADK guidance, Anthropic's Research multi-agent system,
   and the LangGraph/Claude Code patterns.
4. **Either better or equal output quality** — we won't ship a
   regression to gain architectural elegance.
5. **Either simpler or equivalent operational complexity** — same.
6. **A measurable evaluation harness** — every architectural change
   gated on eval evidence, not on aesthetic preference.

## Research findings — external evidence

Delegated to a research agent, full report cited inline below.

### Google ADK official guidance

ADK has two parent→child invocation patterns:

- **`sub_agents=[...]` + `transfer_to_agent`** — the child takes over
  the conversation; control leaves the parent. Used for routers.
- **`AgentTool(agent=child)`** — the parent calls the child like a
  function, gets back the output, retains control. Used for specialist
  invocation in research-agent patterns.

The `LlmAgent` page draws the canonical distinction: **`description` is
metadata for _other_ agents to route on**; `instruction` is the agent's
own behavioral guide
([adk.dev/agents/llm-agents](https://adk.dev/agents/llm-agents/index.md)).
The example given is preferring `"Handles inquiries about current
billing statements"` over `"Billing agent"`.

The mechanical fact: in `agent_tool.py:121`, `super().__init__(name=agent.name, description=agent.description)`
— the parent LLM literally sees `agent.description` as the tool
description. **Description IS the routing primitive in the AgentTool
pattern.** None of the public ADK samples (academic-research,
fomc-research, deep-search, marketing-agency) encode "for query type X,
MUST run Y and Z." They lean on rich descriptions plus reasoning.

### Cross-industry consensus

Anthropic's writeup of the Research multi-agent system is the strongest
external signal. Their reported failure mode is exactly ours — vague
sub-agent task descriptions led to duplication and gaps. Their fix
wasn't "add prescriptive rules"; it was rich, specific task descriptions
that teach sub-agents what to do
([anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system);
[simonwillison.net summary](https://simonwillison.net/2025/Jun/14/multi-agent-research-system/)).

LangChain has formally migrated _away_ from hardcoded routing dicts
toward tool-description-based handoff in their supervisor pattern
([docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/workflows-agents);
[langgraph-supervisor](https://reference.langchain.com/python/langgraph/supervisor/)).
Practitioner critiques converge: hardcoded routing breaks ~30
specialists in
([dev.to](https://dev.to/sturnaai/why-competitive-agent-routing-beats-static-orchestration-3lnj)).
Deep Research Agents survey paper lists "always run all" as a known
anti-pattern when sub-agents have non-trivial cost
([arxiv.org/2506.18096](https://arxiv.org/html/2506.18096v1)).

### Alternatives evaluated

A. **Rich capability descriptions** (mainstream recommendation) —
descriptions carry non-obvious capabilities, LLM reasons about coverage.

B. **Always run all specialists** — Anthropic measured ~15× token cost;
unworkable for our latency profile (tail = slowest specialist every time).

C. **Two-stage classifier→dispatch** — moves the rules problem one
layer deeper.

D. **Coverage-gap iteration (critic loop)** — Anthropic, LangChain Open
Deep Research, Skywork DeepResearchAgent all use this as a safety net.

E. **Hybrid: small always-include floor + rich descriptions** — what
production deep-research systems actually ship.

F. **Specialist self-selection / bidding** — academic only, no
production track record.

**Synthesis:** evidence favors **E with A doing most of the work and D
as a safety net.**

## Architecture discovery — the surprise

Mid-investigation discovery that changed the framing: **in our current
pipeline, the catalog `description` field is NOT actually consumed at
routing time.** Walking through the wiring:

- `specialist_catalog.py` sets `description` on each Specialist.
- `_make_specialist()` in `specialists.py:227` constructs each
  `LlmAgent(description=description)`. ✓
- BUT specialists are children of a `ParallelAgent` (`agent.py:265-269`),
  NOT wrapped as `AgentTool`s on the orchestrator.
- The orchestrator dispatches via a regular `set_specialist_briefs(briefs_dict)`
  tool (`specialists.py:190`), not via tool selection.
- The orchestrator's view of "what each specialist does" is _only_ the
  prompt text in `research_orchestrator.md:65-73` — a hand-maintained
  duplicate that drifts independently from the catalog.

So in our setup, the catalog comment claiming descriptions are "used by
the orchestrator prompt" is aspirational; nothing renders the catalog
into the prompt at runtime. The .md text is the actual routing primitive.

This shaped the path-forward decisions: any "fatten the descriptions"
change has to either (a) land primarily in `research_orchestrator.md`
with the catalog updated for consistency, or (b) restructure the
pipeline so the catalog actually drives routing.

## Spike findings — empirical comparison of orchestration patterns

Detail in `docs/agent-tool-spike-findings-2026-04-29.md`. Headlines:

- Built two minimal pipelines: Variant A (current pattern replica) and
  Variant B (specialists wrapped as `AgentTool`).
- Same query, models, specialists, places_context, instruction-level
  forcing of both-specialist dispatch.
- 2 trials per variant.

**Confirmed:**

- Gemini 3.1 Pro emits parallel AgentTool calls in a single response;
  ADK runs them concurrently.
- `output_key` writes from child agents propagate back to the parent
  session state via `state_delta` forwarding (`agent_tool.py:256-258`).
- Latency comparable: Variant A 99-134s; Variant B 89-130s.
- Variant B's research_plan (orchestrator's summary) is consistently
  richer (489-721 chars vs 438-441) because it sees specialist outputs
  as tool responses.

**Surfaced as a complication:**

- Plugin lifecycle. Both `FirestoreProgressPlugin` and `ChatLoggerPlugin`
  use `before_run_callback` / `after_run_callback`, which fire once per
  root invocation. Under AgentTool, each specialist call is its own
  root invocation, so these callbacks would misfire (multiple ownership
  claims, multiple heartbeats, multiple terminal writes per turn).
  `firestore_progress.py:19-22` explicitly documents the plugin's
  dependence on the current composition pattern.
- Parent-runner event visibility. Specialist events stay encapsulated
  inside AgentTool's child runner; the parent only sees orchestrator
  events. Eval scorer (`evals/parse_events.py`) walks the parent
  stream — under Variant B it loses per-specialist tool counts, fetched
  URLs, token usage, grounding data.

**Resolved by further research (after the spike):**

- Subagent output access. Plugins propagate to child runners
  (`agent_tool.py:222-236`); each child runner constructs its own
  PluginManager wrapping the same plugin instances; `on_event_callback`
  fires for child events. So a small `EventCapturePlugin` would observe
  per-specialist events under both variants. Eval-scorer regression is
  **not** a real blocker — switching to plugin-based event capture is
  ~20 lines and works for both architectures.

## Quality + simplification — honest assessment

**Quality (does Variant B produce better output?):**

- _Specialist output:_ identical under both. Same model, same
  instructions, same tools.
- _Orchestrator summary:_ measurably richer under B (the 489-721 vs
  438-441 numbers).
- _Iterative dispatch capability:_ unique to B. Orchestrator can call
  one specialist, read its output, decide whether to call others,
  redirect to `dynamic_researcher_1` if an angle doesn't fit.
  `set_specialist_briefs` is one-shot; the pre-dispatch coverage check
  is a poor substitute because it predicts coverage gaps without seeing
  real data. The iterative pattern is what Anthropic's Research
  multi-agent system uses. **This is the load-bearing quality argument
  for B.**

**Simplification:**

- _Orchestrator code:_ simpler under B (one `LlmAgent` instead of
  `SequentialAgent[orch, ParallelAgent[specs]]`; no
  `set_specialist_briefs`; no `_make_skip_callback`; no duplicate
  specialist list at `research_orchestrator.md:65-73`).
- _Plugin layer:_ slightly more complex under B (~15-20 lines per
  plugin to detect nested invocations and skip lifecycle callbacks).
  Bounded, not a rewrite.
- _Eval scorer:_ simpler under either path if we move event capture to
  a plugin (works for both architectures; cleanly decouples scoring
  from runner shape).
- _Frontend progress UI:_ needs verification under B — `on_event`
  fires correctly for child events, but writes to Firestore depend on
  whether the plugin maps invocation_context to the right session ID.

**Net:** Variant B simplifies the orchestrator and eval layers, adds
bounded complexity to plugins, has uncertain frontend impact pending
verification.

## Open decisions

Two paths under active consideration:

**Path A — full Variant B migration.** AgentTool-wrapped specialists,
plugin lifecycle refactor, eval scorer to plugin-capture, full prompt
rewrite. ~6-8 days. Highest-risk piece is plugin work. End state:
canonical Google/Anthropic pattern; iterative dispatch capability;
descriptions are truly the routing primitive.

**Path B — capture the routing-quality win without the architecture
change.** Keep current `SequentialAgent` + `ParallelAgent` +
`set_specialist_briefs`. Render the catalog into the orchestrator's
prompt at runtime (single source of truth). Fatten descriptions to
lead with scope, then live data sources, then boundary. Drop the
query-type coverage matrix; replace with a count-based principle
("≥2 specialists, ≥3 for multi-angle"). Add a pre-dispatch coverage
check to the orchestrator instruction. ~2-3 days. No architectural
risk. End state: same routing reasoning from the LLM's perspective as
Path A, but with the existing plumbing intact.

Recommendation noted in the spike findings: do Path B first, gate on
eval results, reconsider Path A only if the description rewrite + count
floor + coverage check don't deliver.

But the iterative-dispatch capability (Path A only) is the future-proof
feature. If we expect to lean on it, Path A becomes a "now or
later" question, not "if at all."

## Learnings — what changed our thinking

- The catalog comment was misleading. We assumed `description` was
  load-bearing; mechanically, in our pipeline, it isn't.
- The query-type coverage rules exist because the orchestrator's view
  of capabilities (the .md list) doesn't surface non-obvious data
  sources. Fix the _what each specialist actually surfaces_ problem
  and the rules dissolve.
- AgentTool's plugin propagation is more complete than the spike
  findings doc initially suggested. Per-callback hooks (`on_event`,
  `before_tool`, `after_tool`) work fine in nested invocations; only
  run-level lifecycle (`before_run`, `after_run`) misfires. That makes
  the plugin refactor focused, not a rewrite.
- The eval harness already exists (`agent/evals/run_matrix.py`,
  `evals/pairwise.py`, `evals/scores/V*.csv`) — we don't need to build
  evaluation infrastructure, only adapt it.
- LLM-as-judge with the same model family as the system being evaluated
  has known correlation bias. Mitigation: judge with Opus while the
  system runs Gemini.
- We don't have a labeled ground-truth eval set. We have a query
  taxonomy and a fixture set, but no per-query "correct specialist
  set" labels. For pairwise judging this is fine; for absolute
  rubric scoring it's a real gap.
- Pairwise judging is cheaper, faster, and gives more signal per token
  than absolute rubric scoring for A/B architectural comparison.
- Run-to-run latency variance is significant (88s ↔ 130s for the same
  variant on the same query). Single-trial latency claims are
  unreliable.

## Sources

ADK official:

- [adk.dev/agents/multi-agents](https://adk.dev/agents/multi-agents/index.md)
- [adk.dev/agents/llm-agents](https://adk.dev/agents/llm-agents/index.md) (description vs instruction)
- [adk-python/src/google/adk/tools/agent_tool.py](https://github.com/google/adk-python/blob/main/src/google/adk/tools/agent_tool.py)
- [github.com/google/adk-samples](https://github.com/google/adk-samples)

Industry / cross-platform:

- [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [simonwillison.net/2025/Jun/14](https://simonwillison.net/2025/Jun/14/multi-agent-research-system/)
- [docs.langchain.com — workflows-agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [langgraph-supervisor reference](https://reference.langchain.com/python/langgraph/supervisor/)
- [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research)

Critique / survey:

- [dev.to — competitive agent routing](https://dev.to/sturnaai/why-competitive-agent-routing-beats-static-orchestration-3lnj)
- [arxiv.org/html/2506.18096v1 — Deep Research Agents survey](https://arxiv.org/html/2506.18096v1)
- [getmaxim.ai — LLM Router landscape 2026](https://www.getmaxim.ai/articles/top-5-llm-router-solutions-in-2026/)

Internal:

- `agent/superextra_agent/instructions/research_orchestrator.md`
- `agent/superextra_agent/specialist_catalog.py`
- `agent/superextra_agent/specialists.py`
- `agent/superextra_agent/agent.py`
- `agent/superextra_agent/firestore_progress.py:19-22` (plugin lifecycle dependency)
- `agent/.venv/lib/python3.12/site-packages/google/adk/tools/agent_tool.py` (AgentTool source — plugin propagation, state forwarding)
- `agent/.venv/lib/python3.12/site-packages/google/adk/agents/parallel_agent.py` (ParallelAgent fan-out, event merging)
- `agent/evals/queries.json`, `agent/evals/venues.json` (existing fixtures)
- `agent/evals/run_matrix.py` (existing eval harness)
- `agent/evals/parse_events.py` (existing scorer)
- `agent/evals/pairwise.py` (existing pairwise comparison harness)

Spike artifacts:

- `agent/spikes/agent_tool/build.py` — both variant builders
- `agent/spikes/agent_tool/run_spike.py` — runner with verbose event capture
- `agent/spikes/agent_tool/results/variant_*.json` — captured event logs
- `docs/agent-tool-spike-findings-2026-04-29.md` — full spike report
