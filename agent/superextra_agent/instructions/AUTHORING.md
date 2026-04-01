# Writing Agent Instructions

Read this before writing or modifying any instruction file in this directory.

## Architecture

**Router → Context Enricher → Research Planner → Specialists (via AgentTool) → Synthesizer**

- The **planner** decides what to research and writes a specific brief for each specialist. It's the only communication channel to specialists — anything they need to know (language, date, constraints, what NOT to research) must be in the brief.
- **Specialists** are directed researchers. They only see the planner's brief, not the user's question, the session state, or each other's output.
- The **synthesizer** reads all specialist outputs from state and produces the user-facing answer. It does not research.

## Rules

These exist because we hit each problem at least once.

1. **Agents take the path of least resistance.** If a specialist has Google Places data and isn't told to go beyond it, it will reformat that data and call it research. Every specialist instruction must say: the Places context is your starting point, not your output.

2. **Agents don't coordinate.** If scopes overlap, they will produce identical output. The planner must assign non-overlapping briefs with explicit "do not research X" boundaries.

3. **LLMs default to summarizing.** The synthesizer was compressing 25K chars to 2.2K (91% loss). "Preserve depth" must be an explicit instruction — preserve tables, quotes, numbers, source citations.

4. **Specialists can't infer what they can't see.** The planner must relay: response language, date (`[Date: ...]` format), what other specialists are covering. When you add new context that specialists need, the fix is always in the planner's instructions.

5. **Relevance filtering is the planner's job.** Specialists should not self-filter with "NOT_RELEVANT" logic. The planner only calls specialists whose domain fits.

6. **"Be thorough" is not an instruction.** "Try at least 3 different search queries, check multiple platforms, and quantify patterns" is. Make methodology concrete.

7. **Don't copy-paste across specialist files without customizing.** Shared structure is fine, but examples and methodology must be domain-specific. A menu pricing agent shouldn't have "new restaurants Mokotow 2026" as its search example.

8. **Domain boundaries live in the planner.** When a topic could go to multiple specialists (rent, delivery platforms, reviews), add explicit ownership rules to the planner's "Domain boundaries" section.

9. **Agents are sycophantic by default.** LLMs agree with the user's framing unless explicitly told not to. Every layer must have permission to challenge premises: the planner identifies assumptions and tests them in reconnaissance, specialists report what data shows even when it contradicts the brief's framing, and the synthesizer leads with corrections when findings warrant it. Without this, the system confirms whatever the user already believes.

## Instruction structure

Every specialist instruction follows this structure:

1. Role description (1-2 sentences)
2. Date awareness (`[Date: ...]` prefix)
3. Your assignment (follow the planner's brief)
4. Your scope (domain knowledge reference, not task instruction)
5. How to research (domain-specific search strategies)
6. Restaurant context from Google Places (`{places_context}` template)
7. How to answer (format, specificity, citations)
8. Tone
9. Boundaries

The "Your assignment" section is critical — without it, agents revert to interpreting broadly.

## Template variables

Specialist instructions use `{places_context}`, injected at runtime by `_make_instruction()` in `specialists.py`. The synthesizer has many variables (`{places_context}`, `{research_plan}`, `{market_result}`, etc.) resolved by `_synthesizer_instruction()` in `agent.py`.

Templates use Python's `str.format()`. Never add literal curly braces to `.md` files — use doubled braces (`{{`, `}}`) to escape them.

## Modification checklist

**Adding or removing a specialist:**

1. Create/delete the instruction `.md` file
2. Add/remove the `LlmAgent` in `specialists.py`
3. Add/remove the `AgentTool` wrapper in `SPECIALIST_TOOLS`
4. Update "Available specialist agents" in `research_planner.md`
5. Add/remove `output_key` from `_SYNTHESIZER_KEYS` in `agent.py`
6. Add/remove `{result_key}` in `synthesizer.md`

**Adding a new template variable:**

1. Add `{variable_name}` to the `.md` file
2. Update `_make_instruction()` to resolve it from `ctx.state`
3. Ensure an upstream agent writes to that state key

**Adding an ambiguous domain topic:**

1. Add ownership rules to "Domain boundaries" in `research_planner.md`
2. Clarify scope in relevant specialist `.md` files if needed
