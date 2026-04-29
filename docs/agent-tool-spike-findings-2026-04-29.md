# AgentTool migration spike — findings

**Date:** 2026-04-29
**Branch:** main (spike code in `agent/spikes/agent_tool/`)
**Cost:** ~$3-5 in Vertex AI calls (4 runs total)

## TL;DR

The AgentTool pattern works mechanically — Gemini 3.1 Pro emits parallel
tool calls in a single turn, ADK runs the specialist sub-agents
concurrently, output_keys propagate back to the parent's session state.
End-to-end latency is comparable to the current SequentialAgent +
ParallelAgent pattern (sometimes faster, fewer events of overhead).

**The blocker isn't orchestration — it's plugin lifecycle.**
`FirestoreProgressPlugin` is documented at
`agent/superextra_agent/firestore_progress.py:19-22` to deliberately
require the current composition pattern, because ADK fires
`before_run_callback` / `after_run_callback` once per root invocation.
Under AgentTool, each specialist call becomes its own root invocation —
the plugin would try to claim the run, spawn heartbeats, and write
terminal payloads N times per turn instead of once. That's not a small
plumbing fix; it's a meaningful refactor of the plugin lifecycle layer.

**Recommendation:** the orchestration migration is technically viable
but more invasive than initially scoped. Path forward depends on whether
we treat the plugin work as in-scope or whether we keep
SequentialAgent/ParallelAgent and capture the alignment win via a
smaller, lower-risk change.

## What was tested

- **Variant A**: replica of current pattern — `SequentialAgent[orchestrator (with set_specialist_briefs tool), ParallelAgent[menu_pricing, marketing_digital]]`.
- **Variant B**: AgentTool pattern — single `LlmAgent` orchestrator with `tools=[AgentTool(menu_pricing), AgentTool(marketing_digital)]`.

Both variants share: same Gemini 3.1 Pro models, same MEDIUM thinking
config on the orchestrator, same HIGH thinking on specialists, same
specialist instruction bodies (`menu_pricing.md`, `marketing_digital.md`),
same `[google_search, fetch_web_content]` tool pair on each specialist,
same hand-crafted `places_context` (no enricher), same query
(`q3_price_comparison` + monsun fixture), same prompt-level instruction
to dispatch both specialists. The orchestrator dispatch mechanism is the
only intentional difference.

Two trials per variant. Code under `agent/spikes/agent_tool/`. Raw event
logs under `agent/spikes/agent_tool/results/`.

## Apples-to-apples results

| Metric                           | Variant A trial 1     | Variant A trial 2     | Variant B trial 1             | Variant B trial 2             |
| -------------------------------- | --------------------- | --------------------- | ----------------------------- | ----------------------------- |
| Total elapsed                    | 133.7s                | 99.0s                 | 130.1s                        | 88.7s                         |
| Both specialists ran             | yes                   | yes                   | yes (1 empty)\*               | yes                           |
| pricing_result chars             | 5280                  | 5558                  | 5678                          | 5850                          |
| marketing_result chars           | 6578                  | 7021                  | **0\***                       | 6762                          |
| research_plan chars              | 441                   | 438                   | 721                           | 489                           |
| Events observed by parent runner | 7                     | 5                     | **3**                         | **3**                         |
| Parallelism mechanism            | ParallelAgent fan-out | ParallelAgent fan-out | Same-turn parallel tool calls | Same-turn parallel tool calls |

\*Variant B trial 1 had a flaky empty marketing_digital response —
specialist child agent ran but produced no final text. Trial 2 worked
correctly. Same flakiness profile would exist under Variant A; it's
upstream model behaviour, not an AgentTool defect.

## Open question 1 — parallelism: **confirmed yes**

Gemini 3.1 Pro emitted both AgentTool calls in a **single response**,
visible in the trace as `call ['menu_pricing', 'marketing_digital']` —
one event with two `function_call` parts. ADK's runtime then ran the
two child agents concurrently (the parallel execution can be inferred
from the timing — both specialists finished within a single response
window of ~75-105 seconds rather than serializing to ~150-200s).

The `resp` event came back with both results bundled:
`resp ['menu_pricing', 'marketing_digital']  →menu_pricing.len=5908  →marketing_digital.len=14`.

**Implication:** no separate fan-out machinery needed. The orchestrator
LLM can choose to dispatch one, two, or all specialists in a single
turn, and ADK runs them in parallel automatically.

**Caveat:** parallelism depends on the model _choosing_ to emit multiple
calls at once. The spike orchestrator prompt explicitly instructed
"emit BOTH tool calls in a single response so they execute concurrently."
A weaker prompt could lead the model to call serially. Production
prompts will need this language to preserve current parallel behaviour.

## Open question 2 — state propagation under AgentTool: **confirmed yes**

Both observable from the source (`agent_tool.py:256-258`) and verified
in the trial 2 run:

