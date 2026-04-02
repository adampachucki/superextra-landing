# Agent Architecture: Simplification Analysis

## Current complexity

The pipeline has 4 control-flow layers before a user gets an answer:

```
Router → Scoper → [User confirmation] → Enricher → Executor → Specialists → Synthesizer
```

For follow-ups, there is a parallel second pipeline:

```
Router → Enricher → Planner → Specialists → Synthesizer
```

15 agents, 2 pipelines, 1,011 lines of instructions, and a mandatory confirmation gate on every first question.

---

## Core problems

**The confirmation step destroys momentum.** The scoper plans 2-5 research angles, presents them, and waits for the user to say "yes." That is 30-60 seconds of latency plus friction — before any actual research has happened. Users came for intelligence, not to approve a research plan they cannot meaningfully evaluate yet.

**Two nearly-identical orchestrators** — Executor and Planner — solve the same problem (plan + dispatch specialists) via different paths depending on conversation state. The only meaningful difference is that Planner does reconnaissance via `google_search` before planning. That is one feature difference, not enough to justify two agents.

**The Router adds a hop without adding value.** It classifies conversation state (first message? follow-up? plan confirmation?), but that classification exists _because_ of the two-pipeline, confirmation-gate design. Remove those and the router largely disappears.

---

## What actually generates value

Three things deliver real intelligence:

1. **Context Enricher** — Places API enrichment of target + competitive set. Grounds everything.
2. **Parallel specialists** — 7 domain experts simultaneously researching different angles. This is the core value engine.
3. **Synthesizer** — Weaves findings into a coherent, premise-tested briefing.

The premise auditing threaded through Planner/Executor/Synthesizer is genuinely valuable and should be preserved.

---

## Recommended architecture

**Collapse to a single pipeline, remove the confirmation gate.**

```
[Orchestrator] → Enricher → Specialists (parallel) → Synthesizer
```

### 1. Merge Scoper + Executor + Planner into one Research Orchestrator

The orchestrator:

- Always runs 2-3 `google_search` reconnaissance queries first (Planner's best feature)
- Audits premises before dispatching (already in Planner)
- Dispatches specialists in parallel immediately — no user confirmation
- Writes execution summary for Synthesizer

This removes 3 agents and 1 UX roundtrip. The user gets a richer first response because reconnaissance is built in, not skipped.

### 2. Remove the Router or reduce to conversation-state detection only

Without a confirmation gate, the Router's 6 rules collapse to roughly 2: "new question" and "follow-up." That is a few lines of state check, not a full agent.

### 3. Collapse to one dynamic researcher

Two `dynamic_researcher` instances with identical instructions exist only because ADK needs separate agent objects for parallel calls. Instantiate them at dispatch time rather than maintaining two named agents.

---

## Handling vague prompts

The confirmation loop was added to make conversation engaging and surface intent from vague prompts. It is solving two different problems at once:

1. **Understanding vague intent** — what does the user actually want researched?
2. **Building engagement/trust** — show the system is thoughtful, not a black box

Those need different solutions.

### Why the confirmation loop is the wrong tool for vague prompts

When a prompt is vague, showing a research plan does not actually resolve the vagueness — the user often just says "looks good" without really evaluating it. Latency is added without gaining clarity.

### Recommended replacements

**One targeted question — best for genuinely ambiguous prompts**

Instead of a full plan, ask one specific question that unlocks the right research direction.

> "Are you trying to understand why ratings dropped, or benchmark against competitors?"

One message, one reply, then straight to research. Faster than plan → confirm and gets better signal.

**Interpret and hedge — best for researchable-but-vague prompts**

Run research on the most likely interpretation, state it upfront in the response:

> "Taking this as a question about competitive positioning in your area — here is what the data shows. If you meant something else, follow up and I will reframe."

Zero roundtrips. The user corrects course via a follow-up, which is already handled by the research pipeline.

**Research-in-progress streaming — best for engagement**

Stream progress instead of asking for plan approval:

> _Researching your competitive set... checking guest sentiment... analyzing pricing..._

Solves the engagement problem without a roundtrip. SSE streaming is already in place.

### Outcome

This collapses 6 router rules to effectively 2:

- Genuinely vague → ask one question
- Everything else → research immediately, state interpretation if needed

The Scoper agent and its confirmation loop go away entirely.

---

## Net impact

|                                 | Now                         | After                                              |
| ------------------------------- | --------------------------- | -------------------------------------------------- |
| Agents                          | 15                          | ~9 (Router, Enricher, Orchestrator, 7 Specialists) |
| Pipelines                       | 2                           | 1                                                  |
| Instruction files               | 15                          | ~11                                                |
| User roundtrips to first answer | 2 (plan confirm + response) | 1 (response)                                       |
| Estimated time to first answer  | 2-3 min                     | 1-1.5 min                                          |
| Premise auditing                | Preserved                   | Preserved (orchestrator + synthesizer)             |
| Specialist depth                | Unchanged                   | Unchanged                                          |

---

## What to keep exactly as-is

- All 7 domain specialist instructions — they are the knowledge layer
- Synthesizer logic including premise-contradiction-first ordering
- `_append_sources` callback — source attribution is genuinely valuable
- Context Enricher and Places API integration
- Multilingual support
