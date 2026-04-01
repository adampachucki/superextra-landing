# Writing Agent Instructions

Guidelines for writing and maintaining instruction files in this directory. These exist because we learned the hard way what happens when instructions are vague, overlapping, or don't account for how agents interact with each other.

## Architecture context

The pipeline is: **Router → Context Enricher → Research Planner → Specialists (via AgentTool) → Synthesizer**

The Research Planner decides which specialists to call and writes a specific brief for each. Specialists don't see the raw user question — they receive the planner's brief as their input. The synthesizer reads all specialist outputs from state and weaves them into a final report.

This means:

- Specialists are **directed researchers**, not independent analysts
- The planner is the only agent that decides what to research
- The synthesizer is the only agent that produces the user-facing answer

## Lessons learned

### Agents will always take the path of least resistance

If an agent has access to pre-gathered data (like Google Places context) and isn't explicitly told to go beyond it, it will reformat that data and call it research. Every specialist instruction must make clear: **the Places context is your starting point, not your output.** Tell the agent what it should find that isn't already there.

### Vague scope = redundant output

When we gave 7 specialists the same broad question ("How does MOOcafe compare?"), 6 of them produced identical competitor rating tables. Agents don't coordinate with each other — if their scopes overlap and they receive the same question, they will do the same work. The planner pattern exists to prevent this, but specialist instructions should still define clear scope boundaries.

### "Summarize" is the default behavior — depth must be demanded

The synthesizer was compressing 25K chars of specialist output down to 2.2K chars (91% loss). LLMs default to summarizing. If you want the synthesizer to preserve specific data points, tables, quotes, and numbers, you must **explicitly say so**. "Preserve depth" is a real instruction, not implied.

### NOT_RELEVANT is the planner's job, not the specialist's

Specialists used to decide relevance themselves, which led to wasted work (agents spending tokens only to say "not my scope") and missed insights (agents self-filtering too aggressively). The planner now handles relevance — it only calls specialists whose domain fits. Specialist instructions should not include self-filtering logic.

## Instruction structure

Every specialist instruction should follow this structure:

```
1. Role description (who you are, 1-2 sentences)
2. Date awareness (use [Date: ...] prefix for time-relative queries)
3. Your assignment (follow the brief you received)
4. Your scope (what domain knowledge you bring)
5. How to research (search strategies specific to your domain)
6. Restaurant context from Google Places ({places_context} template)
7. How to answer (output format, specificity, citations)
8. Tone
9. Boundaries
```

### The assignment section is critical

Every specialist must have this near the top:

```markdown
## Your assignment

Your research brief (the message you received) tells you exactly what to
investigate. Follow it closely — it was crafted to cover a specific angle
and avoid overlap with other specialists working on the same question.
```

Without this, agents revert to interpreting the question broadly and doing whatever they think is relevant.

### The scope section is reference, not instruction

The "Your scope" section lists what the specialist knows about, not what it should do for every query. It helps the agent understand its domain expertise. The actual task comes from the planner's brief.

## Template variables

Specialist instructions use `{places_context}` which gets injected at runtime from session state via `_make_instruction()` in `specialists.py`. If you add a new template variable:

1. Add it to the instruction `.md` file as `{variable_name}`
2. Update `_make_instruction()` in `specialists.py` to resolve it from `ctx.state`
3. Make sure something upstream writes to that state key

The synthesizer uses a different pattern — its template has many variables (`{places_context}`, `{research_plan}`, `{market_result}`, etc.) resolved by `_synthesizer_instruction()` in `agent.py`. If you add a new specialist or state key, update `_SYNTHESIZER_KEYS` in `agent.py`.

## Planner instructions

The research planner has a different structure because it doesn't research — it plans. Key principles baked into its instructions:

- **Depth over breadth** — 2-3 targeted specialists beat 7 vague ones
- **No overlap** — if two specialists would find the same data, only call one
- **Specific briefs** — include what to research, what NOT to research, and what format to use
- **Reconnaissance** — the planner can do quick google_search to orient itself before assigning briefs, but must not produce findings itself
- **Build on Places data** — tell specialists what to find beyond the pre-gathered data

If you change the available specialists (add, remove, rename), update the "Available specialist agents" list in `research_planner.md`.

## Synthesizer instructions

The synthesizer's job is to weave specialist findings into a coherent report. Key rules:

- **Preserve depth** — do not compress specific data into vague summaries
- **Structure by insight theme** — not by specialist name
- **Cite sources** — carry through source citations from specialist findings
- **Ignore missing specialists** — "Agent did not produce output." means it wasn't called, don't mention it
- **End with follow-up topics** — "I can research further on:" + 2-3 objective, detailed topics (no "your/my" — use third person)

## Common mistakes to avoid

- **Don't duplicate the Places context description** — use `{places_context}` template injection, not a paragraph describing what data "may" be available
- **Don't add self-filtering logic** — no "If this question is not relevant to your scope, respond with NOT_RELEVANT". The planner handles this.
- **Don't write instructions that assume the raw user question** — specialists receive the planner's brief, not the user's question
- **Don't tell agents to "be thorough" without saying how** — "search thoroughly" is vague. "Try at least 3 different search queries, check multiple platforms, and quantify patterns" is actionable.
- **Don't forget the date awareness line** — agents must use the `[Date: ...]` prefix to avoid presenting old data as current