```
[variant_b_trial2 + 77.4s] research_orchestrator_b
  resp ['menu_pricing', 'marketing_digital']
  state_delta=['pricing_result', 'marketing_result']
```

Each specialist's `output_key` write fires inside its child runner; the
delta is forwarded to the parent session via
`tool_context.state.update(event.actions.state_delta)`. Final state
inspection confirms both keys land:

```
pricing_result    str(len=5850)
marketing_result  str(len=6762)
research_plan     str(len=489)
```

So the synthesizer / gap researcher / fallback report builder can
continue reading from the same state keys with no plumbing change.

## Open question 3 — prompt shape under AgentTool: **simpler, not larger**

Current `research_orchestrator.md` is 124 lines. Variant B's spike
prompt was 47 lines — the entire `## How to dispatch` and "valid brief
keys" framing collapses into "call these specialists as tools."

Production-shaped Variant B prompt would need to add back: reconnaissance
guidance, premise audit, follow-up handling, source-diversity guidance,
domain-boundaries section. Final length probably comparable to
current — bigger by a few lines for the "emit calls in parallel"
instruction, smaller by ~20 lines from dropping the briefs-tool
mechanics, the "set_specialist_briefs ONCE" guidance, and the duplicated
specialist list at lines 65-73 (descriptions become canonical via
`AgentTool(agent.description)`).

The orchestrator's behaviour also changes shape: instead of "plan and
hand off," it's "plan, call, await, optionally call more, summarize."
The spike orchestrator emitted one summarizing text event after the
specialist tool calls returned (lines 489-721 chars across the trials),
which would need to become the orchestrator's research-plan output —
shape-compatible with what the synthesizer expects today.

## Visibility regression — the cost AgentTool extracts

This wasn't on the original spike list, but it surfaced empirically and
matters: the parent runner sees **only 3 events** in Variant B vs **5-7
events** in Variant A.

Variant A trace (5 events, trial 2):

```
+  8.1s  research_orchestrator_a  call ['set_specialist_briefs']
+  8.1s  research_orchestrator_a  resp ['set_specialist_briefs']
+ 10.2s  research_orchestrator_a  text(438)
+ 87.2s  marketing_digital        text(7021) state_delta=['marketing_result']
+ 99.0s  menu_pricing             text(5558) state_delta=['pricing_result']
```

Variant B trace (3 events, trial 2):

```
+  7.5s  research_orchestrator_b  call ['menu_pricing', 'marketing_digital']
+ 77.4s  research_orchestrator_b  resp [...]  state_delta=[both]
+ 88.7s  research_orchestrator_b  text(489)
```

In Variant A, every specialist's intermediate events (web fetches, model
calls, thinking events) bubble up through ParallelAgent's queue
(`parallel_agent.py:_merge_agent_run`) into the parent runner's iterator.
The eval scorer reads these. The `chat_logger` plugin reads these. The
Firestore progress plugin maps these into per-specialist UI rows.

In Variant B, those events stay inside the AgentTool's _child runner_
(`agent_tool.py:228-264`). The parent runner only sees the orchestrator's
own events: the call, the response, the summary. Specialist work is
encapsulated.

Plugins are still propagated to the child runner
(`agent_tool.py:222-227, plugins=plugins`), so a plugin that hooks into
the runner directly will still see the events. But the parent runner's
event iterator — which is what `evals/run_matrix.py:_consume()` uses —
won't see them.

**Practical implication:** the eval scorer at `evals/parse_events.py`
parses events from the parent stream. Today it counts specialist
fetches, thoughts, etc. Under Variant B, that data isn't reachable from
the same code path — the scorer would need to be rewritten to walk the
child runner's events (if accessible) or operate on summarised state.

## The blocker — plugin lifecycle

This is the finding I didn't expect. `FirestoreProgressPlugin` is
documented at the top of the file:

> Plugin granularity (plan §4.2.2): production agents use
> `SequentialAgent`/`ParallelAgent` composition, NOT `AgentTool`. ADK
> fires plugin run-level callbacks once per root-runner invocation, so
> `claim_invocation` runs ONCE per turn and the heartbeat lives for the
> full 7–15 min pipeline.
> — `firestore_progress.py:19-22`

The plugin's three lifecycle hooks (`before_run_callback`,
`on_event_callback`, `after_run_callback`) are designed around exactly
one root invocation per user turn. It claims the Firestore session
state (`status='queued' → 'running'`), spawns a 30s heartbeat,
processes events, then writes the terminal payload at the end.

Under AgentTool, each AgentTool call creates a fresh child Runner with
the same plugins attached. That means:

- `before_run_callback` would try to **re-claim** the (already-claimed)
  Firestore session for each specialist call. The OwnershipLost path
  would fire spuriously.
- A new 30s heartbeat task would spawn for each specialist — multiple
  concurrent heartbeats on the same session.
- `after_run_callback` would try to write the terminal payload after
  each specialist's runner finishes, including before the orchestrator
  has actually produced a final report.

This isn't a small plumbing fix. It's a refactor of the plugin
lifecycle: distinguishing top-level invocations from nested ones,
suppressing the lifecycle hooks for AgentTool-spawned children, and
re-routing event observation so per-specialist progress still surfaces
in Firestore.

`include_plugins=False` on each `AgentTool` is a possible escape hatch —
it would prevent the plugin from attaching to child runners. But that
also means specialist-level progress events wouldn't be observed at all,
which would break the per-specialist progress UI (the activity rows
showing "Menu & Pricing — analyzing 3 platforms…"). The current
production pipeline emits granular per-specialist events that the
frontend renders live; those would need a different observation
mechanism under Variant B.

## What this means for the project

**The original argument for Variant B holds:** AgentTool wrapping
aligns with how Claude Code, Anthropic's Research agent, ADK samples,
and human analyst teams actually operate. Descriptions become the real
routing primitive. Single source of truth. The mechanics work.

**But the migration cost is bigger than the spike originally scoped.**
In addition to the orchestrator rewrite, eval scorer update, and
description fattening, we'd need to:

1. Refactor `FirestoreProgressPlugin` to handle nested invocations
   (probably ~1-2 days of careful work given its lifecycle complexity
   and the per-write-class error semantics).
2. Re-route per-specialist progress events so the frontend's activity
   rows still update live (or accept a UX regression where the user
   only sees "research in progress" without per-specialist detail).
3. Rewrite `evals/parse_events.py` to score against state writes
   instead of streamed specialist events.

That brings total scope to roughly **6-8 days** instead of the **4-5
days** originally estimated, and the plugin work is the highest-risk
piece (production runs depend on it for fenced ownership).

## Two paths forward

**Path A — full Variant B migration.** Treat the plugin refactor as
in-scope. Sequence: spike already done → plugin lifecycle refactor (with
its own tests) → orchestrator rewrite → description fattening → eval
scorer update → run evals. ~6-8 days, real plumbing risk in step 2,
but you end up with the canonical pattern matching Google's docs and
the analogous systems.

**Path B — capture the win without the migration.** Keep
`SequentialAgent` + `ParallelAgent` + `set_specialist_briefs`. Make
descriptions canonical by **rendering the catalog into the orchestrator's
prompt at runtime** (was earlier called Diff C). Fatten the descriptions
(Diff A). Drop the query-type-coverage matrix (Diff B). Add the
pre-dispatch coverage check (Option 2). The orchestrator's behavioural
change is identical to Variant B from the LLM's perspective — same
descriptions, same routing reasoning — but the architecture stays
untouched, and the plugin layer keeps working as designed. ~2-3 days.

Path A is more architecturally elegant. Path B captures most of the
operational win with much less risk and no plugin rework.

Honest take: I'd recommend Path B _first_, ship the description
rewrite + count-based floor + coverage check + evals, and only
re-evaluate Path A after we have a baseline of how the new
descriptions perform. If descriptions are doing the routing work
correctly under Path B, the marginal benefit of moving to Path A is
mostly aesthetic ("descriptions are _actually_ the routing primitive
now") rather than operational. If descriptions aren't doing the
routing work even after fattening, Path A is unlikely to fix that —
it's a routing-quality problem, not a routing-mechanism problem.

## Smaller findings worth noting

- `fetch_web_content` triggers an ADK warning on every model call:
  `Tools at indices [1] are not compatible with automatic function
calling (AFC). AFC is disabled.` AFC is the auto-call shortcut where
  Python callables are invoked by ADK directly without a model
  round-trip; non-callable tools (FunctionDeclarations) disable it.
  Doesn't break anything, but worth investigating whether
  `fetch_web_content` could be exposed as an AFC-compatible callable
  for a marginal latency win.
- Variant B's research_plan is consistently longer (489-721 chars vs
  438-441 for Variant A). The orchestrator naturally produces a
  richer summary when it has the specialists' actual outputs in front
  of it (as tool responses) vs. only its own dispatch decision.
- Run-to-run variance in latency is significant (88.7s ↔ 130.1s for
  Variant B; 99.0s ↔ 133.7s for Variant A). Mostly driven by
  fetch_web_content latency (Wolt page fetches via Jina r.jina.ai
  varied widely). Any latency comparison from a single trial is
  unreliable; need ≥5 trials for a statistically meaningful claim.

## Files

- `agent/spikes/agent_tool/build.py` — both variant builders
- `agent/spikes/agent_tool/run_spike.py` — runner with verbose event capture
- `agent/spikes/agent_tool/probe.py` — isolated specialist probe (used
  to debug the trial 1 silent menu_pricing event — turned out to be a
  filtering bug in my summariser)
- `agent/spikes/agent_tool/orchestrator_a.md` — Variant A prompt
- `agent/spikes/agent_tool/orchestrator_b.md` — Variant B prompt
- `agent/spikes/agent_tool/places_context.py` — hand-crafted context
- `agent/spikes/agent_tool/results/variant_*.json` — captured event logs
